# CLAUDE.md — Meeting Buddy

## What This Project Is
Local-first macOS meeting copilot. Captures system audio via ScreenCaptureKit, transcribes in real-time with Whisper, infers the active question, retrieves evidence from ingested documents (RAG), and displays an always-on-top Tauri overlay with bullet talking points and citations.

## Quick Reference

### Running the App
```bash
source .venv/bin/activate
python -m backend.main                    # Start backend (audio + ASR + WebSocket)
cd ui && npm run tauri dev                # Start overlay UI (separate terminal)
```

### Building Components
```bash
cd audio-capture && swift build -c release   # Rebuild Swift audio helper
cd ui && npm run tauri dev                   # Dev mode (hot reload)
cd ui && npm run tauri build                 # Production build
```

### Ingest CLI
```bash
python -m ingest create-project --name "my-project"
python -m ingest ingest --project "my-project" --path /path/to/docs/
python -m ingest list-docs --project "my-project"
```

## Architecture

### Package Layout
- `backend/` — Python backend (audio, ASR, transcript, question detection, synthesis, WebSocket server)
- `audio-capture/` — Swift CLI that captures system audio via ScreenCaptureKit, outputs raw PCM to stdout
- `ingest/` — Document ingestion pipeline (parse, chunk, embed, store in LanceDB)
- `ui/` — Tauri 2.10 overlay app (Rust backend + HTML/CSS/JS frontend)

### Data Flow
```
System Audio → AudioCapture (Swift) → stdout pipe → SCKCapture (Python)
  → VAD (Silero) → ASR (faster-whisper) → TranscriptBuffer
  → ActiveQuestionExtractor → SynthesisEngine (OpenAI) → WebSocket → Tauri UI
                                    ↑
                              Retriever (LanceDB) ← Ingested docs
```

### Threading Model
- **Main thread**: asyncio event loop (WebSocket server, synthesis, broadcast)
- **SCK reader thread**: reads PCM from Swift subprocess stdout pipe
- **ASR background thread**: runs VAD + Whisper transcription

### Key Files
| File | Purpose |
|------|---------|
| `backend/main.py` | Entry point, wires all components |
| `backend/config.py` | All configuration dataclasses |
| `backend/settings.py` | Persistent settings (~/.meeting-buddy/config.json) |
| `backend/audio/sck_capture.py` | ScreenCaptureKit bridge (spawns Swift binary) |
| `backend/asr/streaming.py` | VAD → ASR state machine |
| `backend/question/extractor.py` | Heuristic active question detection |
| `backend/synthesis/engine.py` | LLM synthesis (API key or OAuth modes) |
| `backend/synthesis/prompt.py` | System/user prompts for synthesis |
| `backend/server/websocket.py` | Bidirectional WebSocket server |
| `backend/auth/oauth.py` | OpenAI OAuth token management |
| `ingest/retriever.py` | Cosine similarity search over LanceDB |
| `ingest/project_manager.py` | Project CRUD, metadata.json per project |
| `ui/src/main.js` | WebSocket client, settings UI, file picker |
| `ui/src/style.css` | Dark theme styles |
| `ui/src-tauri/src/lib.rs` | Tauri setup (hotkeys, dialog plugin) |

## Coding Conventions

### Python
- **Python 3.9.6** (system default) — always use `from __future__ import annotations` for modern type hints
- Use dataclasses for configuration; avoid Pydantic
- asyncio for server/synthesis; threading only for audio capture and ASR
- `websockets` 15.x asyncio API (`websockets.asyncio.server.serve`)
- Logging via stdlib `logging`, not print statements

### Swift (audio-capture)
- Swift CLI with `@main`-style entry point
- Output raw PCM to stdout, logs to stderr only
- Build: `swift build -c release`

### Tauri / Frontend
- Tauri 2.10 (NOT v1) — APIs and config format differ significantly
- `use tauri::Emitter;` required for `.emit()` calls in Rust
- Vanilla JS (no framework) — single `main.js` file
- `crate-type = ["lib"]` for desktop-only (NOT `["staticlib", "cdylib", "rlib"]` — causes 40+ min builds)
- `codegen-units = 256` in dev profile for fast iteration

### Data Storage
- Per-project data at `~/.meeting-buddy/projects/<slug>/`
- Each project has `metadata.json` and `lance/` (LanceDB vector store)
- App settings at `~/.meeting-buddy/config.json`
- OAuth tokens at `~/.meeting-buddy/oauth_tokens.json` (chmod 0o600)

## Common Pitfalls
- `pipe.read(n)` on macOS returns partial reads — always use exact-read loops for binary pipes
- LanceDB search must use `.metric("cosine")` — default L2 gives wrong scores for normalized embeddings
- LanceDB `to_pandas()` requires pandas — use `to_arrow()` instead
- Silero VAD v5+ requires specific window sizes (512, 1024, 1536 samples at 16kHz)
- `macOSPrivateApi` is NOT a valid top-level key in Tauri 2.x config
- ChatGPT Plus OAuth uses `chatgpt.com/backend-api/codex/responses`, NOT `api.openai.com/v1`

## Feature Roadmap
See `memory/FEATURE_PLAN.md` for the full roadmap. Phases G-J cover:
- G: Manual question override, pre-meeting prep mode, document context & priority
- H: Session Q&A history, transcript context in synthesis, streaming answers
- I: Quick-pin answers, URL ingestion, confidence styling
- J: Post-meeting export, smart question staleness
