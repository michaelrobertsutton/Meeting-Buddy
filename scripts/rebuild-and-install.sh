#!/bin/bash
# rebuild-and-install.sh — Pull latest, rebuild .app, reinstall to /Applications
# Usage: bash scripts/rebuild-and-install.sh
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Meeting Buddy"
BUNDLE="$REPO_ROOT/ui/src-tauri/target/release/bundle/macos/$APP_NAME.app"

echo "==> Pulling latest main…"
cd "$REPO_ROOT"
git checkout main
git stash --include-untracked 2>/dev/null || true
git pull --rebase

echo "==> Writing project_root pointer for sidecar…"
mkdir -p "$HOME/.meeting-buddy"
echo "$REPO_ROOT" > "$HOME/.meeting-buddy/project_root"

echo "==> Rebuilding AudioCapture (Swift)…"
cd "$REPO_ROOT/audio-capture"
swift build -c release 2>&1
cp .build/release/AudioCapture "$REPO_ROOT/ui/src-tauri/AudioCapture-aarch64-apple-darwin"

echo "==> Rebuilding MeetingBuddyHUD (Swift)…"
cd "$REPO_ROOT/native/MeetingBuddyHUD"
swift build -c release 2>&1
cp .build/release/MeetingBuddyHUD "$REPO_ROOT/ui/src-tauri/MeetingBuddyHUD-aarch64-apple-darwin"

echo "==> Building .app bundle (this takes ~2 min)…"
cd "$REPO_ROOT/ui"
npm run tauri build 2>&1

echo "==> Killing running instance (if any)…"
osascript -e 'quit app "Meeting Buddy"' 2>/dev/null || true
killall "Meeting Buddy" 2>/dev/null || true
sleep 2

echo "==> Installing to /Applications…"
rm -rf "/Applications/$APP_NAME.app"
cp -r "$BUNDLE" "/Applications/$APP_NAME.app"

# Remove the build-output copy so Launch Services doesn't see two apps
# with the same bundle ID and create a duplicate Dock entry.
rm -rf "$BUNDLE"

echo "==> Launching…"
open "/Applications/$APP_NAME.app"

echo ""
echo "✓ Done. Meeting Buddy installed and launched."
