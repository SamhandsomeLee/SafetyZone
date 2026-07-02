#!/usr/bin/env python3
"""
Jetson YOLOv8s throughput benchmark (stock FP16 TensorRT engine).

Measures peak inference FPS on this board. Run after:
  bash tools/build_engine.sh

For best peak numbers (optional, requires sudo):
  sudo nvpmodel -m 0 && sudo jetson_clocks
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.postprocess import postprocess_yolo
from detect.backend import create_backend
from detect.letterbox import preprocess_bgr


@dataclass(frozen=True)
class LatencyStats:
    samples: int
    min_ms: float
    avg_ms: float
    max_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    fps: float


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[max(0, min(index, len(ordered) - 1))]


def _summarize(times_ms: list[float]) -> LatencyStats:
    avg = statistics.mean(times_ms)
    return LatencyStats(
        samples=len(times_ms),
        min_ms=min(times_ms),
        avg_ms=avg,
        max_ms=max(times_ms),
        p50_ms=_percentile(times_ms, 50),
        p90_ms=_percentile(times_ms, 90),
        p95_ms=_percentile(times_ms, 95),
        p99_ms=_percentile(times_ms, 99),
        fps=1000.0 / avg if avg > 0 else 0.0,
    )


def _load_frame(video: Path | None, image: Path | None) -> np.ndarray:
    import cv2

    if image is not None:
        frame = cv2.imread(str(image))
        if frame is None:
            raise FileNotFoundError(f"failed to read image: {image}")
        return frame

    video_path = video or Path("data/sample_videos/demo.mp4")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise FileNotFoundError(f"failed to open video: {video_path}")
    ok, frame = capture.read()
    capture.release()
    if not ok or frame is None:
        raise RuntimeError(f"failed to read frame from: {video_path}")
    return frame


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return None


def _gpu_freq_mhz() -> tuple[int | None, int | None]:
    gpu_paths = [
        Path("/sys/devices/platform/bus@0/17000000.gpu/devfreq/17000000.gpu"),
        Path("/sys/devices/17000000.ga10b/devfreq/17000000.ga10b"),
    ]
    for base in gpu_paths:
        cur = _read_text(base / "cur_freq")
        maxf = _read_text(base / "max_freq")
        if cur and maxf:
            return int(cur) // 1_000_000, int(maxf) // 1_000_000
    return None, None


def _power_mode() -> str:
    try:
        import subprocess

        result = subprocess.run(
            ["nvpmodel", "-q"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in (result.stdout + result.stderr).splitlines():
            if "NV Power Mode" in line:
                return line.split(":", 1)[-1].strip()
    except OSError:
        pass
    return "unknown"


def _print_stats(title: str, stats: LatencyStats) -> None:
    print(f"\n=== {title} ===")
    print(f"  samples : {stats.samples}")
    print(f"  latency : min={stats.min_ms:.2f}  avg={stats.avg_ms:.2f}  max={stats.max_ms:.2f} ms")
    print(f"  p50/p90/p95/p99 : {stats.p50_ms:.2f} / {stats.p90_ms:.2f} / {stats.p95_ms:.2f} / {stats.p99_ms:.2f} ms")
    print(f"  FPS (avg) : {stats.fps:.1f}")


def _bench_trt_only(backend, batch: np.ndarray, warmup: int, iters: int) -> LatencyStats:
    for _ in range(warmup):
        backend.infer_batch(batch)
    times: list[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        backend.infer_batch(batch)
        times.append((time.perf_counter() - t0) * 1000.0)
    return _summarize(times)


def _bench_infer_raw(backend, frame: np.ndarray, warmup: int, iters: int) -> LatencyStats:
    for _ in range(warmup):
        backend.infer_raw(frame)
    times: list[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        backend.infer_raw(frame)
        times.append((time.perf_counter() - t0) * 1000.0)
    return _summarize(times)


def _bench_infer_postprocess(
    backend,
    frame: np.ndarray,
    *,
    conf: float,
    nms_iou: float,
    min_area: float,
    warmup: int,
    iters: int,
) -> LatencyStats:
    for _ in range(warmup):
        raw = backend.infer_raw(frame)
        postprocess_yolo(raw, conf=conf, nms_iou=nms_iou, min_area=min_area, class_ids=(0,))
    times: list[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        raw = backend.infer_raw(frame)
        postprocess_yolo(raw, conf=conf, nms_iou=nms_iou, min_area=min_area, class_ids=(0,))
        times.append((time.perf_counter() - t0) * 1000.0)
    return _summarize(times)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark YOLOv8s FP16 TensorRT peak FPS on Jetson",
    )
    parser.add_argument("--engine", default="models/stock/yolov8s.engine")
    parser.add_argument("--video", type=Path, default=None, help="Video for test frame")
    parser.add_argument("--image", type=Path, default=None, help="Image for test frame")
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--iters", type=int, default=200)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--nms-iou", type=float, default=0.45)
    parser.add_argument("--min-area", type=float, default=400.0)
    parser.add_argument(
        "--mode",
        choices=("all", "trt", "infer", "postprocess"),
        default="all",
        help="all=three sections; trt=GPU only; infer=letterbox+TRT; postprocess=+NMS",
    )
    args = parser.parse_args()

    engine_path = Path(args.engine)
    if not engine_path.is_file():
        print(f"ERROR: engine not found: {engine_path}", file=sys.stderr)
        print("Run: bash tools/build_engine.sh", file=sys.stderr)
        return 1

    frame = _load_frame(args.video, args.image)
    h, w = frame.shape[:2]
    batch, _meta = preprocess_bgr(frame, input_size=640)

    cur_mhz, max_mhz = _gpu_freq_mhz()
    print("SafetyZone YOLOv8s Jetson benchmark")
    print(f"  engine   : {engine_path}")
    print(f"  frame    : {w}x{h} BGR")
    print(f"  input    : 640x640 letterbox → TRT FP16")
    print(f"  warmup   : {args.warmup}   iters: {args.iters}")
    print(f"  power    : {_power_mode()}")
    if cur_mhz is not None:
        print(f"  GPU freq : {cur_mhz} MHz (cap {max_mhz} MHz)")
    print("  tip      : sudo nvpmodel -m 0 && sudo jetson_clocks  for peak")

    with create_backend("tensorrt", engine_path) as backend:
        if args.mode in ("all", "trt"):
            stats = _bench_trt_only(backend, batch, args.warmup, args.iters)
            _print_stats("TRT only (GPU peak, preprocessed batch reused)", stats)

        if args.mode in ("all", "infer"):
            stats = _bench_infer_raw(backend, frame, args.warmup, args.iters)
            _print_stats("Letterbox + TRT (infer_raw)", stats)

        if args.mode in ("all", "postprocess"):
            stats = _bench_infer_postprocess(
                backend,
                frame,
                conf=args.conf,
                nms_iou=args.nms_iou,
                min_area=args.min_area,
                warmup=args.warmup,
                iters=args.iters,
            )
            _print_stats("Letterbox + TRT + postprocess (person NMS)", stats)

    print("\nNote: 'TRT only' is the usual upper bound for single-stream YOLOv8s on this board.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
