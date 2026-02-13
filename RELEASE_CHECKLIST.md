# Release Checklist (macOS)

This checklist is meant to keep releases boring. Run it before cutting a new build or sharing a .app with someone.

## 0) Pre-flight
- [ ] You are on `main` and up-to-date (`git pull`)
- [ ] CI is green for the commit you’re releasing
- [ ] No uncommitted changes (`git status`)

## 1) Build prerequisites
- [ ] Python venv exists at repo root: `.venv/` (required by current sidecar runtime)
- [ ] AudioCapture helper builds:
  - [ ] `cd audio-capture && swift build -c release`
- [ ] UI dependencies installed:
  - [ ] `cd ui && npm ci`

## 2) Build the app bundle
- [ ] `cd ui && npm run tauri build`
- [ ] Confirm the bundle exists:
  - [ ] `ui/src-tauri/target/release/bundle/macos/Meeting Buddy.app`

## 3) Sidecar binaries present in the bundle
Verify the bundle includes required external binaries:
- [ ] `meeting-buddy-backend` (Python backend sidecar)
- [ ] `AudioCapture` (Swift ScreenCaptureKit helper)

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
- [ ] Transcript begins updating when system audio is playing
- [ ] Question detection changes the active question during a test call/video
- [ ] Answer card populates with:
  - [ ] one-liner
  - [ ] bullets
  - [ ] citations
- [ ] Export works (writes Markdown/JSON to disk)

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
- Backend sidecar currently expects a `.venv` directory at the project root at runtime.
- macOS permission checks can require an app restart to reflect the updated state.
