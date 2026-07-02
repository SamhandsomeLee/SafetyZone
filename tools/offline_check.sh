#!/usr/bin/env bash
# Report stock model assets and next step for Jetson M2 (Win scp → build engine).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STOCK="${1:-$ROOT/models/stock}"

ONNX="$STOCK/yolov8s.onnx"
ENGINE="$STOCK/yolov8s.engine"

echo "SafetyZone stock model check"
echo "  dir: $STOCK"
echo ""

_status() {
  local label="$1"
  local path="$2"
  if [[ -f "$path" ]]; then
    local size
    size="$(du -h "$path" | cut -f1)"
    echo "  [OK]   $label  ($size)  $path"
    return 0
  fi
  echo "  [MISS] $label  $path"
  return 1
}

have_onnx=0
have_engine=0
_status "yolov8s.onnx" "$ONNX" && have_onnx=1 || true
_status "yolov8s.engine" "$ENGINE" && have_engine=1 || true

echo ""
if [[ "$have_engine" -eq 1 ]]; then
  echo "Next: python tools/jetson_infer_smoke.py --engine $ENGINE [--image ...]"
elif [[ "$have_onnx" -eq 1 ]]; then
  echo "Next: bash tools/build_engine.sh"
else
  echo "Next (Win 本机 export + scp):"
  echo "  yolo export model=yolov8s.pt format=onnx imgsz=640 opset=18 simplify=True dynamic=False"
  echo "  scp yolov8s.onnx nvidia@<jetson-ip>:~/Desktop/SafetyZone/models/stock/"
fi
