# MeetingBuddyShell (native SwiftUI shell)

This folder contains a **minimal SwiftUI/AppKit shell** to validate the Meeting Buddy WebSocket protocol and HUD behaviors.

## Open in Xcode
This is a **Swift Package Manager (SPM)** target.

- Open `native/MeetingBuddyShell/Package.swift` in Xcode
- Select the `MeetingBuddyShell` scheme
- Run

## Run backend + shell
1) Start backend:
```bash
cd <repo>
source .venv/bin/activate
python -m backend.main
```

2) Run the shell:
- In Xcode: Run `MeetingBuddyShell`
- Or via CLI:
```bash
cd native/MeetingBuddyShell
swift run MeetingBuddyShell
```

## What it demonstrates
- NSPanel HUD: `.nonactivatingPanel`, floating, movable by background
- WebSocket: connects to `ws://localhost:8765`
- Minimal rendering of transcript + active question + answer one-liner
- Reconnect attempts + visible connected/disconnected state

## Notes
- WebSocket protocol is documented in [docs/protocol.md](../../docs/protocol.md).
- `snapshot`/`update` include `protocol_version`.
