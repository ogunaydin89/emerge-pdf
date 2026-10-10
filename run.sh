#!/usr/bin/env bash
# ==============================================================================
# EmergePDF - Standalone Desktop Launcher
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# 1. Bootstrap environment if missing
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "📦 Initializing isolated Python environment for EmergePDF..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
fi

# 2. Launch PyQt6 Desktop Application
echo "📄 Launching EmergePDF..."
exec "$VENV_DIR/bin/python" "$SCRIPT_DIR/src/main.py" "$@"
