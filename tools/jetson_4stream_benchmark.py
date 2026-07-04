#!/usr/bin/env python3
"""
4-stream YOLOv8s stress test (matches production: GPU serial, multi video sources).

Simulates up to 4 camera/video inputs sharing one TensorRT engine.

Examples:
  python3 tools/jetson_4stream_benchmark.py
  python3 tools/jetson_4stream_benchmark.py --streams 4 --duration 30
  python3 tools/jetson_4stream_benchmark.py --display --fast
  python3 tools/jetson_4stream_benchmark.py --target-fps 5 --duration 60
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline import scale_detections_to_frame
from core.postprocess import Detection, postprocess_yolo
from detect.backend import create_backend
from detect.draw import draw_person_boxes
from detect.letterbox import BatchBuffer, LetterboxMeta, preprocess_bgr_into


@dataclass
class StreamSlot:
    stream_id: int
    capture: object
    prep_buffer: BatchBuffer = field(default_factory=BatchBuffer)
    gpu_input: np.ndarray = field(init=False)
    infer_copy: np.ndarray = field(init=False)
    latest_frame: np.ndarray | None = None
    latest_meta: LetterboxMeta | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    frames_read: int = 0
    frames_inferred: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    last_det_count: int = 0

    def __post_init__(self) -> None:
        self.gpu_input = np.empty_like(self.prep_buffer.batch)
        self.infer_copy = np.empty_like(self.prep_buffer.batch)


def _ensure_display() -> bool:
    if os.environ.get("DISPLAY"):
        return True
    if Path("/tmp/.X11-unix/X0").exists():
        os.environ["DISPLAY"] = ":0"
        return True
    return False


def _open_captures(video: Path, streams: int, stagger: bool) -> list[object]:
    import cv2

    caps: list[object] = []
    for index in range(streams):
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            raise RuntimeError(f"failed to open video stream {index}: {video}")
        if stagger:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if total > streams:
                cap.set(cv2.CAP_PROP_POS_FRAMES, (index * total // streams) % total)
        caps.append(cap)
    return caps


def _capture_loop(slot: StreamSlot, stop: threading.Event) -> None:
    import cv2

    while not stop.is_set():
        ok, frame = slot.capture.read()
        if not ok:
            slot.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = slot.capture.read()
            if not ok:
                time.sleep(0.01)
                continue
        with slot.lock:
            meta = preprocess_bgr_into(frame, slot.prep_buffer)
            np.copyto(slot.gpu_input, slot.prep_buffer.batch)
            slot.latest_frame = frame
            slot.latest_meta = meta
            slot.frames_read += 1
        time.sleep(0.001)


def _infer_batch(
    backend,
    batch: np.ndarray,
    meta: LetterboxMeta | None,
    *,
    conf: float,
    nms_iou: float,
    min_area: float,
) -> tuple[int, list[Detection]]:
    raw = backend.infer_batch(batch)
    letterbox_dets = postprocess_yolo(
        raw,
        conf=conf,
        nms_iou=nms_iou,
        min_area=min_area,
        class_ids=(0,),
    )
    if meta is None:
        return len(letterbox_dets), []
    scaled = scale_detections_to_frame(letterbox_dets, meta)
    return len(scaled), scaled


def _draw_tile(
    frame: np.ndarray,
    stream_id: int,
    detections: list[Detection],
    infer_ms: float,
) -> np.ndarray:
    import cv2

    vis = frame.copy()
    draw_person_boxes(vis, detections, thickness=2)
    cv2.rectangle(vis, (0, 0), (vis.shape[1], 28), (20, 20, 20), -1)
    cv2.putText(
        vis,
        f"cam{stream_id}  dets={len(detections)}  {infer_ms:.0f}ms",
        (8, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 0),
        2,
    )
    return vis


def _build_grid(tiles: list[np.ndarray]) -> np.ndarray:
    import cv2

    if not tiles:
        raise ValueError("no tiles")
    h, w = tiles[0].shape[:2]
    resized = [cv2.resize(t, (w, h)) if t.shape[:2] != (h, w) else t for t in tiles]
    while len(resized) < 4:
        resized.append(np.zeros((h, w, 3), dtype=np.uint8))
    top = np.hstack(resized[:2])
    bottom = np.hstack(resized[2:4])
    return np.vstack([top, bottom])


def run_benchmark(
    *,
    video: Path,
    engine: Path,
    streams: int,
    duration: float,
    target_fps: float | None,
    fast: bool,
    display: bool,
    stagger: bool,
    conf: float,
    nms_iou: float,
    min_area: float,
) -> int:
    if not video.is_file():
        print(f"ERROR: video not found: {video}", file=sys.stderr)
        return 1
    if not engine.is_file():
        print(f"ERROR: engine not found: {engine}", file=sys.stderr)
        return 1
    if streams < 1 or streams > 4:
        print("ERROR: --streams must be 1..4", file=sys.stderr)
        return 1

    import cv2

    caps = _open_captures(video, streams, stagger)
    slots = [StreamSlot(stream_id=i, capture=caps[i]) for i in range(streams)]

    stop = threading.Event()
    readers = [
        threading.Thread(target=_capture_loop, args=(slot, stop), daemon=True, name=f"cap-{i}")
        for i, slot in enumerate(slots)
    ]
    for thread in readers:
        thread.start()

    per_stream_interval = (1.0 / target_fps) if target_fps and target_fps > 0 else 0.0
    next_due = [time.perf_counter() for _ in slots]

    window = "SafetyZone 4-Stream Test"
    if display:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window, 1280, 720)

    print("SafetyZone multi-stream YOLO stress test")
    print(f"  video    : {video}")
    print(f"  engine   : {engine}")
    print(f"  streams  : {streams}  (GPU serial round-robin, design-aligned)")
    print(f"  duration : {duration:.0f}s")
    if target_fps:
        print(f"  target   : {target_fps:.1f} FPS/stream  (~{target_fps * streams:.1f} infer/s total)")
    else:
        print(f"  mode     : {'FAST max throughput' if fast else 'continuous'}")
    print(f"  display  : {'on' if display else 'off'}")

    total_infers = 0
    missed_deadlines = 0
    all_latencies: list[float] = []
    run_t0 = time.perf_counter()
    deadline = run_t0 + duration

    with create_backend("tensorrt", engine) as backend:
        backend.warmup(3)
        while time.perf_counter() < deadline:
            loop_t0 = time.perf_counter()
            tiles: list[np.ndarray] = []

            for slot in slots:
                if target_fps:
                    now = time.perf_counter()
                    if now < next_due[slot.stream_id]:
                        continue
                    next_due[slot.stream_id] = now + per_stream_interval

                with slot.lock:
                    if slot.latest_frame is None:
                        continue
                    np.copyto(slot.infer_copy, slot.gpu_input)
                    frame = slot.latest_frame
                    meta = slot.latest_meta

                t0 = time.perf_counter()
                det_count, detections = _infer_batch(
                    backend,
                    slot.infer_copy,
                    meta,
                    conf=conf,
                    nms_iou=nms_iou,
                    min_area=min_area,
                )
                infer_ms = (time.perf_counter() - t0) * 1000.0

                slot.frames_inferred += 1
                slot.last_det_count = det_count
                slot.latencies_ms.append(infer_ms)
                all_latencies.append(infer_ms)
                total_infers += 1

                if target_fps and infer_ms > per_stream_interval * 1000.0:
                    missed_deadlines += 1

                if display and slot.stream_id < 4:
                    tiles.append(_draw_tile(frame, slot.stream_id, detections, infer_ms))

            if display and tiles:
                while len(tiles) < min(4, streams):
                    tiles.append(np.zeros_like(tiles[0]))
                grid = _build_grid(tiles[:4])
                cv2.rectangle(grid, (0, 0), (grid.shape[1], 36), (20, 20, 20), -1)
                elapsed = time.perf_counter() - run_t0
                agg_fps = total_infers / elapsed if elapsed > 0 else 0.0
                cv2.putText(
                    grid,
                    f"4-stream test  total_infer={total_infers}  agg={agg_fps:.1f} infer/s",
                    (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 220, 255),
                    2,
                )
                cv2.imshow(window, grid)
                wait_ms = 1 if fast else max(1, int(1000.0 / 15.0))
                key = cv2.waitKey(wait_ms) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    break

            if not fast and target_fps is None:
                time.sleep(0.001)

            if target_fps and (time.perf_counter() - loop_t0) < 0.001:
                time.sleep(0.001)

    stop.set()
    for cap in caps:
        cap.release()
    if display:
        cv2.destroyAllWindows()

    elapsed = time.perf_counter() - run_t0
    agg_fps = total_infers / elapsed if elapsed > 0 else 0.0

    print("\n=== Results ===")
    print(f"  wall time       : {elapsed:.1f}s")
    print(f"  total inferences: {total_infers}")
    print(f"  aggregate       : {agg_fps:.1f} infer/s")
    if all_latencies:
        print(
            f"  latency (all)   : avg={statistics.mean(all_latencies):.1f}ms  "
            f"p95={sorted(all_latencies)[int(len(all_latencies) * 0.95) - 1]:.1f}ms"
        )
    if target_fps:
        print(f"  missed deadlines: {missed_deadlines}  (infer slower than target per stream)")

    print("\n  Per stream:")
    for slot in slots:
        avg_ms = statistics.mean(slot.latencies_ms) if slot.latencies_ms else 0.0
        stream_fps = slot.frames_inferred / elapsed if elapsed > 0 else 0.0
        print(
            f"    cam{slot.stream_id}: inferred={slot.frames_inferred}  "
            f"{stream_fps:.2f} infer/s  avg={avg_ms:.1f}ms  reads={slot.frames_read}"
        )

    if target_fps:
        required = target_fps * streams
        ok = agg_fps >= required * 0.95
        print(f"\n  target total {required:.1f} infer/s -> {'PASS' if ok else 'FAIL'} ({agg_fps:.1f} infer/s)")
    elif streams == 4:
        # Bootstrap guidance: 4 streams @ 5 FPS each = 20 infer/s
        for label, need in (("5 FPS/stream", 20.0), ("3 FPS/stream", 12.0)):
            ok = agg_fps >= need * 0.95
            print(f"  vs {label} ({need:.0f} infer/s): {'OK' if ok else 'NO'}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="4-stream YOLOv8s Jetson stress test")
    parser.add_argument("--video", default="data/sample_videos/demo.mp4")
    parser.add_argument("--engine", default="models/stock/yolov8s.engine")
    parser.add_argument("--streams", type=int, default=4)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument(
        "--target-fps",
        type=float,
        default=None,
        help="Target infer FPS per stream (e.g. 5 → 20 infer/s for 4 streams)",
    )
    parser.add_argument("--fast", action="store_true", help="Max throughput (no target throttle)")
    parser.add_argument("--display", action="store_true", help="2x2 preview grid")
    parser.add_argument(
        "--stagger",
        action="store_true",
        help="Start each stream at a different frame offset",
    )
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--nms-iou", type=float, default=0.45)
    parser.add_argument("--min-area", type=float, default=400.0)
    args = parser.parse_args()

    display = args.display
    if display:
        display = _ensure_display()

    return run_benchmark(
        video=Path(args.video),
        engine=Path(args.engine),
        streams=args.streams,
        duration=args.duration,
        target_fps=args.target_fps,
        fast=args.fast or (args.target_fps is None and not args.display),
        display=display,
        stagger=args.stagger or args.streams > 1,
        conf=args.conf,
        nms_iou=args.nms_iou,
        min_area=args.min_area,
    )


if __name__ == "__main__":
    raise SystemExit(main())
