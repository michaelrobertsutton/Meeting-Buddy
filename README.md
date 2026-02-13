# Meeting Buddy

Local-first macOS meeting copilot. Captures system audio via ScreenCaptureKit, transcribes in real-time using Whisper, infers the active question, retrieves evidence from your documents (RAG), and displays an always-on-top overlay with bullet talking points and citations.

All audio and transcript data stays on your device. Only the active question + retrieved context is sent to OpenAI for synthesis.

## Features

- **Real-time transcription** — faster-whisper with Silero VAD, streaming to overlay
- **Active question inference** — heuristic extraction from rolling transcript buffer
- **Document RAG** — ingest PDF/DOCX/MD/HTML, embed with all-MiniLM-L6-v2, search via LanceDB
- **Bullet synthesis** — GPT-4o-mini generates evidence-backed talking points with citations
- **Always-on-top overlay** — Tauri window with dark theme, hotkeys, pin/unpin
- **Settings panel** — manage API key, projects, and document ingestion from the UI (no terminal needed)

## Prerequisites

- macOS 14+ (Apple Silicon recommended)
- Python 3.9+ with venv
- Rust (for Tauri UI): `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- Screen Recording permission for Terminal.app (System Settings > Privacy & Security > Screen Recording)

No virtual audio driver needed — Meeting Buddy uses ScreenCaptureKit to capture system audio directly.

## Installation

```bash
cd "Meeting Buddy"

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install backend + ingest dependencies
pip install -e .

# Build the Swift audio capture helper
cd audio-capture && swift build -c release && cd ..

# Install Tauri UI dependencies
cd ui && npm install && cd ..
```

The first run downloads the Whisper model (~500MB for `small`) — one-time only.

## Usage

### Quick start (UI manages everything)

```bash
source .venv/bin/activate

# Start the backend
python -m backend.main

# In another terminal — launch the overlay
cd ui && npm run tauri dev
```

Click the gear icon in the overlay to:
1. **Set your OpenAI API key** (required for synthesis)
2. **Create a project** and switch to it
3. **Add documents** via file picker — ingestion runs in the background with progress

### CLI fallback (power users)

```bash
# Start with a specific project (overrides saved setting)
python -m backend.main --project "my-project"

# Or set API key via environment
OPENAI_API_KEY=sk-... python -m backend.main --project "my-project"

# Ingest documents via CLI
python -m ingest create-project --name "my-project"
python -m ingest ingest --project "my-project" --path /path/to/docs/
python -m ingest list-docs --project "my-project"
```

## Hotkeys

| Shortcut | Action |
|----------|--------|
| `Cmd+Shift+M` | Toggle overlay visibility |
| `Cmd+Shift+P` | Pin/unpin output (freeze while you speak) |

## Configuration

Edit defaults in `backend/config.py`. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `model_size` | `"small"` | Whisper model (`tiny.en`, `base.en`, `small`, `medium`) |
| `compute_type` | `"int8"` | Quantization for CPU inference |
| `silence_duration_ms` | `300` | Silence before triggering transcription |
| `max_chunk_duration_s` | `5.0` | Max audio chunk length |

Settings like API key and active project persist in `~/.meeting-buddy/config.json`.

## Troubleshooting

**No transcript appearing**
- Ensure Screen Recording permission is granted to Terminal.app
- Play audio with clear speech (not just music)
- Check that `audio-capture/.build/release/AudioCapture` exists (build with `swift build -c release`)

**Transcription is slow**
- Switch to a smaller model: `model_size="tiny.en"` in `backend/config.py`

**Synthesis not working**
- Check that an OpenAI API key is configured (Settings panel or `OPENAI_API_KEY` env var)
- Check that a project is selected and has ingested documents

## Project Structure

```
Meeting Buddy/
├── backend/
│   ├── main.py              # Entry point (audio + ASR + WebSocket)
│   ├── config.py            # All configuration dataclasses
│   ├── settings.py          # Persistent settings (API key, project)
│   ├── audio/
│   │   ├── sck_capture.py   # ScreenCaptureKit audio capture
│   │   └── capture.py       # Legacy sounddevice capture (unused)
│   ├── asr/
│   │   ├── engine.py        # faster-whisper wrapper
│   │   ├── vad.py           # Silero VAD wrapper
│   │   └── streaming.py     # VAD -> ASR orchestrator
│   ├── transcript/
│   │   └── buffer.py        # Rolling transcript buffer
│   ├── question/
│   │   └── extractor.py     # Active question inference
│   ├── synthesis/
│   │   ├── engine.py        # OpenAI synthesis (GPT-4o-mini)
│   │   └── prompt.py        # System/user prompts
│   └── server/
│       └── websocket.py     # Bidirectional WebSocket server
├── audio-capture/
│   └── Sources/AudioCapture/main.swift  # Swift SCK helper
├── ingest/
│   ├── config.py            # Ingest configuration
│   ├── parsers/             # PDF, DOCX, MD, HTML parsers
│   ├── chunker.py           # Text chunking
│   ├── embedder.py          # Sentence-transformer embeddings
│   ├── store.py             # LanceDB vector store
│   ├── retriever.py         # Query-time retrieval
│   ├── pipeline.py          # Parse -> chunk -> embed -> store
│   ├── project_manager.py   # Project CRUD
│   └── __main__.py          # CLI entry point
└── ui/
    ├── index.html           # Overlay HTML (+ settings drawer)
    ├── src/
    │   ├── main.js          # WebSocket client, settings, file picker
    │   └── style.css        # Dark theme styles
    └── src-tauri/
        ├── src/lib.rs        # Tauri setup (hotkeys, dialog plugin)
        └── tauri.conf.json   # Window config (always-on-top, transparent)
```
