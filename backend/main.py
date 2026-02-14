import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from backend.asr.engine import ASREngine
from backend.asr.streaming import StreamingASR
from backend.asr.vad import VADFilter
from backend.audio.sck_capture import SCKCapture
from backend.auth.oauth import TokenManager
from backend.config import AppConfig
from backend.question.extractor import ActiveQuestionExtractor
from backend.server.websocket import TranscriptWebSocket
from backend.settings import SettingsManager
from backend.transcript.buffer import TranscriptBuffer

logger = logging.getLogger(__name__)

# Project root — env var (sidecar mode) or one level up from backend/
_PROJECT_ROOT = Path(os.environ["MEETINGBUDDY_PROJECT_ROOT"]) if os.environ.get("MEETINGBUDDY_PROJECT_ROOT") else Path(__file__).resolve().parent.parent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="meeting-buddy", description="Meeting Buddy backend")
    parser.add_argument(
        "--project",
        default=None,
        help="Project name for RAG retrieval (must be ingested first)",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Enable DEBUG logging for question extraction diagnostics
    logging.getLogger("backend.question.extractor").setLevel(logging.DEBUG)
    logging.getLogger("backend.server.websocket").setLevel(logging.DEBUG)

    args = _parse_args()
    config = AppConfig()
    settings = SettingsManager()
    token_manager = TokenManager()
    settings.set_token_manager(token_manager)

    # --- Resolve active project (CLI overrides saved setting) ---
    active_project = settings.get_active_project(args.project)

    # --- Resolve API key: OAuth tokens first, then saved key, then env var ---
    api_key = settings.get_api_key()
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    if token_manager.has_tokens():
        logger.info("OAuth tokens loaded — API key available")

    # --- Resolve AudioCapture binary path ---
    # Env var (set by sidecar script) overrides the default relative path
    env_binary = os.environ.get("MEETINGBUDDY_AUDIO_BINARY")
    if env_binary:
        binary_path = Path(env_binary)
    else:
        binary_path = _PROJECT_ROOT / config.audio.capture_binary
    if not binary_path.is_file():
        logger.error(
            "AudioCapture binary not found at %s.\n"
            "Build it with:  cd audio-capture && swift build -c release",
            binary_path,
        )
        sys.exit(1)

    # --- Initialize components ---
    logger.info("Initializing components...")

    transcript_buffer = TranscriptBuffer(config.transcript)

    def on_final(text: str, start_time: float, end_time: float) -> None:
        transcript_buffer.add_segment(text, start_time, end_time)
        print(f"  [{start_time:6.1f}s - {end_time:6.1f}s]  {text}")

    capture = SCKCapture(config.audio, str(binary_path))
    vad = VADFilter(config.vad, sample_rate=config.audio.target_sample_rate)
    engine = ASREngine(config.asr)
    streaming = StreamingASR(
        capture=capture,
        vad=vad,
        engine=engine,
        audio_config=config.audio,
        streaming_config=config.streaming,
        on_final=on_final,
    )
    extractor = ActiveQuestionExtractor(transcript_buffer, config.question)

    # --- Always create ProjectManager + IngestConfig (needed for WS commands) ---
    project_manager = None
    ingest_config = None
    try:
        from ingest.config import IngestConfig
        from ingest.project_manager import ProjectManager

        ingest_config = IngestConfig()
        project_manager = ProjectManager(ingest_config.project)
    except ImportError:
        logger.warning("Ingest package not available — project management disabled")

    # --- Optional: RAG retriever ---
    retriever = None
    if active_project and project_manager:
        try:
            from ingest.retriever import Retriever

            if not project_manager.project_exists(active_project):
                logger.warning("Project '%s' not found — RAG disabled", active_project)
            else:
                project_path = project_manager.get_project_path(active_project)
                retriever = Retriever(project_path, ingest_config)
                logger.info("RAG retriever loaded for project '%s'", active_project)
        except ImportError:
            logger.warning("Ingest package not available — RAG disabled")
        except Exception:
            logger.exception("Failed to initialize retriever")

    # --- Optional: Synthesis engine ---
    synthesis_engine = None
    if config.synthesis.enabled and (api_key or token_manager.has_tokens()):
        try:
            from backend.synthesis.engine import SynthesisEngine

            synthesis_engine = SynthesisEngine(config.synthesis, retriever=retriever)
            # If OAuth, route through ChatGPT backend (uses Plus/Pro subscription)
            if token_manager.has_tokens():
                account_id = token_manager.get_chatgpt_account_id()
                access_token = token_manager.get_api_key()
                if access_token and account_id:
                    synthesis_engine.reinit_client_oauth(access_token, account_id)
                    logger.info("Synthesis via ChatGPT backend (model=%s)", config.synthesis.model)
                else:
                    logger.warning("OAuth tokens present but missing account ID — falling back to API")
            else:
                logger.info("Synthesis engine enabled (model=%s)", config.synthesis.model)
        except ImportError:
            logger.warning("OpenAI package not available — synthesis disabled")
        except Exception:
            logger.exception("Failed to initialize synthesis engine")
    elif config.synthesis.enabled:
        logger.info("No API key configured — synthesis disabled (set via UI or OPENAI_API_KEY)")

    ws_server = TranscriptWebSocket(
        config.server, transcript_buffer, extractor,
        synthesis_engine=synthesis_engine,
        settings_manager=settings,
        project_manager=project_manager,
        ingest_config=ingest_config,
        token_manager=token_manager,
    )
    # Store capture reference for diagnostics
    ws_server._capture = capture

    # --- Start pipeline ---
    capture.start()
    streaming.start()

    print("\nCapturing system audio via ScreenCaptureKit.")
    print(f"WebSocket server at ws://{config.server.host}:{config.server.port}")
    if active_project:
        print(f"RAG project: {active_project}")
    if synthesis_engine:
        print(f"Synthesis: {config.synthesis.model}")
    elif not api_key:
        print("Synthesis: disabled (no API key — set via Settings panel)")
    print("Press Ctrl+C to stop.\n")

    # --- Run asyncio event loop (WebSocket server) in main thread ---
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    shutdown_event = asyncio.Event()

    def handle_signal() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    async def run() -> None:
        await ws_server.start()
        # Sentinel for Tauri: backend is listening and ready for connections.
        print("MEETING_BUDDY_READY", flush=True)
        await shutdown_event.wait()
        await ws_server.stop()

    try:
        loop.run_until_complete(run())
    finally:
        streaming.stop()
        capture.stop()
        loop.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
