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

# Rebuild native SwiftUI settings app (sidecar for Cmd+,)
cd native/MeetingBuddySettings && swift build -c release
cp .build/release/MeetingBuddySettings \
   ../../ui/src-tauri/MeetingBuddySettings-aarch64-apple-darwin

# Rebuild native HUD overlay (SwiftUI sidecar)
cd native/MeetingBuddyHUD && swift build -c release
cp .build/release/MeetingBuddyHUD \
   ../../ui/src-tauri/MeetingBuddyHUD-aarch64-apple-darwin
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
| `backend/synthesis/engine.py` | LLM synthesis (API key or OAuth modes, streaming) |
| `backend/synthesis/prompt.py` | System/user prompts for synthesis |
| `backend/synthesis/prep.py` | Pre-meeting prep question generation |
| `backend/server/websocket.py` | Bidirectional WebSocket server (Q&A history, export, prep) |
| `backend/auth/oauth.py` | OpenAI OAuth token management |
| `backend/export/renderer.py` | Session export (Markdown/JSON) |
| `ingest/retriever.py` | Cosine similarity search over LanceDB |
| `ingest/project_manager.py` | Project CRUD, metadata.json per project |
| `ingest/parsers/url_parser.py` | Web URL fetching and HTML parsing |
| `ui/src/main.js` | WebSocket client, settings UI, file picker, prep mode, Q&A history |
| `ui/src/style.css` | Dark theme styles + confidence indicators |
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

## MANDATORY: Always plan before working

**Never start coding without a crystal-clear plan first.** This is a hard rule, no exceptions.

1. Read the GitHub issue
2. Explore the relevant code
3. Write out the full implementation plan (files to change, approach, edge cases)
4. Get user confirmation before touching any code

Starting to poke at code without a plan wastes tokens and produces nothing.

## Workflow Orchestration

### 1) Plan mode default
- Enter plan mode for any non-trivial task (3+ steps or architectural decisions)
- If something goes sideways: stop and re-plan immediately (don't keep pushing)
- Use plan mode for verification steps, not just building
- Write detailed specs up front to reduce ambiguity

### 2) Subagent strategy
- Use subagents liberally to keep the main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3) Self-improvement loop
- After any correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent repeating the same mistake
- Ruthlessly iterate until mistake rate drops
- Review `tasks/lessons.md` at session start for the relevant project

### 4) Verification before done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5) Demand elegance (balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: implement the elegant solution
- Skip for simple/obvious fixes (don't over-engineer)
- Challenge your own work before presenting it

### 6) Autonomous bug fixing
- When given a bug report: just fix it (don't ask for hand-holding)
- Point at logs, errors, failing tests, then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

Use `tasks/todo.md` and `tasks/lessons.md` (local only — `tasks/` is gitignored).

1. **Plan first:** write plan to `tasks/todo.md` with checkable items
2. **Verify plan:** check in before starting implementation
3. **Track progress:** mark items complete as you go
4. **Explain changes:** high-level summary at each step
5. **Document results:** add review section to `tasks/todo.md`
6. **Capture lessons:** update `tasks/lessons.md` after corrections

## Core Principles
- **Simplicity first:** Make every change as simple as possible. Minimal code impact.
- **No laziness:** Find root causes. No temporary fixes. Senior developer standards.
- **Minimal impact:** Changes should only touch what's necessary. Avoid introducing bugs.

## GitHub issue + PR workflow (required)

**Source of truth:** [CONTRIBUTING.md](CONTRIBUTING.md). When working on a GitHub issue:

1. **Before starting:** Set issue to `status:in-progress` and assign (or add agent label e.g. `agent:claw`).
2. **One issue per branch:** Use branch name like `feature/119-transcript-engine` or `fix/118-foo`.
3. **When opening a PR:** Move the issue to `status:review` (remove `status:ready` or `status:in-progress`, add `status:review`). PR title/body should reference and close the issue (e.g. "Closes #119").
4. **Do not** leave work merged-to-main without a PR; do not leave issues in `status:in-progress` after opening a PR.

```bash
gh issue edit <N> --remove-label "status:ready" --add-label "status:in-progress"   # when starting
gh issue edit <N> --remove-label "status:in-progress" --add-label "status:review"   # when PR open
```

## Feature Roadmap
See [docs/roadmap.md](docs/roadmap.md) (and GitHub Issues/labels) for the roadmap and current work queue.

High-level status:
- ✅ Phases **G–J** implemented
- ✅ Phase **UI** (macOS redesign) implemented
