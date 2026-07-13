#!/usr/bin/env bash
# Production E2E dry-run smoke (#51) — wiring only; never claims M8/M9/M11 pass.
# Usage: from repo root → bash tools/e2e_production_dry_run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "== A1 MANIFEST format =="
python tools/check_testset_overlap.py --testset jetson_update/testset --manifest-only

echo "== A2 windows_studio wizard dry-run =="
python -m windows_studio.app --run

echo "== A3 build_engine --dry-run (if studio export placeholder exists) =="
shopt -s nullglob
onnx_candidates=(windows_studio_data/export/*.onnx)
if ((${#onnx_candidates[@]} > 0)); then
  mkdir -p /tmp/sz_e2e_smoke/candidates
  python -m jetson_update.build_engine \
    --onnx "${onnx_candidates[0]}" \
    --out /tmp/sz_e2e_smoke/candidates \
    --dry-run
else
  echo "[skip] no windows_studio_data/export/*.onnx — run A2 first or supply ONNX"
fi

echo "== A4 acceptance dry-run + empty-set reject =="
if [[ -f models/stock/yolov8s.engine ]]; then
  eng=models/stock/yolov8s.engine
else
  mkdir -p /tmp/sz_e2e_smoke
  eng=/tmp/sz_e2e_smoke/placeholder.engine
  : >"$eng"
  echo "[info] stock engine missing; using empty placeholder for CLI wiring"
fi
# dry-run: never production pass
python -m jetson_update.acceptance --engine "$eng" --testset jetson_update/testset --dry-run || true
# empty frames=[] should REJECT / hotswap forbidden
python -m jetson_update.acceptance --engine "$eng" --testset jetson_update/testset || true

echo "== A5 receiver --once =="
mkdir -p jetson_update/inbox
python -m jetson_update.receiver --once

echo "== A6 pytest update/hotswap wiring =="
python -m pytest tests/jetson_update/ tests/app/test_hotswap_wiring.py -q

echo
echo "Dry-run smoke finished. Fill docs/benchmarks/e2e_production_YYYYMMDD.md for board evidence."
echo "Do NOT mark M11 formal pass from this script alone."
