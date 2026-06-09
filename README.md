# Meeting Buddy

A local-first macOS meeting copilot. It listens to your system audio, transcribes in real time, figures out what question is on the table, searches your documents for relevant context, and surfaces bullet-point answers in a floating overlay — all without leaving the meeting.

Audio and transcripts never leave your machine. Only the inferred question and retrieved context go to OpenAI.

---

## What it does

- **Live transcription** — faster-whisper + Silero VAD, streams to the overlay as you talk
- **Question detection** — heuristically infers the active question from the rolling transcript
- **Document RAG** — ingest PDFs, DOCX, Markdown, HTML, or URLs; retrieval via LanceDB + MiniLM embeddings
- **Streaming answers** — GPT-4o-mini synthesizes evidence-backed talking points with citations, streamed in real time
- **Manual override** — type your own question if auto-detection misses it
- **Prep mode** — generate and answer likely questions before the meeting starts
- **Q&A history** — browse everything asked and answered in the current session
- **Export** — save the full session (transcript + Q&A) as Markdown or JSON

## Requirements

- macOS 14+ (Apple Silicon)
- Python 3.9+
- Rust (for the Tauri process manager): `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- Screen Recording permission — no virtual audio driver needed, it uses ScreenCaptureKit directly

## Setup

```bash
# Clone and enter the repo
cd Meeting-Buddy

# Python dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Swift audio helper
cd audio-capture && swift build -c release && cd ..

# UI dependencies
cd ui && npm install && cd ..
```

First run downloads the Whisper model (~500MB for `small`) once.

### Build the app bundle

```bash
bash scripts/build-release.sh
```

Produces `ui/src-tauri/target/release/bundle/macos/Meeting Buddy.app` (and a DMG if hdiutil is available).

Install:
```bash
rm -rf "/Applications/Meeting Buddy.app"
cp -r "ui/src-tauri/target/release/bundle/macos/Meeting Buddy.app" /Applications/
```

After first launch, grant **Screen Recording** permission to **Meeting Buddy** in System Settings → Privacy & Security → Screen Recording, then restart.

## Running in dev

**Fastest loop (native HUD only):**
```bash
# Terminal 1
source .venv/bin/activate && python -m backend.main

# Terminal 2
cd native/MeetingBuddyHUD && swift run
```

**Full stack (Tauri tray + global shortcuts):**
```bash
# Build sidecars once (or when they change)
cd native/MeetingBuddyHUD && swift build -c release
cp .build/release/MeetingBuddyHUD ../../ui/src-tauri/MeetingBuddyHUD-aarch64-apple-darwin
cd ../MeetingBuddySettings && swift build -c release
cp .build/release/MeetingBuddySettings ../../ui/src-tauri/MeetingBuddySettings-aarch64-apple-darwin
cd ../..

# Terminal 1
source .venv/bin/activate && python -m backend.main

# Terminal 2
cd ui && npm run tauri dev
```

## Document ingestion

```bash
python -m ingest create-project --name "my-project"
python -m ingest ingest --project "my-project" --path /path/to/docs/
python -m ingest ingest --project "my-project" --path https://example.com/article
python -m ingest list-docs --project "my-project"
```

Or use the Settings panel (Cmd+,) to manage projects and docs through the UI.

## Hotkeys

| Shortcut | Action |
|----------|--------|
| `Option+Space` | Toggle overlay |
| `Cmd+H` | Hide overlay |
| `Cmd+,` | Settings |
| `Cmd+K` | Clear session |
| `Cmd+Shift+P` | Pin/unpin output |

## Configuration

Key settings in `backend/config.py`:

| Setting | Default | Notes |
|---------|---------|-------|
| `model_size` | `"small"` | `tiny.en` is faster, `medium` is more accurate |
| `compute_type` | `"int8"` | Quantization level |
| `silence_duration_ms` | `300` | Pause that triggers transcription |
| `max_chunk_duration_s` | `5.0` | Max audio chunk length |

API key and active project persist in `~/.meeting-buddy/config.json`.

## Troubleshooting

**No transcript**
- Check Screen Recording permission is granted to the right app (Meeting Buddy for bundles, Terminal for dev)
- Make sure audio is actually playing — the VAD won't fire on silence
- Verify the Swift binary exists: `audio-capture/.build/release/AudioCapture`
- Restart after granting permissions

**Can't connect to ws://localhost:8765**
- The backend isn't running. Start it first: `source .venv/bin/activate && python -m backend.main`
- For the bundled app, if connection fails, the venv may not be found — copy `.venv` to `~/.meeting-buddy/venv` or run `bash scripts/install.sh`

**Synthesis not working**
- Set your OpenAI API key in Settings, or via `OPENAI_API_KEY` env var
- Make sure a project is selected and has documents ingested

**Transcription slow**
- Drop to `model_size = "tiny.en"` in `backend/config.py`

## Project layout

```
Meeting-Buddy/
├── backend/          # Python: audio, ASR, question detection, synthesis, WebSocket
├── audio-capture/    # Swift: ScreenCaptureKit audio helper (raw PCM → stdout)
├── ingest/           # Document pipeline: parse → chunk → embed → LanceDB
├── native/
│   ├── MeetingBuddyHUD/       # SwiftUI floating overlay
│   └── MeetingBuddySettings/  # SwiftUI settings app
└── ui/               # Tauri process manager (tray, hotkeys, sidecar lifecycle)
```

## License

MIT
