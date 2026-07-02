#!/usr/bin/env bash
# Build TensorRT FP16 engine from a local ONNX file (fully offline on Jetson).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/models/stock}"
ONNX="${ONNX:-$OUT_DIR/yolov8s.onnx}"
ENGINE="${ENGINE:-$OUT_DIR/yolov8s.engine}"
TRTEXEC="${TRTEXEC:-/usr/src/tensorrt/bin/trtexec}"

if [[ ! -f "$ONNX" ]]; then
  echo "ERROR: ONNX not found: $ONNX" >&2
  echo "" >&2
  echo "Offline Jetson: copy ONNX from Win first, e.g.:" >&2
  echo "  scp yolov8s.onnx nvidia@<jetson-ip>:~/Desktop/SafetyZone/models/stock/" >&2
  exit 1
fi

if [[ ! -x "$TRTEXEC" ]]; then
  echo "ERROR: trtexec not found at $TRTEXEC" >&2
  exit 1
fi

mkdir -p "$(dirname "$ENGINE")"
echo "Building FP16 engine"
echo "  ONNX:   $ONNX"
echo "  ENGINE: $ENGINE"
echo "  TRT:    $TRTEXEC"

"$TRTEXEC" \
  --onnx="$ONNX" \
  --saveEngine="$ENGINE" \
  --fp16 \
  --skipInference

echo "Engine ready: $ENGINE"
