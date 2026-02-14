from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from subprocess import CalledProcessError, check_output

import websockets
from websockets.asyncio.server import ServerConnection, serve

from backend.config import ServerConfig
from backend.question.extractor import ActiveQuestionExtractor
from backend.transcript.buffer import TranscriptBuffer

logger = logging.getLogger(__name__)


def _git_short_sha() -> str:
    try:
        sha = check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
        return sha or "unknown"
    except (FileNotFoundError, CalledProcessError):
        return "unknown"


class TranscriptWebSocket:
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
        if hasattr(self, "_broadcast_task") and self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
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

    async def _cmd_get_settings(self, params: dict) -> dict:
        if not self._settings_manager:
            return {"error": "Settings not available"}
        data = self._settings_manager.to_safe_dict()
        if self._project_manager:
            data["projects"] = self._project_manager.list_projects()
        return data

    async def _cmd_get_status(self, params: dict) -> dict:
        """Return lightweight backend status for clients."""
        active_project = ""
        if self._settings_manager:
            active_project = self._settings_manager.get_active_project() or ""

        return {
            "protocol_version": 1,
            "backend": {
                "name": "meeting-buddy-backend",
                "version": _git_short_sha(),
                "started_at": self._session_start,
                "uptime_s": round(time.time() - self._session_start, 3),
            },
            "active_project": active_project,
            "capabilities": {
                "command_params_envelope": True,
            },
        }

    async def _cmd_set_api_key(self, params: dict) -> dict:
        key = params.get("key", "").strip()
        if not key:
            raise ValueError("API key cannot be empty")
        if not self._settings_manager:
            raise RuntimeError("Settings not available")

        self._settings_manager.set_api_key(key)

        # Reinit or create synthesis engine
        if self._synthesis_engine:
            self._synthesis_engine.reinit_client(key)
        else:
            self._init_synthesis_engine(key)

        return self._settings_manager.to_safe_dict()

    async def _cmd_list_projects(self, params: dict) -> dict:
        if not self._project_manager:
            return {"projects": []}
        projects = self._project_manager.list_projects()
        # Add chunk counts
        for p in projects:
            try:
                from ingest.store import ProjectStore
                store = ProjectStore(Path(p["path"]))
                p["chunk_count"] = store.chunk_count()
            except Exception:
                p["chunk_count"] = 0
        return {"projects": projects}

    async def _cmd_create_project(self, params: dict) -> dict:
        name = params.get("name", "").strip()
        if not name:
            raise ValueError("Project name cannot be empty")
        if not self._project_manager:
            raise RuntimeError("Project manager not available")

        self._project_manager.create_project(name)
        return {"projects": self._project_manager.list_projects()}

    async def _cmd_switch_project(self, params: dict) -> dict:
        name = params.get("name", "").strip()
        if not name:
            raise ValueError("Project name cannot be empty")
        if not self._project_manager:
            raise RuntimeError("Project manager not available")
        if not self._project_manager.project_exists(name):
            raise ValueError(f"Project '{name}' not found")

        if self._settings_manager:
            self._settings_manager.set_active_project(name)

        self._reload_retriever(name)
        self._active_answer = None
        # Reset Q&A history when switching projects to keep sessions scoped
        self._qa_history = []

        return {"active_project": name}

    async def _cmd_delete_project(self, params: dict) -> dict:
        name = params.get("name", "").strip()
        if not name:
            raise ValueError("Project name cannot be empty")
        if not self._project_manager:
            raise RuntimeError("Project manager not available")

        # If deleting active project, clear retriever
        active = self._settings_manager.get_active_project() if self._settings_manager else ""
        if active == name:
            if self._settings_manager:
                self._settings_manager.set_active_project("")
            if self._synthesis_engine:
                self._synthesis_engine.set_retriever(None)
            self._active_answer = None

        self._project_manager.delete_project(name)
        return {"projects": self._project_manager.list_projects()}

    async def _cmd_list_docs(self, params: dict) -> dict:
        active = self._settings_manager.get_active_project() if self._settings_manager else ""
        if not active or not self._project_manager:
            return {"docs": []}

        try:
            from ingest.store import ProjectStore
            project_path = self._project_manager.get_project_path(active)
            store = ProjectStore(project_path)

            docs = store.list_document_details()

            # Merge in per-doc registry fields (description/priority)
            registry = {}
            try:
                registry = self._project_manager.get_doc_registry(active)
            except Exception:
                registry = {}

            for d in docs:
                meta = registry.get(d.get("title")) if isinstance(registry, dict) else None
                if not isinstance(meta, dict):
                    meta = {}
                d["description"] = meta.get("description", "")
                d["priority"] = meta.get("priority", "normal")

            return {"docs": docs}
        except Exception:
            logger.exception("Failed to list docs")
            return {"docs": []}

    async def _cmd_ingest_files(self, params: dict) -> dict:
        paths = params.get("paths", [])
        if not paths:
            raise ValueError("No file paths provided")

        active = self._settings_manager.get_active_project() if self._settings_manager else ""
        if not active:
            raise RuntimeError("No active project — create or switch to one first")

        if self._ingestion_in_progress:
            raise RuntimeError("Ingestion already in progress")

        # Ack immediately, run in background
        asyncio.create_task(self._run_ingestion(active, paths))
        return {"status": "started", "file_count": len(paths)}

    async def _cmd_delete_doc(self, params: dict) -> dict:
        title = params.get("title", "").strip()
        if not title:
            raise ValueError("Document title cannot be empty")

        active = self._settings_manager.get_active_project() if self._settings_manager else ""
        if not active or not self._project_manager:
            raise RuntimeError("No active project")

        from ingest.store import ProjectStore
        project_path = self._project_manager.get_project_path(active)
        store = ProjectStore(project_path)
        deleted = store.delete_document(title)

        # Reload retriever to pick up changes
        self._reload_retriever(active)

        return {"deleted_chunks": deleted, "docs": store.list_documents()}

    async def _cmd_get_doc_meta(self, params: dict) -> dict:
        """Return doc_registry metadata for a given doc title."""
        title = (params.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")

        active = self._settings_manager.get_active_project() if self._settings_manager else ""
        if not active or not self._project_manager:
            raise RuntimeError("No active project")

        reg = self._project_manager.get_doc_registry(active)
        entry = reg.get(title) if isinstance(reg, dict) else None
        if not isinstance(entry, dict):
            entry = {"description": "", "priority": "normal"}
        return {"title": title, "meta": entry}

    async def _cmd_update_doc_meta(self, params: dict) -> dict:
        """Update doc_registry metadata for a given doc title."""
        title = (params.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")

        active = self._settings_manager.get_active_project() if self._settings_manager else ""
        if not active or not self._project_manager:
            raise RuntimeError("No active project")

        description = params.get("description")
        priority = params.get("priority")
        entry = self._project_manager.update_doc_meta(
            active,
            doc_title=title,
            description=description,
            priority=priority,
        )
        return {"title": title, "meta": entry}

    # --- OAuth login commands ---

    async def _cmd_start_login(self, params: dict) -> dict:
        if not self._token_manager:
            raise RuntimeError("OAuth not configured")
        from backend.auth.login_server import LoginServer
        self._login_server = LoginServer(self._token_manager)
        auth_url = await self._login_server.start_login()
        # Run the await-login in background — when it completes, reinit synthesis
        asyncio.create_task(self._complete_login())
        return {"auth_url": auth_url}

    async def _complete_login(self) -> None:
        try:
            await self._login_server.await_login(timeout=120)
            # Switch to oauth auth method
            if self._settings_manager:
                self._settings_manager.set_auth_method("oauth")
            # Reinit synthesis with OAuth credentials (ChatGPT backend)
            access_token = self._token_manager.get_api_key()
            account_id = self._token_manager.get_chatgpt_account_id()
            if access_token and account_id:
                if self._synthesis_engine:
                    self._synthesis_engine.reinit_client_oauth(access_token, account_id)
                else:
                    self._init_synthesis_engine(access_token)
            # Broadcast auth_complete event
            await self._broadcast_event({
                "type": "auth_complete",
                "oauth_status": self._token_manager.to_status_dict(),
            })
        except Exception:
            logger.exception("Login flow failed")
            await self._broadcast_event({
                "type": "auth_error",
                "error": "Login failed — try again",
            })
        finally:
            self._login_server = None

    async def _cmd_login_status(self, params: dict) -> dict:
        if not self._token_manager:
            return {"logged_in": False, "email": "", "expires_at_ms": 0}
        return self._token_manager.to_status_dict()

    async def _cmd_logout(self, params: dict) -> dict:
        if not self._token_manager:
            raise RuntimeError("OAuth not configured")
        self._token_manager.clear()
        if self._settings_manager:
            self._settings_manager.set_auth_method("api_key")
        # Don't null synthesis engine — manual API key may still work
        await self._broadcast_event({"type": "auth_logout"})
        return {"logged_out": True}

    async def _cmd_select_question(self, params: dict) -> dict:
        """Manually select a question from history (or resume auto-detection)."""
        text = params.get("text")  # None = resume auto
        if not self._extractor:
            raise RuntimeError("Question extractor not available")
        self._extractor.select_question(text)
        # Trigger synthesis for the selected question
        if text and self._synthesis_engine:
            asyncio.create_task(self._run_synthesis(text))
        return {"selected": text}

    async def _cmd_get_qa_history(self, params: dict) -> dict:
        """Return the current in-memory Q&A history for this session."""
        # Return a shallow copy so callers can't mutate internal state
        return {"qa_history": list(self._qa_history)}

    async def _cmd_set_question(self, params: dict) -> dict:
        """Manually override the active question with free-form text."""
        text = (params.get("text") or "").strip()
        if not self._extractor:
            raise RuntimeError("Question extractor not available")

        # Empty string = clear manual override
        if not text:
            self._extractor.select_question(None)
            return {"selected": None}

        self._extractor.select_question(text)
        if self._synthesis_engine:
            asyncio.create_task(self._run_synthesis(text))
        return {"selected": text}

    # --- Prep mode (pre-meeting Q&A) ---

    async def _cmd_generate_prep_questions(self, params: dict) -> dict:
        count = int(params.get("count", 12))
        active = self._settings_manager.get_active_project() if self._settings_manager else ""
        if not active or not self._project_manager:
            raise RuntimeError("No active project")
        if not self._synthesis_engine:
            raise RuntimeError("Synthesis engine not available")

        # Use doc_registry descriptions/priorities as the context seed.
        doc_registry = self._project_manager.get_doc_registry(active)
        from backend.synthesis.prep import PrepQuestionGenerator

        gen = PrepQuestionGenerator(self._synthesis_engine)
        qs = await gen.generate(doc_registry, count=count)
        self._prep_questions = qs
        self._prep_results = {}
        return {"questions": qs}

    async def _cmd_get_prep_results(self, params: dict) -> dict:
        return {
            "questions": self._prep_questions,
            "results": self._prep_results,
        }

    async def _cmd_add_prep_question(self, params: dict) -> dict:
        q = (params.get("text") or "").strip()
        if not q:
            raise ValueError("text is required")
        if q not in self._prep_questions:
            self._prep_questions.append(q)

        if self._synthesis_engine:
            result = await self._synthesis_engine.synthesize_once(q)
            self._prep_results[q] = result.to_dict()
        return {"questions": self._prep_questions, "results": self._prep_results}

    # --- Pinned answers ---

    async def _cmd_get_pinned(self, params: dict) -> dict:
        return {"pinned": list(self._pinned_answers)}

    async def _cmd_pin_answer(self, params: dict) -> dict:
        """Pin the current answer (or a provided answer payload) for quick recall."""
        question = (params.get("question") or "").strip()
        answer = params.get("answer")

        if not question and self._last_question:
            question = self._last_question
        if answer is None:
            answer = self._active_answer

        if not question or not answer:
            raise ValueError("No answer available to pin")

        # Dedup by question text
        for item in self._pinned_answers:
            if item.get("question") == question:
                return {"pinned": list(self._pinned_answers)}

        self._pin_seq += 1
        item = {
            "id": str(self._pin_seq),
            "question": question,
            "answer": answer,
            "timestamp": time.time(),
        }
        self._pinned_answers.insert(0, item)
        await self._broadcast_event({"type": "pinned_update", "pinned": list(self._pinned_answers)})
        return {"pinned": list(self._pinned_answers)}

    async def _cmd_unpin_answer(self, params: dict) -> dict:
        pid = (params.get("id") or "").strip()
        question = (params.get("question") or "").strip()

        before = len(self._pinned_answers)
        if pid:
            self._pinned_answers = [p for p in self._pinned_answers if str(p.get("id")) != pid]
        elif question:
            self._pinned_answers = [p for p in self._pinned_answers if p.get("question") != question]
        else:
            raise ValueError("id or question is required")

        if len(self._pinned_answers) != before:
            await self._broadcast_event({"type": "pinned_update", "pinned": list(self._pinned_answers)})
        return {"pinned": list(self._pinned_answers)}

    async def _cmd_export_session(self, params: dict) -> dict:
        """Export session data as markdown or JSON."""
        from backend.export.renderer import SessionData, render_json, render_markdown

        fmt = params.get("format", "markdown")
        if fmt not in ("markdown", "json"):
            raise ValueError(f"Unsupported format: {fmt}")

        save_path = params.get("path", "")

        # Collect session data
        segments = self.buffer.get_segments()
        project_name = ""
        if self._settings_manager:
            project_name = self._settings_manager.get_active_project() or ""

        session = SessionData(
            transcript_segments=[seg.to_dict() for seg in segments],
            qa_history=self._qa_history,
            project_name=project_name,
            session_start=self._session_start,
            session_end=time.time(),
        )

        if fmt == "markdown":
            content = render_markdown(session)
            ext = ".md"
        else:
            content = render_json(session)
            ext = ".json"

        # Determine output path
        if save_path:
            out = Path(save_path)
        else:
            export_dir = Path("~/.meeting-buddy/exports").expanduser()
            export_dir.mkdir(parents=True, exist_ok=True)
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"session_{timestamp}{ext}"
            out = export_dir / filename

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        logger.info("Session exported to %s", out)

        return {"path": str(out), "format": fmt}

    async def _cmd_get_audio_status(self, params: dict) -> dict:
        """Return diagnostic information about audio capture."""
        if not hasattr(self, '_capture') or self._capture is None:
            return {
                "error": "Audio capture not available",
                "running": False,
            }
        
        status = self._capture.get_status()
        return {"audio_status": status}

    # --- Background ingestion ---

    async def _run_ingestion(self, project_name: str, paths: list[str]) -> None:
        self._ingestion_in_progress = True
        total_chunks = 0
        errors = []

        try:
            from ingest.config import IngestConfig
            from ingest.pipeline import IngestPipeline

            config = self._ingest_config or IngestConfig()
            pipeline = IngestPipeline(config)
            loop = asyncio.get_event_loop()

            for i, path_str in enumerate(paths):
                # Detect if it's a URL
                is_url = isinstance(path_str, str) and ("://" in path_str or path_str.startswith("http"))
                
                try:
                    if is_url:
                        display_name = path_str
                    else:
                        path = Path(path_str)
                        display_name = path.name
                    
                    await self._broadcast_event({
                        "type": "ingest_progress",
                        "current": i + 1,
                        "total": len(paths),
                        "file": display_name,
                    })

                    if is_url:
                        # Ingest URL directly
                        count = await loop.run_in_executor(
                            None, pipeline.ingest_file, project_name, path_str
                        )
                    else:
                        path = Path(path_str)
                        if path.is_dir():
                            count = await loop.run_in_executor(
                                None, pipeline.ingest_directory, project_name, path
                            )
                        else:
                            count = await loop.run_in_executor(
                                None, pipeline.ingest_file, project_name, path_str
                            )
                    total_chunks += count
                except Exception as e:
                    logger.exception("Failed to ingest %s", path_str)
                    display_name = path_str if is_url else Path(path_str).name
                    errors.append({"file": display_name, "error": str(e)})

            # Reload retriever after ingestion
            self._reload_retriever(project_name)

            await self._broadcast_event({
                "type": "ingest_complete",
                "total_chunks": total_chunks,
                "file_count": len(paths),
                "errors": errors,
            })
        except Exception:
            logger.exception("Ingestion failed")
            await self._broadcast_event({
                "type": "ingest_complete",
                "total_chunks": 0,
                "file_count": len(paths),
                "errors": [{"file": "pipeline", "error": "Ingestion pipeline failed"}],
            })
        finally:
            self._ingestion_in_progress = False

    # --- Helpers ---

    def _reload_retriever(self, project_name: str) -> None:
        """Swap retriever for a new project."""
        if not self._project_manager or not self._ingest_config:
            return
        try:
            from ingest.retriever import Retriever

            project_path = self._project_manager.get_project_path(project_name)
            retriever = Retriever(project_path, self._ingest_config)
            if self._synthesis_engine:
                self._synthesis_engine.set_retriever(retriever)
            logger.info("Retriever reloaded for project '%s'", project_name)
        except Exception:
            logger.exception("Failed to reload retriever for '%s'", project_name)

    def _init_synthesis_engine(self, api_key: str) -> None:
        """Create synthesis engine on first API key save."""
        try:
            from backend.config import SynthesisConfig
            from backend.synthesis.engine import SynthesisEngine

            config = SynthesisConfig()
            if self._settings_manager:
                config.model = self._settings_manager.get_synthesis_model()

            import os
            os.environ["OPENAI_API_KEY"] = api_key
            self._synthesis_engine = SynthesisEngine(config)
            self._synthesis_engine.reinit_client(api_key)

            # Attach retriever if we have an active project
            active = self._settings_manager.get_active_project() if self._settings_manager else ""
            if active:
                self._reload_retriever(active)

            logger.info("Synthesis engine created with new API key")
        except Exception:
            logger.exception("Failed to create synthesis engine")

    # --- Transcript broadcast (unchanged) ---

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

            question = self._extractor.current_question if self._extractor else None
            question_changed = question != self._last_question
            
            if question_changed:
                logger.info("[WebSocket] Question changed: '%s' -> '%s'", self._last_question, question)
            
            self._last_question = question

            if question_changed and question and self._synthesis_engine:
                # Only auto-trigger synthesis when not in manual mode
                if not self._synthesis_in_flight and self._extractor and self._extractor._manual_question is None:
                    logger.info("[WebSocket] Triggering synthesis for question: %s", question)
                    asyncio.create_task(self._run_synthesis(question))
                else:
                    if self._synthesis_in_flight:
                        logger.debug("[WebSocket] Synthesis already in flight, skipping")
                    elif self._extractor and self._extractor._manual_question is not None:
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
        # Notify clients that synthesis is in progress
        await self._broadcast_event({"type": "synthesis_searching", "question": question})
        try:
            # Get recent transcript context (last 90 seconds) for disambiguation
            transcript_context = self.buffer.get_recent_text(lookback_seconds=90.0)
            
            # Use streaming synthesis
            full_text = ""
            streamed = False
            async for delta in self._synthesis_engine.synthesize_stream(question, transcript_context=transcript_context):
                streamed = True
                full_text += delta
                # Try to parse partial JSON for one_liner preview
                partial_one_liner = self._try_parse_partial_json(full_text)
                if partial_one_liner:
                    await self._broadcast_event({
                        "type": "answer_partial",
                        "partial_text": partial_one_liner,
                    })
            
            # If no streaming occurred (cached result), fall back to non-streaming
            if not streamed or not full_text:
                result = await self._synthesis_engine.synthesize(question, transcript_context=transcript_context)
                if result is not None:
                    answer_dict = result.to_dict()
                    self._active_answer = answer_dict
                    self._qa_history.append({
                        "question": question,
                        "answer": answer_dict,
                        "timestamp": time.time(),
                    })
                    max_history = 100
                    if len(self._qa_history) > max_history:
                        self._qa_history = self._qa_history[-max_history:]
                    await self._broadcast_answer()
                return
            
            # Parse final JSON result from streamed text
            try:
                import json
                data = json.loads(full_text)
                result_dict = {
                    "one_liner": data.get("one_liner", ""),
                    "bullets": data.get("bullets", []),
                    "best_practice_bullets": data.get("best_practice_bullets", []),
                    "clarifiers": data.get("clarifiers", []),
                    "citations": data.get("citations", []),
                    "confidence": float(data.get("confidence", 0.0)),
                }
                
                # Validate citations if we have retrieval results
                # (Note: we'd need to pass results through, but for now just use what we have)
                
                self._active_answer = result_dict
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
                await self._broadcast_answer()
            except json.JSONDecodeError:
                logger.exception("Failed to parse synthesis JSON")
                await self._broadcast_event({"type": "synthesis_error", "error": "Failed to parse response"})
        except Exception:
            logger.exception("Synthesis task failed")
            await self._broadcast_event({"type": "synthesis_error", "error": "Synthesis failed"})
        finally:
            self._synthesis_in_flight = False

    def _try_parse_partial_json(self, text: str) -> str | None:
        """Try to extract partial one_liner from incomplete JSON."""
        try:
            import json
            import re
            # Look for "one_liner": "..." pattern, even if JSON is incomplete
            match = re.search(r'"one_liner"\s*:\s*"([^"]*)"', text)
            if match:
                return match.group(1)
            # Try parsing if JSON looks complete enough
            if text.strip().endswith("}") or '"one_liner"' in text:
                data = json.loads(text + '"}')  # Try to complete it
                return data.get("one_liner", "")
        except Exception:
            pass
        return None

    async def _broadcast_answer(self) -> None:
        """Broadcast an answer_update message to all clients."""
        if not self._clients or not self._active_answer:
            return

        message = json.dumps({
            "type": "answer_update",
            "active_answer": self._active_answer,
        })
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
            msg["manual_question"] = self._extractor._manual_question is not None
        msg["synthesis_searching"] = self._synthesis_in_flight
        if self._active_answer:
            msg["active_answer"] = self._active_answer
        # Always include Q&A history so new clients get full session context
        msg["qa_history"] = list(self._qa_history)
        msg["pinned"] = list(self._pinned_answers)
        return msg
