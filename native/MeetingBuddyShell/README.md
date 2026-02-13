# MeetingBuddyShell (Native SwiftUI shell) — Spike scaffold

This directory scaffolds the **Phase 1 spike** from `NATIVE_SHELL_PLAN.md` (Issue #83).

Goal: a native macOS SwiftUI/AppKit shell that opens a **non-activating NSPanel HUD** and connects to the existing backend WebSocket (`ws://localhost:8765`).

## Status
This is a **scaffold** only. It is intended to be opened/built with **Xcode**.

On this machine, `xcodebuild` is not available (Command Line Tools only). You can still commit this scaffold so the project can be completed on a machine with Xcode.

## How to use (on a Mac with Xcode)
1. Install Xcode (from App Store).
2. Create a new Xcode project:
   - macOS App (SwiftUI)
   - name: `MeetingBuddyShell`
3. Copy the Swift files from `Sources/MeetingBuddyShell/` into the Xcode target.
4. Ensure the app has network access (default is fine for localhost).
5. Run the Python backend separately:

```bash
cd <repo>
source .venv/bin/activate
python -m backend.main
```

6. Launch the SwiftUI app. It should connect and render snapshot/update.

## Notes
- WebSocket protocol is documented in `PROTOCOL.md`.
- Snapshot/update now includes `protocol_version`.
