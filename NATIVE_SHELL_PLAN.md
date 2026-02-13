# UI-first Native Shell Plan (SwiftUI/AppKit) — Internal Tool

This document expands Issue #83 with an actionable plan and a concrete Phase 1 spike.

## Goal
Build an optional **native SwiftUI/AppKit shell** (HUD + Settings + menu bar) while **keeping the current Python backend** and **WebSocket protocol**.

This is for **internal distribution** (no Mac App Store constraints).

## Non-goals (initially)
- Rewriting ASR/RAG/synthesis in Swift
- Sandboxing/App Store entitlements

## Why UI-first
- Native window behaviors (true non-activating NSPanel HUD)
- Best-in-class HIG fit (NavigationSplitView settings, accessibility)
- Clean permission UX and fewer "webview quirks"

## Current backend contract
- WebSocket protocol documented in `PROTOCOL.md`
- Snapshot/update messages include `protocol_version: 1`

## Proposed repo layout
```
Meeting Buddy/
  backend/               # existing
  ingest/                # existing
  ui/                    # existing Tauri UI
  native/                # NEW
    MeetingBuddyShell/   # Xcode project directory
      MeetingBuddyShell.xcodeproj
      Sources/
```

## Phase 1 spike (2–4 days): “Minimal native HUD”

### Deliverable
A SwiftUI app that:
- opens a non-activating **NSPanel** HUD window
- connects to `ws://localhost:8765`
- renders:
  - transcript stream (simple)
  - active question
  - answer one-liner

### Acceptance criteria
- HUD stays on top without stealing focus from Zoom/Teams
- HUD updates live from backend snapshot/update
- If backend is not running, UI shows a clear offline state + retry

### Implementation checklist
1) **Create project**
   - Xcode: macOS App (SwiftUI)
   - Add a `WebSocketClient` service using `URLSessionWebSocketTask`

2) **NSPanel HUD window**
   - Create an `NSPanel` with:
     - `isFloatingPanel = true`
     - `level = .floating`
     - `collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]`
     - `styleMask` includes `.nonactivatingPanel` (key behavior)
     - `becomesKeyOnlyIfNeeded = true`
     - `isMovableByWindowBackground = true`
   - Wrap SwiftUI content via `NSHostingView`

3) **Data model mapping**
   - Define Codable structs for snapshot/update:
     - `protocol_version`, `version`, `segments`, `active_question`, `active_answer`...
   - Maintain last-received state in an `ObservableObject`

4) **Render minimal UI**
   - Transcript: last N sentences
   - Question: single line
   - Answer: one-liner

5) **Retry + offline UX**
   - If WS disconnects: show “Backend disconnected” + automatic reconnect

### Notes on permissions
The native shell does not change capture permissions; the backend + Swift AudioCapture still drive audio.

## Phase 2 (3–6 days): Native Settings window
- Use `NavigationSplitView` to implement:
  - General
  - Documents
  - OpenAI Account
- Reuse existing backend commands from `PROTOCOL.md`

## Phase 3 (2–4 days): Menu bar + hotkeys
- Menu bar item with actions
- Global shortcuts using Carbon/HotKey or a small helper library

## Packaging for internal distribution
Options:
- Keep backend as sidecar (current model)
- Bundle backend + venv into a single internal installer (DMG/zip + script)

## Go/No-go gates
- After Phase 1 spike: decide if native shell materially improves UX enough to justify continued investment.
