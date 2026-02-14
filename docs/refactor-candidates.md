# Refactor candidates

This is a lightweight backlog of code health opportunities discovered during ongoing UI-first migration. These are *not* required for feature delivery; track as separate issues/PRs when ready.

## High priority

1) **WebSocket message decoding (Swift)**
- Paths:
  - `native/MeetingBuddyHUD/Sources/MeetingBuddyHUD/WebSocketClient.swift`
  - `native/MeetingBuddyShell/Sources/MeetingBuddyShell/WebSocketClient.swift`
  - `native/MeetingBuddySettings/Sources/MeetingBuddySettings/WebSocketClient.swift`
- Rationale: duplicated client logic + mixed typed/Any decoding.
- Suggestion: extract a shared SwiftPM target (e.g., `MeetingBuddyProtocol`) with:
  - `BackendMessage` models
  - robust decode for `response.data`
  - command send/await helper

2) **Command naming consistency**
- Paths: `docs/protocol.md`, `backend/server/websocket.py`, native clients
- Rationale: UI elements previously referenced legacy names (`manual_question`, `set_manual_question`) vs current protocol (`set_question`).
- Suggestion: enforce a single source-of-truth command list in `docs/protocol.md` + add a small protocol test that validates the handler map contains the documented commands.

## Medium priority

3) **HUD state model split**
- Paths: `native/MeetingBuddyHUD/Sources/MeetingBuddyHUD/ContentView.swift`
- Rationale: ContentView currently contains multiple major UI components in one file.
- Suggestion: split into:
  - `HUDToolbarView.swift`
  - `TranscriptView.swift`
  - `SynthesisCardView.swift`
  - `HUDStatusBarView.swift`

4) **Backend broadcast payload shaping**
- Paths: `backend/server/websocket.py`
- Rationale: backend often includes full `segments` array even when not changed; can cause unnecessary UI churn.
- Suggestion: add a version/fingerprint field for transcript updates and/or only include segments when changed.

## Low priority

5) **CI tightening**
- Add `swift test` (when we have tests) and a rustfmt/clippy job if/when Rust code grows.

---

Last updated: 2026-02-14
