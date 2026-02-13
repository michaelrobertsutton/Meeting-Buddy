#!/usr/bin/env bash
# scripts/install.sh — sets up ~/.meeting-buddy/venv for end-user or dev
set -euo pipefail

INSTALL_DIR="${MEETINGBUDDY_INSTALL_DIR:-$HOME/.meeting-buddy}"
VENV="$INSTALL_DIR/venv"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Meeting Buddy — Installer"

PYTHON=$(command -v python3 || true)
[ -z "$PYTHON" ] && { echo "ERROR: python3 not found."; exit 1; }
echo "Python: $PYTHON ($($PYTHON --version))"

echo "Creating venv at $VENV..."
mkdir -p "$INSTALL_DIR"
"$PYTHON" -m venv "$VENV"

echo "Installing dependencies..."
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -e "$REPO_ROOT" -q

echo "Downloading Whisper model (tiny)..."
"$VENV/bin/python" -c "
from faster_whisper import WhisperModel
WhisperModel('tiny', compute_type='int8')
print('Model ready.')
"

echo ""
echo "Done. Grant Screen Recording permission to Meeting Buddy.app:"
echo "  System Settings → Privacy & Security → Screen Recording"
echo ""
echo "To use this venv with the app, either:"
echo "  - Launch Meeting Buddy.app (it will use $VENV if present), or"
echo "  - Set: export MEETINGBUDDY_VENV=$VENV"
