# Release Checklist (macOS)

This checklist is meant to keep releases boring. Run it before cutting a new build or sharing a .app with someone.

## 0) Pre-flight
- [ ] You are on `main` and up-to-date (`git pull`)
- [ ] CI is green for the commit you're releasing
- [ ] No uncommitted changes (`git status`)

## 1) Build

**Prerequisites:** Rust (rustup), Xcode CLT, Node 20+, Python 3.9+

1. Run: `bash scripts/build-release.sh`
2. App: `ui/src-tauri/target/release/bundle/macos/Meeting Buddy.app`
3. DMG (if hdiutil present): `dist/MeetingBuddy.dmg`

## 2) Fresh-machine install test

1. Copy `Meeting Buddy.app` to a machine without the repo (or use the DMG).
2. Run one-time setup: `bash scripts/install.sh` (from a clone that has `scripts/`, or document this step for users).
3. Launch the app — HUD should appear and backend should start (venv at `~/.meeting-buddy/venv`).
4. Verify: transcript updates, Cmd+, opens settings, Q&A works.
5. Open/close Settings repeatedly (gear, Cmd+,, tray) and confirm the same Settings instance is reused (no relaunch flash).

## 3) Sidecar binaries in the bundle

Verify the bundle includes:
- [ ] `meeting-buddy-backend` (Python backend sidecar script)
- [ ] `AudioCapture` (Swift ScreenCaptureKit helper)
- [ ] `MeetingBuddyHUD` (native HUD overlay executable)
- [ ] `MeetingBuddySettings` (native settings executable)

## 4) Permissions (most common failure mode)

In **System Settings → Privacy & Security**:

### Screen Recording
- [ ] Permission granted to **Meeting Buddy**
- [ ] If permission was just granted: quit + relaunch the app

### Microphone (optional)
- [ ] Permission granted if you intend to capture mic audio

## 5) Runtime sanity checks

Launch the app and confirm:
- [ ] HUD appears and remains always-on-top
- [ ] HUD toggles with `Option + Space`
- [ ] Settings opens with `Cmd + ,`
- [ ] Settings sidebar remains interactive after repeated open/close cycles
- [ ] Cmd+Tab / dock reopen while Settings is visible does not unexpectedly front HUD over Settings
- [ ] Transcript begins updating when system audio is playing
- [ ] Settings → Permissions → Screen Recording matches runtime capture behavior (audio active => granted)
- [ ] Question detection changes the active question during a test call/video
- [ ] Answer card populates with:
  - [ ] one-liner
  - [ ] bullets
  - [ ] citations
- [ ] Export works (writes Markdown/JSON to disk)
- [ ] **Synthesis cache hit**: ask the same question twice (or trigger the same detected question twice within a session). The second answer should appear immediately with no visible LLM latency. Confirm a `Cache hit` log line in the backend output.
- [ ] No duplicate stale processes after reopen cycles:
  - [ ] `pgrep -x MeetingBuddyHUD | wc -l` is `1`
  - [ ] `pgrep -x MeetingBuddySettings | wc -l` is `0` when settings closed, `1` when open

## 6) Document ingestion checks

- [ ] Create/switch project
- [ ] Add a local PDF/DOCX/MD/HTML document
- [ ] Add a URL document
- [ ] Verify doc list shows size + indexed status
- [ ] Ask a question that should retrieve content from the ingested doc

## 7) Packaging / distribution

- [ ] Install in `/Applications` (optional)
- [ ] Verify app launches from Spotlight / Finder

## 8) Rollback plan

- [ ] Keep the last known-good `.app` build available
- [ ] If release fails due to permissions: reset Screen Recording permission, relaunch

---

## Notes / Known constraints

- The backend sidecar looks for a Python venv in this order: `MEETINGBUDDY_VENV`, `~/.meeting-buddy/venv`, `Contents/Resources/venv`, or (in dev) `MEETINGBUDDY_PROJECT_ROOT/.venv`. Run `scripts/install.sh` to create `~/.meeting-buddy/venv` on a fresh machine.
- macOS permission checks can require an app restart to reflect the updated state.
