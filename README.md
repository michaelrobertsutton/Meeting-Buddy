# Meeting Buddy

Local-first macOS meeting copilot. Captures system audio via ScreenCaptureKit, transcribes in real-time using Whisper, infers the active question, retrieves evidence from your documents (RAG), and displays an always-on-top overlay with bullet talking points and citations.

All audio and transcript data stays on your device. Only the active question + retrieved context is sent to OpenAI for synthesis.

## Features

### Core Capabilities
- **Real-time transcription** — faster-whisper with Silero VAD, streaming to overlay
- **Active question inference** — heuristic extraction from rolling transcript buffer
- **Document RAG** — ingest PDF/DOCX/MD/HTML/URLs, embed with all-MiniLM-L6-v2, search via LanceDB
- **Bullet synthesis** — GPT-4o-mini generates evidence-backed talking points with citations
- **Streaming answers** — see answers appear in real-time as they're generated
- **Confidence indicators** — color-coded borders (green/yellow/red) and low-confidence warnings

### Meeting Features
- **Manual question override** — type questions directly in the quick question input
- **Pre-meeting prep mode** — generate and answer questions before meetings start
- **Q&A history** — browse past questions and answers from the current session
- **Session export** — export transcripts and Q&A history as Markdown or JSON

### UI & Controls
- **Always-on-top overlay** — Tauri window with dark theme, hotkeys, pin/unpin
- **Settings panel** — manage API key (or OAuth), projects, and document ingestion from the UI
- **Question history** — ranked list of detected questions with staleness indicators

## Prerequisites

- macOS 14+ (Apple Silicon recommended)
- Python 3.9+ with venv
- Rust (for Tauri UI): `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- **Screen Recording permission**:
  - **Bundled app**: Grant permission to "Meeting Buddy" (System Settings > Privacy & Security > Screen Recording)
  - **Development mode**: Grant permission to Terminal.app (System Settings > Privacy & Security > Screen Recording)
  - You can open the relevant System Settings panes from **Meeting Buddy → Settings → Permissions**.

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

### Building and Installing the App Bundle

**Quick install (all-in-one command):**

```bash
# Replace with your actual project path
cd "/path/to/Meeting Buddy" && \
git checkout main && git pull origin main && \
source .venv/bin/activate && \
cd audio-capture && swift build -c release && cd .. && \
cd ui && npm run tauri build && cd .. && \
rm -rf "/Applications/Meeting Buddy.app" && \
cp -r "ui/src-tauri/target/release/bundle/macos/Meeting Buddy.app" /Applications/
```

Or if you're already in the project directory (or any subdirectory):

```bash
cd "$(git rev-parse --show-toplevel)" && \
git checkout main && git pull origin main && \
source .venv/bin/activate && \
cd audio-capture && swift build -c release && cd .. && \
cd ui && npm run tauri build && cd .. && \
rm -rf "/Applications/Meeting Buddy.app" && \
cp -r "ui/src-tauri/target/release/bundle/macos/Meeting Buddy.app" /Applications/
```

**Step-by-step (if you prefer):**

```bash
# Ensure you're in the project root with venv activated
source .venv/bin/activate

# Build the Swift audio capture helper (required for bundling)
cd audio-capture && swift build -c release && cd ..

# Build the Tauri app bundle
cd ui
npm run tauri build
cd ..
```

This creates a `.app` bundle at:
```
ui/src-tauri/target/release/bundle/macos/Meeting Buddy.app
```

Then install to Applications:

```bash
# Remove old version if it exists (optional)
rm -rf "/Applications/Meeting Buddy.app"

# Install new version
cp -r "ui/src-tauri/target/release/bundle/macos/Meeting Buddy.app" /Applications/
```

**Note:** The bundled app includes the Tauri UI overlay, Python backend as a sidecar, and AudioCapture Swift binary. The app bundle expects to find the project's `.venv` directory at runtime.

## Usage

### Running the Bundled App

If you've built and installed the app bundle:

1. **Launch "Meeting Buddy" from Applications** (or Spotlight)
2. The app will automatically start the backend and display the overlay
3. **Grant Screen Recording permission** when prompted — you must grant permission to **"Meeting Buddy"** (not Terminal.app) in System Settings > Privacy & Security > Screen Recording
4. **Restart the app** after granting permissions if audio capture doesn't work immediately

**Important:** Without Screen Recording permission, the app cannot capture audio and transcripts will not appear.

### Development Mode (Quick start)

```bash
source .venv/bin/activate

# Start the backend
python -m backend.main

# In another terminal — launch the overlay
cd ui && npm run tauri dev
```

Tip: Settings now opens in a **separate Settings window** (Cmd+,) with sidebar navigation.

Click the gear icon in the overlay to:
1. **Set your OpenAI API key** (or use OAuth with ChatGPT Plus) — required for synthesis
2. **Create a project** and switch to it
3. **Add documents**:
   - Use **Add Files** or **Add Folder** for local documents (PDF, DOCX, MD, HTML)
   - Paste a **URL** in the URL input field and click **Add URL** to ingest web content
   - Ingestion runs in the background with progress indicators

### Using the Overlay

**During meetings:**
- The overlay automatically detects questions from the transcript and generates answers
- Use the **quick question input** (top bar) to manually ask questions
- Click **"Auto"** to resume automatic question detection
- View **Q&A History** to see past questions and answers
- Answers show **confidence indicators**: green border (high), yellow (medium), red (low)

**Before meetings (Prep Mode):**
- Click **"Prep Mode"** in settings to generate prep questions
- Add custom prep questions and get answers immediately
- Switch back to meeting mode when ready

**After meetings:**
- Use **Export Session** to save transcript and Q&A history as Markdown or JSON

### CLI fallback (power users)

```bash
# Start with a specific project (overrides saved setting)
python -m backend.main --project "my-project"

# Or set API key via environment
OPENAI_API_KEY=sk-... python -m backend.main --project "my-project"

# Ingest documents via CLI
python -m ingest create-project --name "my-project"
python -m ingest ingest --project "my-project" --path /path/to/docs/
python -m ingest ingest --project "my-project" --path https://example.com/article  # URLs work too!
python -m ingest list-docs --project "my-project"
```

## Hotkeys

| Shortcut | Action |
|----------|--------|
| `Option+Space` | Toggle HUD visibility |
| `Cmd+,` | Open Settings |
| `Cmd+K` | Clear Session (UI reset) |
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
- **Bundled app**: Ensure Screen Recording permission is granted to **"Meeting Buddy"** (System Settings > Privacy & Security > Screen Recording)
- **Development mode**: Ensure Screen Recording permission is granted to **Terminal.app**
- Play audio with clear speech (not just music)
- Check that `audio-capture/.build/release/AudioCapture` exists (build with `swift build -c release`)
- Verify audio is actually playing (check system volume)
- Try restarting the app after granting permissions

**Cannot connect to the server (ws://localhost:8765)**
- The "server" is the local Python backend. If nothing is listening on `localhost:8765`, the backend did not start.
- **Bundled app**: launch **Meeting Buddy** from Applications (this starts the backend + tray). Then open HUD/Settings.
- **Dev**: start the backend manually: `source .venv/bin/activate && python -m backend.main`
- If you started the native HUD directly (`swift run`), it will try a best-effort backend launch, but the reliable path is running the backend yourself.

**Transcription is slow**
- Switch to a smaller model: `model_size="tiny.en"` in `backend/config.py`

**Synthesis not working**
- Check that an OpenAI API key is configured (Settings panel or `OPENAI_API_KEY` env var)
- Check that a project is selected and has ingested documents
- For OAuth mode: ensure you've logged in via the Settings panel

**URL ingestion failing**
- Check your internet connection
- Some sites may block automated requests — try a different URL
- Check backend logs for HTTP error codes

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
│   │   ├── engine.py        # OpenAI synthesis (GPT-4o-mini, streaming)
│   │   ├── prompt.py        # System/user prompts
│   │   └── prep.py          # Pre-meeting prep question generation
│   ├── auth/
│   │   ├── oauth.py         # OpenAI OAuth token management
│   │   └── login_server.py  # OAuth callback server
│   ├── export/
│   │   └── renderer.py      # Session export (Markdown/JSON)
│   └── server/
│       └── websocket.py     # Bidirectional WebSocket server
├── audio-capture/
│   └── Sources/AudioCapture/main.swift  # Swift SCK helper
├── ingest/
│   ├── config.py            # Ingest configuration
│   ├── parsers/             # PDF, DOCX, MD, HTML, URL parsers
│   │   ├── base.py          # Parser protocol
│   │   ├── pdf_parser.py
│   │   ├── docx_parser.py
│   │   ├── markdown_parser.py
│   │   ├── html_parser.py
│   │   ├── url_parser.py    # Web URL fetching & parsing
│   │   └── registry.py     # Parser selection
│   ├── chunker.py           # Text chunking
│   ├── embedder.py          # Sentence-transformer embeddings
│   ├── store.py             # LanceDB vector store
│   ├── retriever.py         # Query-time retrieval
│   ├── pipeline.py          # Parse -> chunk -> embed -> store
│   ├── project_manager.py   # Project CRUD
│   └── __main__.py          # CLI entry point
└── ui/
    ├── index.html           # Overlay HTML (+ settings drawer, Q&A history, prep mode)
    ├── src/
    │   ├── main.js          # WebSocket client, settings, file picker, prep mode
    │   └── style.css        # Dark theme styles + confidence indicators
    └── src-tauri/
        ├── src/lib.rs        # Tauri setup (hotkeys, dialog plugin)
        └── tauri.conf.json   # Window config (always-on-top, transparent)
```
