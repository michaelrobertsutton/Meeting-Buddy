from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from subprocess import CalledProcessError, check_output

logger = logging.getLogger(__name__)


def _git_short_sha() -> str:
    try:
        sha = check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
        return sha or "unknown"
    except (FileNotFoundError, CalledProcessError):
        return "unknown"


class CommandsMixin:
    """Command handler methods for TranscriptWebSocket.

    Extracted from websocket.py to reduce file size and isolate command
    implementations from the core server/broadcast infrastructure.
    All methods access ``self.*`` attributes defined in TranscriptWebSocket.__init__.
    """

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

    async def _cmd_set_listening(self, params: dict) -> dict:
        """Pause or resume listening (ASR + synthesis trigger)."""
        listening = params.get("listening", True)
        if not isinstance(listening, bool):
            listening = bool(listening)
        if self._listening == listening:
            return {"listening": self._listening}
        self._listening = listening
        if self._streaming:
            if self._listening:
                self._streaming.resume()
            else:
                self._streaming.pause()
        await self._broadcast_event({"type": "listening_update", "listening": self._listening})
        return {"listening": self._listening}

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
            except (FileNotFoundError, OSError):
                p["chunk_count"] = 0
            except Exception as e:
                logger.warning("Failed to get chunk count for project %s: %s", p.get("path"), e)
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
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                registry = {}
            except Exception as e:
                logger.warning("Failed to get doc registry for project %s: %s", active, e)
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
        # Clean up any previous login attempt still holding the port
        if self._login_server is not None:
            await self._login_server._cleanup()
            self._login_server = None
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
                self._synthesis_engine.set_retriever(retriever, project_slug=project_name)
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

