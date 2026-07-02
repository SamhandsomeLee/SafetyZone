#!/usr/bin/env python3
"""Jetson M2 smoke test: stock FP16 engine + trt_backend single-frame infer."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.postprocess import postprocess_yolo
from detect.backend import create_backend


def _load_image(path: Path) -> np.ndarray:
    import cv2

    image = cv2.imread(str(path))
    if image is None:
        raise FileNotFoundError(f"failed to read image: {path}")
    return image


def _load_video_frame(path: Path) -> np.ndarray:
    import cv2

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise FileNotFoundError(f"failed to open video: {path}")
    ok, frame = capture.read()
    capture.release()
    if not ok or frame is None:
        raise RuntimeError(f"failed to read frame from video: {path}")
    return frame


def _synthetic_person_frame() -> np.ndarray:
    """Fallback frame when no media is provided (sanity check only)."""
    frame = np.full((480, 640, 3), 180, dtype=np.uint8)
    frame[120:420, 220:420] = (90, 90, 90)
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description="SafetyZone Jetson TensorRT smoke test (M2)")
    parser.add_argument(
        "--engine",
        default="models/stock/yolov8s.engine",
        help="Path to TensorRT FP16 engine",
    )
    parser.add_argument("--image", type=Path, help="BGR image path")
    parser.add_argument("--video", type=Path, help="Video path (first frame)")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--nms-iou", type=float, default=0.45)
    parser.add_argument("--min-area", type=float, default=0.0)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--benchmark", type=int, default=0, help="Repeat infer N times for timing")
    args = parser.parse_args()

    engine_path = Path(args.engine)
    if not engine_path.is_file():
        print(f"ERROR: engine not found: {engine_path}", file=sys.stderr)
        print("Offline: bash tools/offline_check.sh", file=sys.stderr)
        print("  scp yolov8s.onnx -> models/stock/ then: bash tools/build_engine.sh", file=sys.stderr)
        return 1

    if args.image:
        frame = _load_image(args.image)
    elif args.video:
        frame = _load_video_frame(args.video)
    else:
        frame = _synthetic_person_frame()
        print("WARN: no --image/--video; using synthetic frame (person hit not guaranteed)")

    with create_backend("tensorrt", engine_path) as backend:
        backend.warmup(args.warmup)

        t0 = time.perf_counter()
        raw = backend.infer_raw(frame)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if args.benchmark > 0:
            start = time.perf_counter()
            for _ in range(args.benchmark):
                backend.infer_raw(frame)
            total = time.perf_counter() - start
            fps = args.benchmark / total if total > 0 else 0.0
            print(f"benchmark: {args.benchmark} runs, {fps:.1f} FPS")

        detections = postprocess_yolo(
            raw,
            conf=args.conf,
            nms_iou=args.nms_iou,
            min_area=args.min_area,
            class_ids=(0,),
        )

    print(f"engine: {engine_path}")
    print(f"input: {frame.shape[1]}x{frame.shape[0]} BGR")
    print(f"raw output shape: {tuple(raw.shape)} dtype={raw.dtype}")
    print(f"infer latency: {elapsed_ms:.1f} ms")
    print(f"person detections: {len(detections)}")
    for index, det in enumerate(detections[:5]):
        print(
            f"  [{index}] conf={det.conf:.3f} box="
            f"({det.x1:.0f},{det.y1:.0f},{det.x2:.0f},{det.y2:.0f})"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
