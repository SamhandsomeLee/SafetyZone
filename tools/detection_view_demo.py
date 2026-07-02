#!/usr/bin/env python3
"""Real-time person detection demo with bounding boxes and safety zones."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline import StationRunner, resolve_station
from core.config import load_config
from core.postprocess import Detection
from core.zone import judge_zone, scale_polygon
from detect.backend import create_backend

SIGNAL_LABELS = {
    -1: ("SAFE", (80, 200, 80)),
    0: ("WARN", (0, 200, 255)),
    1: ("SLOW", (0, 180, 255)),
    2: ("STOP", (0, 0, 255)),
}


def _zone_color(zone: str | None) -> tuple[int, int, int]:
    if zone == "stop":
        return (0, 0, 255)
    if zone == "slow":
        return (0, 200, 255)
    return (0, 255, 0)


def _draw_zones(
    frame: np.ndarray,
    *,
    slow_polygon: list[list[float]],
    stop_polygon: list[list[float]],
    ref_size: tuple[int, int],
) -> None:
    import cv2

    frame_h, frame_w = frame.shape[:2]
    frame_size = (frame_w, frame_h)

    slow = scale_polygon(slow_polygon, ref_size, frame_size).astype(np.int32)
    stop = scale_polygon(stop_polygon, ref_size, frame_size).astype(np.int32)

    overlay = frame.copy()
    cv2.fillPoly(overlay, [slow], (0, 180, 255))
    cv2.fillPoly(overlay, [stop], (0, 0, 255))
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
    cv2.polylines(frame, [slow], True, (0, 200, 255), 2)
    cv2.polylines(frame, [stop], True, (0, 0, 255), 2)
    cv2.putText(frame, "SLOW", tuple(slow[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
    cv2.putText(frame, "STOP", tuple(stop[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)


def _draw_detection(
    frame: np.ndarray,
    det: Detection,
    *,
    slow_polygon: list[list[float]],
    stop_polygon: list[list[float]],
    ref_size: tuple[int, int],
    anchor_mode: str,
    min_overlap: float,
) -> None:
    import cv2

    frame_h, frame_w = frame.shape[:2]
    zone = judge_zone(
        det.as_box(),
        slow_polygon=slow_polygon,
        stop_polygon=stop_polygon,
        ref_size=ref_size,
        frame_size=(frame_w, frame_h),
        anchor_mode=anchor_mode,  # type: ignore[arg-type]
        min_overlap=min_overlap,
    )
    color = _zone_color(zone)
    x1, y1, x2, y2 = map(int, (det.x1, det.y1, det.x2, det.y2))
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    label = f"person {det.conf:.2f}"
    if zone:
        label += f" [{zone.upper()}]"
    cv2.putText(frame, label, (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


def _draw_hud(
    frame: np.ndarray,
    *,
    signal: int,
    frame_index: int,
    infer_ms: float,
    det_count: int,
    process_fps: float,
    fast: bool,
) -> None:
    import cv2

    label, color = SIGNAL_LABELS.get(signal, (str(signal), (255, 255, 255)))
    mode = "FAST" if fast else "REALTIME"
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 42), (20, 20, 20), -1)
    cv2.putText(
        frame,
        f"STOCK {mode}  signal={signal}({label})  f={frame_index}  "
        f"dets={det_count}  {infer_ms:.0f}ms  {process_fps:.1f}fps",
        (10, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        color,
        2,
    )


def _ensure_display() -> bool:
    """Use local X11 :0 when SSH session has no DISPLAY (common on Jetson)."""
    if os.environ.get("DISPLAY"):
        return True
    if Path("/tmp/.X11-unix/X0").exists():
        os.environ["DISPLAY"] = ":0"
        return True
    return False


def run_demo(
    *,
    video_path: Path,
    engine_path: Path,
    config_path: Path,
    station_id: str | None,
    display: bool,
    output: Path | None,
    max_frames: int | None,
    loop: bool,
    fast: bool,
) -> int:
    import cv2

    if not video_path.is_file():
        print(f"ERROR: video not found: {video_path}", file=sys.stderr)
        return 1
    if not engine_path.is_file():
        print(f"ERROR: engine not found: {engine_path}", file=sys.stderr)
        return 1

    config = load_config(config_path)
    station, param = resolve_station(config, station_id)
    runner = StationRunner(station=station, param=param)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        print(f"ERROR: failed to open video: {video_path}", file=sys.stderr)
        return 1

    src_fps = capture.get(cv2.CAP_PROP_FPS) or 15.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ref_size = (param.ref_width, param.ref_height)

    writer = None
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        record_fps = src_fps if not fast else 30.0
        writer = cv2.VideoWriter(
            str(output),
            cv2.VideoWriter_fourcc(*"mp4v"),
            record_fps,
            (width, height),
        )
        if not writer.isOpened():
            print(f"ERROR: failed to create output: {output}", file=sys.stderr)
            return 1

    window = "SafetyZone Detection Demo"
    if display:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window, min(1280, width), min(720, height))

    frame_index = 0
    frame_interval_ms = 1000.0 / src_fps if src_fps > 0 else 0.0
    wait_ms = 1 if fast else max(1, int(1000.0 / src_fps))

    print(f"video={video_path} ({width}x{height} @ {src_fps:.1f}fps source)")
    print(f"engine={engine_path} station={station.id}")
    print(f"mode={'FAST (max throughput)' if fast else 'REALTIME (sync to video fps)'}")
    print(f"display={'on' if display else 'off'} DISPLAY={os.environ.get('DISPLAY', '(unset)')}")
    if output:
        print(f"output={output}")
    if display:
        print("Press Q or Esc to quit.")

    run_t0 = time.perf_counter()
    process_fps = 0.0

    with create_backend("tensorrt", engine_path) as backend:
        backend.warmup(2)
        while max_frames is None or frame_index < max_frames:
            ok, frame = capture.read()
            if not ok or frame is None:
                if loop and frame_index > 0:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break

            t0 = time.perf_counter()
            signal, _zone, detections, _fault = runner.process(
                frame,
                backend=backend,
                frame_index=frame_index,
                timestamp_ms=frame_index * frame_interval_ms,
            )
            infer_ms = (time.perf_counter() - t0) * 1000.0

            vis = frame.copy()
            _draw_zones(
                vis,
                slow_polygon=param.slow_polygon,
                stop_polygon=param.stop_polygon,
                ref_size=ref_size,
            )
            for det in detections:
                _draw_detection(
                    vis,
                    det,
                    slow_polygon=param.slow_polygon,
                    stop_polygon=param.stop_polygon,
                    ref_size=ref_size,
                    anchor_mode=station.detect_mode,
                    min_overlap=param.min_overlap,
                )

            elapsed = time.perf_counter() - run_t0
            if elapsed > 0:
                process_fps = (frame_index + 1) / elapsed

            _draw_hud(
                vis,
                signal=signal,
                frame_index=frame_index,
                infer_ms=infer_ms,
                det_count=len(detections),
                process_fps=process_fps,
                fast=fast,
            )

            if writer is not None:
                writer.write(vis)
            if display:
                cv2.imshow(window, vis)
                key = cv2.waitKey(wait_ms) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    print(f"stopped at frame={frame_index}")
                    break

            frame_index += 1

    capture.release()
    if writer is not None:
        writer.release()
        print(f"saved {frame_index} frames -> {output}")
    if display:
        cv2.destroyAllWindows()

    total = time.perf_counter() - run_t0
    avg_fps = frame_index / total if total > 0 and frame_index else 0.0
    print(f"done frames={frame_index}  avg_process_fps={avg_fps:.1f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SafetyZone real-time detection view demo")
    parser.add_argument("--video", default="data/sample_videos/demo.mp4")
    parser.add_argument("--engine", default="models/stock/yolov8s.engine")
    parser.add_argument("--config", default="configs/config.example.json")
    parser.add_argument("--station", default=None)
    parser.add_argument("--output", type=Path, default=None, help="Optional: save annotated mp4")
    parser.add_argument("--no-display", action="store_true", help="Headless; save --output instead")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Max throughput: no fps throttle, HUD shows process FPS (recommended for peak preview)",
    )
    parser.add_argument("--loop", action="store_true", help="Loop video when end is reached")
    parser.add_argument("--max-frames", type=int, default=None)
    args = parser.parse_args()

    display = not args.no_display
    if display:
        display = _ensure_display()

    output = args.output
    if not display and output is None:
        output = Path("data/sample_videos/demo_annotated.mp4")
    if args.fast and args.output is None:
        output = None

    return run_demo(
        video_path=Path(args.video),
        engine_path=Path(args.engine),
        config_path=Path(args.config),
        station_id=args.station,
        display=display,
        output=output,
        max_frames=args.max_frames,
        loop=args.loop,
        fast=args.fast,
    )


if __name__ == "__main__":
    raise SystemExit(main())
