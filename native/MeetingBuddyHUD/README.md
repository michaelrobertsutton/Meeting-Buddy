# MeetingBuddyHUD

Native SwiftUI/AppKit HUD overlay for Meeting Buddy.

## Features

- **Liquid Glass Window**: `NSPanel` with `NSVisualEffectView` (.hudWindow material) for true macOS translucency
- **Non-Activating Panel**: Does not steal keyboard focus from other apps
- **Global Hotkey**: Alt+Space toggles visibility
- **Always On Top**: Floats above all windows, works across Spaces and fullscreen
- **Draggable**: Drag from anywhere on the header
- **Position Persistence**: Remembers window position via UserDefaults

## Build

```bash
cd native/MeetingBuddyHUD
swift build -c release
```

The binary will be at `.build/release/MeetingBuddyHUD`.

## Design Tokens

| Token | Value |
|-------|-------|
| Accent Blue | `#60B6F2` |
| Text Primary | white |
| Text Secondary | white @ 70% |
| Glass Edge | white @ 10%, 0.5pt |
| Corner Radius | 12pt |
| Spacing Grid | 8pt |
| Margin | 16pt |
| Window Size | 420×700pt |

## Architecture

- `MeetingBuddyHUDApp.swift` — App entry point + AppDelegate
- `HUDPanel.swift` — NSPanel subclass + HUDPanelController
- `GlobalHotkey.swift` — Alt+Space registration
- `ContentView.swift` — Main UI (toolbar, transcript, answer card, status bar)
- `WebSocketClient.swift` — Backend connection (ws://localhost:8765)
- `Models.swift` — Data models for backend messages
- `AppTheme.swift` — Design tokens
