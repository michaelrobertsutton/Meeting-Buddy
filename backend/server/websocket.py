from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from subprocess import CalledProcessError, check_output

import websockets
from websockets.asyncio.server import ServerConnection, serve

from backend.server._commands import CommandsMixin, _git_short_sha
from backend.config import ServerConfig
from backend.question.extractor import ActiveQuestionExtractor
from backend.transcript.buffer import TranscriptBuffer

logger = logging.getLogger(__name__)



class TranscriptWebSocket(CommandsMixin):
    """WebSocket server that broadcasts transcript updates and handles commands."""

    def __init__(
        self,
        config: ServerConfig,
        buffer: TranscriptBuffer,
        extractor: ActiveQuestionExtractor | None = None,
        synthesis_engine=None,
        settings_manager=None,
        project_manager=None,
        ingest_config=None,
        token_manager=None,
    ):
        self.config = config
        self.buffer = buffer
        self._extractor = extractor
        self._synthesis_engine = synthesis_engine
        self._settings_manager = settings_manager
        self._project_manager = project_manager
        self._ingest_config = ingest_config
        self._token_manager = token_manager
        self._login_server = None
        self._clients: set[ServerConnection] = set()
        self._server = None
        self._broadcast_task: asyncio.Task | None = None
        self._last_question: str | None = None
        self._active_answer: dict | None = None
        self._synthesis_in_flight: bool = False
        self._ingestion_in_progress: bool = False
        # In-memory history of Q&A pairs for the current session
        self._qa_history: list[dict] = []
        self._session_start: float = time.time()
        # Prep-mode cache (pre-meeting Q&A)
        self._prep_questions: list[str] = []
        self._prep_results: dict[str, dict] = {}  # question -> answer dict

        # Pinned/bookmarked answers (session state)
        self._pinned_answers: list[dict] = []  # [{id, question, answer, timestamp}]
        self._pin_seq: int = 0
        # Pause/listening: when False, ASR is paused and synthesis is not triggered
        self._listening: bool = True
        self._streaming = None  # Set by main: StreamingASR instance

        # Latency instrumentation (best-effort; values in milliseconds)
        self._latency_last: dict | None = None
        # Speculative retrieval state
        self._speculative_task: asyncio.Task | None = None
        self._speculative_question: str | None = None
        self._speculative_chunks: list | None = None

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._server = await serve(
            self._handler,
            self.config.host,
            self.config.port,
        )
        logger.info("WebSocket server listening on ws://%s:%d", self.config.host, self.config.port)
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        if self._speculative_task and not self._speculative_task.done():
            self._speculative_task.cancel()
            try:
                await self._speculative_task
            except asyncio.CancelledError:
                pass
        self._speculative_task = None
        self._speculative_chunks = None
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            finally:
                self._broadcast_task = None
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("WebSocket server stopped")

    async def _handler(self, ws: ServerConnection) -> None:
        """Handle a new client connection."""
        self._clients.add(ws)
        logger.info("Client connected (%d total)", len(self._clients))

        try:
            snapshot = self._build_message("snapshot")
            await ws.send(json.dumps(snapshot))

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    if "command" in msg:
                        await self._handle_command(ws, msg)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from client")
                except Exception:
                    logger.exception("Error handling client message")
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            logger.info("Client disconnected (%d remaining)", len(self._clients))

    # --- Command dispatch ---

    async def _handle_command(self, ws: ServerConnection, msg: dict) -> None:
        """Dispatch a client command and send response."""
        cmd = msg.get("command", "")
        msg_id = msg.get("id")
        # Preferred envelope going forward:
        #   {"id": "1", "command": "switch_project", "params": {"name": "..."}}
        # Back-compat: legacy "flat" params at top-level.
        params = msg.get("params")
        if not isinstance(params, dict):
            params = {k: v for k, v in msg.items() if k not in ("command", "id", "params")}

        handlers = {
            "get_settings": self._cmd_get_settings,
            "set_api_key": self._cmd_set_api_key,
            "list_projects": self._cmd_list_projects,
            "create_project": self._cmd_create_project,
            "switch_project": self._cmd_switch_project,
            "delete_project": self._cmd_delete_project,
            "list_docs": self._cmd_list_docs,
            "ingest_files": self._cmd_ingest_files,
            "delete_doc": self._cmd_delete_doc,
            "get_doc_meta": self._cmd_get_doc_meta,
            "update_doc_meta": self._cmd_update_doc_meta,
            "start_login": self._cmd_start_login,
            "login_status": self._cmd_login_status,
            "logout": self._cmd_logout,
            "select_question": self._cmd_select_question,
            "get_qa_history": self._cmd_get_qa_history,
            "set_question": self._cmd_set_question,
            "generate_prep_questions": self._cmd_generate_prep_questions,
            "get_prep_results": self._cmd_get_prep_results,
            "add_prep_question": self._cmd_add_prep_question,
            "pin_answer": self._cmd_pin_answer,
            "unpin_answer": self._cmd_unpin_answer,
            "get_pinned": self._cmd_get_pinned,
            "export_session": self._cmd_export_session,
            "get_audio_status": self._cmd_get_audio_status,
            "get_status": self._cmd_get_status,
            "set_listening": self._cmd_set_listening,
        }

        handler = handlers.get(cmd)
        if not handler:
            await self._send_response(ws, msg_id, False, error=f"Unknown command: {cmd}")
            return

        try:
            data = await handler(params)
            await self._send_response(ws, msg_id, True, data=data)
        except Exception as e:
            logger.exception("Command '%s' failed", cmd)
            await self._send_response(ws, msg_id, False, error=str(e))

    async def _send_response(self, ws: ServerConnection, msg_id, success: bool,
                             data=None, error=None) -> None:
        resp = {"type": "response", "id": msg_id, "success": success}
        if data is not None:
            resp["data"] = data
        if error is not None:
            resp["error"] = error
        try:
            await ws.send(json.dumps(resp))
        except websockets.ConnectionClosed:
            pass

    async def _broadcast_event(self, event: dict) -> None:
        """Push an event to all connected clients."""
        if not self._clients:
            return
        raw = json.dumps(event)
        disconnected = set()
        for ws in self._clients:
            try:
                await ws.send(raw)
            except websockets.ConnectionClosed:
                disconnected.add(ws)
        self._clients -= disconnected

    # --- Command handlers ---

    # --- Transcript broadcast (unchanged) ---

    async def _run_speculative_retrieval(self, question):
        """Kick off LanceDB retrieval speculatively (before debounce fires)."""
        try:
            engine = self._synthesis_engine
            if not engine or not engine._retriever:
                return
            loop = asyncio.get_event_loop()
            chunks = await loop.run_in_executor(None, engine._retriever.retrieve, question)
            self._speculative_chunks = chunks
            logger.debug("[Speculative] Done: %s (%d chunks)", question, len(chunks))
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("[Speculative] Retrieval failed")

    async def _broadcast_loop(self) -> None:
        """Poll for transcript updates and broadcast to all clients."""
        last_version = -1
        poll_interval = self.config.poll_interval_ms / 1000.0

        while True:
            await asyncio.sleep(poll_interval)

            current_version = self.buffer.get_version()
            transcript_changed = current_version != last_version

            if transcript_changed:
                logger.debug("[WebSocket] Transcript changed: version %d -> %d", last_version, current_version)
                if self._extractor:
                    logger.debug("[WebSocket] Calling extractor.update()")
                    self._extractor.update()
                else:
                    logger.warning("[WebSocket] Transcript changed but no extractor available")

            candidate = self._extractor.candidate_question if self._extractor else None
            if candidate and candidate != self._speculative_question:
                if self._speculative_task and not self._speculative_task.done():
                    self._speculative_task.cancel()
                self._speculative_question = candidate
                self._speculative_chunks = None
                self._speculative_task = asyncio.create_task(
                    self._run_speculative_retrieval(candidate)
                )

            question = self._extractor.current_question if self._extractor else None
            question_changed = question != self._last_question
            
            if question_changed:
                logger.info("[WebSocket] Question changed: '%s' -> '%s'", self._last_question, question)
            
            self._last_question = question

            if question_changed and question and self._synthesis_engine and self._listening:
                # Only auto-trigger synthesis when not in manual mode and listening
                if not self._synthesis_in_flight and self._extractor and not self._extractor.is_manual_override:
                    logger.info("[WebSocket] Triggering synthesis for question: %s", question)
                    asyncio.create_task(self._run_synthesis(question))
                else:
                    if self._synthesis_in_flight:
                        logger.debug("[WebSocket] Synthesis already in flight, skipping")
                    elif self._extractor and self._extractor.is_manual_override:
                        logger.debug("[WebSocket] Manual question override active, skipping auto-synthesis")
                    else:
                        logger.debug("[WebSocket] No synthesis engine available")

            # Periodic audio health check (every 10 seconds)
            current_time = time.time()
            if not hasattr(self, '_last_audio_check_time'):
                self._last_audio_check_time = current_time
            
            if current_time - self._last_audio_check_time >= 10.0:
                self._last_audio_check_time = current_time
                if hasattr(self, '_capture') and self._capture:
                    status = self._capture.get_status()
                    if not status.get("receiving_audio", False) and status.get("running", False):
                        # Process is running but no audio received in last 2 seconds
                        seconds_since = status.get("seconds_since_last_frame", 0)
                        frames_received = status.get("frames_received", 0)
                        logger.warning(
                            "Audio capture health check: Process running but no audio frames received "
                            "in last %.1f seconds (total frames: %d). "
                            "Check Screen Recording permission and ensure audio is playing.",
                            seconds_since,
                            frames_received
                        )
                        # Broadcast warning to clients
                        await self._broadcast_event({
                            "type": "audio_warning",
                            "message": "No audio detected. Check Screen Recording permission and ensure audio is playing.",
                            "status": status,
                        })

            if not transcript_changed and not question_changed:
                continue
            last_version = current_version

            if not self._clients:
                continue

            message = json.dumps(self._build_message("update", include_segments=transcript_changed))
            disconnected = set()
            for ws in self._clients:
                try:
                    await ws.send(message)
                except websockets.ConnectionClosed:
                    disconnected.add(ws)

            self._clients -= disconnected

    async def _run_synthesis(self, question: str) -> None:
        """Run synthesis with streaming and broadcast partial + final results."""
        self._synthesis_in_flight = True

        # Latency instrumentation (monotonic for deltas; wall clock for logs)
        t0 = time.monotonic()
        first_delta_ms: float | None = None

        # Notify clients that synthesis is in progress
        await self._broadcast_event({"type": "synthesis_searching", "question": question})
        try:
            # Get recent transcript context (last 90 seconds) for disambiguation
            transcript_context = self.buffer.get_recent_text(lookback_seconds=self.config.transcript_lookback_s)

            # Use streaming synthesis (with speculative prefetch if available)
            prefetched = None
            if self._speculative_question == question and self._speculative_chunks is not None:
                prefetched = self._speculative_chunks
                self._speculative_chunks = None
                logger.info("[Speculative] Prefetch hit for synthesis: %s", question)
            full_text = ""
            streamed = False
            async for delta in self._synthesis_engine.synthesize_stream(
                question, transcript_context=transcript_context,
                prefetched_chunks=prefetched,
            ):
                if first_delta_ms is None:
                    first_delta_ms = round((time.monotonic() - t0) * 1000.0, 1)
                streamed = True
                full_text += delta
                # Try to parse partial JSON for one_liner preview
                partial_one_liner = self._try_parse_partial_json(full_text)
                if partial_one_liner:
                    await self._broadcast_event(
                        {
                            "type": "answer_partial",
                            "partial_text": partial_one_liner,
                            "timings": {
                                "ttft_ms": first_delta_ms,
                            },
                        }
                    )

            # If no streaming occurred (cached result), fall back to non-streaming
            if not streamed or not full_text:
                result = await self._synthesis_engine.synthesize(
                    question, transcript_context=transcript_context
                )
                if result is not None:
                    answer_dict = result.to_dict()
                    self._active_answer = answer_dict
                    self._qa_history.append(
                        {
                            "question": question,
                            "answer": answer_dict,
                            "timestamp": time.time(),
                        }
                    )
                    max_history = 100
                    if len(self._qa_history) > max_history:
                        self._qa_history = self._qa_history[-max_history:]

                    total_ms = round((time.monotonic() - t0) * 1000.0, 1)
                    self._latency_last = {
                        "question": question,
                        "ttft_ms": first_delta_ms,
                        "total_ms": total_ms,
                        "retrieval_ms": getattr(self._synthesis_engine, "last_retrieval_ms", None),
                        "cache_hit": getattr(self._synthesis_engine, "cache_hit", False),
                        "mode": "non_streaming_fallback",
                    }

                    await self._broadcast_answer(timings=self._latency_last)
                return

            # Parse final JSON result from streamed text
            try:
                data = json.loads(full_text)
                result_dict = {
                    "one_liner": data.get("one_liner", ""),
                    "bullets": data.get("bullets", []),
                    "best_practice_bullets": data.get("best_practice_bullets", []),
                    "clarifiers": data.get("clarifiers", []),
                    "citations": data.get("citations", []),
                    "confidence": float(data.get("confidence", 0.0)),
                }

                self._active_answer = result_dict
                from backend.synthesis.engine import SynthesisResult as _SR
                self._synthesis_engine.cache_result(question, _SR(**result_dict))
                # Append to in-memory Q&A history for this session
                self._qa_history.append(
                    {
                        "question": question,
                        "answer": result_dict,
                        "timestamp": time.time(),
                    }
                )
                # Keep only the most recent N entries to avoid unbounded growth
                max_history = 100
                if len(self._qa_history) > max_history:
                    self._qa_history = self._qa_history[-max_history:]

                total_ms = round((time.monotonic() - t0) * 1000.0, 1)
                self._latency_last = {
                    "question": question,
                    "ttft_ms": first_delta_ms,
                    "total_ms": total_ms,
                    "retrieval_ms": getattr(self._synthesis_engine, "last_retrieval_ms", None),
                    "cache_hit": getattr(self._synthesis_engine, "cache_hit", False),
                    "mode": "streaming",
                }

                await self._broadcast_answer(timings=self._latency_last)
            except json.JSONDecodeError:
                logger.exception("Failed to parse synthesis JSON")
                await self._broadcast_event(
                    {"type": "synthesis_error", "error": "Failed to parse response"}
                )
        except Exception:
            logger.exception("Synthesis task failed")
            await self._broadcast_event({"type": "synthesis_error", "error": "Synthesis failed"})
        finally:
            self._synthesis_in_flight = False

    def _try_parse_partial_json(self, text: str) -> str | None:
        """Try to extract partial one_liner from incomplete JSON via regex only."""
        try:
            match = re.search(r'"one_liner"\s*:\s*"([^"]*)"', text)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    async def _broadcast_answer(self, timings: dict | None = None) -> None:
        """Broadcast an answer_update message to all clients."""
        if not self._clients or not self._active_answer:
            return

        payload = {
            "type": "answer_update",
            "active_answer": self._active_answer,
        }
        if timings:
            payload["timings"] = timings

        message = json.dumps(payload)
        disconnected = set()
        for ws in self._clients:
            try:
                await ws.send(message)
            except websockets.ConnectionClosed:
                disconnected.add(ws)
        self._clients -= disconnected

    def _build_message(self, msg_type: str, include_segments: bool = True) -> dict:
        """Build a message payload from current buffer state.

        `segments` can be omitted for non-transcript updates to reduce UI churn.
        """
        msg = {
            "type": msg_type,
            "protocol_version": 1,
            "version": self.buffer.get_version(),
        }
        if include_segments:
            segments = self.buffer.get_segments()
            msg["segments"] = [seg.to_dict() for seg in segments]
        if self._extractor:
            msg["active_question"] = self._extractor.current_question
            msg["question_history"] = self._extractor.question_history
            msg["manual_question"] = self._extractor.is_manual_override
        msg["synthesis_searching"] = self._synthesis_in_flight
        if self._active_answer:
            msg["active_answer"] = self._active_answer
        # Always include Q&A history so new clients get full session context
        msg["qa_history"] = list(self._qa_history)
        msg["pinned"] = list(self._pinned_answers)
        # Be defensive: older tests/mocks may not include this attribute.
        msg["listening"] = getattr(self, "_listening", True)
        return msg
