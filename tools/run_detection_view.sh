#!/usr/bin/env bash
# Launch real-time detection view on Jetson local display (HDMI / VNC :0).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DISPLAY="${DISPLAY:-:0}"
exec python3 "$ROOT/tools/detection_view_demo.py" --loop --fast "$@"
