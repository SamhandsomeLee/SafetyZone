#!/usr/bin/env bash
# Launch SafetyZone PySide6 runtime UI on Jetson display :0.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DISPLAY="${DISPLAY:-:0}"
exec python3 "$ROOT/app/main.py" "$@"
