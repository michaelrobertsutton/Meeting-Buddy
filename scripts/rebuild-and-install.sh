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
git pull

echo "==> Writing project_root pointer for sidecar…"
mkdir -p "$HOME/.meeting-buddy"
echo "$REPO_ROOT" > "$HOME/.meeting-buddy/project_root"

echo "==> Installing deps and building .app (this takes ~2 min)…"
cd "$REPO_ROOT/ui"
npm ci && npm run tauri build 2>&1

echo "==> Killing running instance (if any)…"
osascript -e 'quit app "Meeting Buddy"' 2>/dev/null || true
sleep 1

echo "==> Installing to /Applications…"
rm -rf "/Applications/$APP_NAME.app"
cp -r "$BUNDLE" "/Applications/$APP_NAME.app"

echo "==> Launching…"
open "/Applications/$APP_NAME.app"

echo ""
echo "✓ Done. Meeting Buddy installed and launched."
