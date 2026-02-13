from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import websockets
from websockets.asyncio.server import ServerConnection, serve

from backend.config import ServerConfig
from backend.question.extractor import ActiveQuestionExtractor
from backend.transcript.buffer import TranscriptBuffer

logger = logging.getLogger(__name__)


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

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._server = await serve(
            self._handler,
            self.config.host,
            self.config.port,
        )
        logger.info("WebSocket server listening on ws://%s:%d", self.config.host, self.config.port)
        asyncio.create_task(self._broadcast_loop())

    async def stop(self) -> None:
        """Stop the WebSocket server."""
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
        params = {k: v for k, v in msg.items() if k not in ("command", "id")}

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
            "start_login": self._cmd_start_login,
            "login_status": self._cmd_login_status,
            "logout": self._cmd_logout,
            "select_question": self._cmd_select_question,
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
            titles = store.list_documents()
            return {"docs": titles}
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
                path = Path(path_str)
                try:
                    await self._broadcast_event({
                        "type": "ingest_progress",
                        "current": i + 1,
                        "total": len(paths),
                        "file": path.name,
                    })

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
                    errors.append({"file": path.name, "error": str(e)})

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

            if transcript_changed and self._extractor:
                self._extractor.update()

            question = self._extractor.current_question if self._extractor else None
            question_changed = question != self._last_question
            self._last_question = question

            if question_changed and question and self._synthesis_engine:
                # Only auto-trigger synthesis when not in manual mode
                if not self._synthesis_in_flight and self._extractor and self._extractor._manual_question is None:
                    asyncio.create_task(self._run_synthesis(question))

            if not transcript_changed and not question_changed:
                continue
            last_version = current_version

            if not self._clients:
                continue

            message = json.dumps(self._build_message("update"))
            disconnected = set()
            for ws in self._clients:
                try:
                    await ws.send(message)
                except websockets.ConnectionClosed:
                    disconnected.add(ws)

            self._clients -= disconnected

    async def _run_synthesis(self, question: str) -> None:
        """Run synthesis and broadcast result immediately."""
        self._synthesis_in_flight = True
        # Notify clients that synthesis is in progress
        await self._broadcast_event({"type": "synthesis_searching", "question": question})
        try:
            result = await self._synthesis_engine.synthesize(question)
            if result is not None:
                self._active_answer = result.to_dict()
                await self._broadcast_answer()
        except Exception:
            logger.exception("Synthesis task failed")
            await self._broadcast_event({"type": "synthesis_error", "error": "Synthesis failed"})
        finally:
            self._synthesis_in_flight = False

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

    def _build_message(self, msg_type: str) -> dict:
        """Build a message payload from current buffer state."""
        segments = self.buffer.get_segments()
        msg = {
            "type": msg_type,
            "segments": [seg.to_dict() for seg in segments],
            "version": self.buffer.get_version(),
        }
        if self._extractor:
            msg["active_question"] = self._extractor.current_question
            msg["question_history"] = self._extractor.question_history
            msg["manual_question"] = self._extractor._manual_question is not None
        msg["synthesis_searching"] = self._synthesis_in_flight
        if self._active_answer:
            msg["active_answer"] = self._active_answer
        return msg
