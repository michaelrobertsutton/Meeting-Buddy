#!/usr/bin/env bash
# scripts/build-release.sh — build Meeting Buddy.app (and optional DMG) in one command
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TAURI_DIR="$REPO/ui/src-tauri"

echo "==> [1/5] Build AudioCapture"
cd "$REPO/audio-capture" && swift build -c release
cp .build/release/AudioCapture "$TAURI_DIR/AudioCapture-aarch64-apple-darwin"

echo "==> [2/5] Build MeetingBuddyHUD"
cd "$REPO/native/MeetingBuddyHUD" && swift build -c release
cp .build/release/MeetingBuddyHUD "$TAURI_DIR/MeetingBuddyHUD-aarch64-apple-darwin"

echo "==> [3/5] Build MeetingBuddySettings"
cd "$REPO/native/MeetingBuddySettings" && swift build -c release
cp .build/release/MeetingBuddySettings "$TAURI_DIR/MeetingBuddySettings-aarch64-apple-darwin"

echo "==> [4/5] Tauri build"
cd "$REPO/ui" && npm ci && npm run tauri build

APP="$TAURI_DIR/target/release/bundle/macos/Meeting Buddy.app"
echo "==> [5/5] App: $APP"

echo "==> Stabilizing AudioCapture signing identity in app bundle"
codesign -f -s - --identifier com.meetingbuddy.overlay \
  "$APP/Contents/MacOS/AudioCapture"

# Optional: bundle backend source into .app Resources (for PYTHONPATH when using Resources/venv)
RESOURCES="$APP/Contents/Resources/src"
mkdir -p "$RESOURCES"
cp -r "$REPO/backend" "$RESOURCES/"
cp -r "$REPO/ingest" "$RESOURCES/"
cp "$REPO/pyproject.toml" "$RESOURCES/" 2>/dev/null || true

# Optional DMG
if command -v hdiutil &>/dev/null; then
    DMG="$REPO/dist/MeetingBuddy.dmg"
    mkdir -p "$REPO/dist" && rm -f "$DMG"
    hdiutil create -volname "Meeting Buddy" -srcfolder "$APP" -ov -format UDZO "$DMG"
    echo "==> DMG: $DMG"
fi
echo "Done."
