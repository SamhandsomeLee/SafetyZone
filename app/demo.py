"""Offline pipeline demo CLI (Sprint 1.3)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline import run_video_file
from core.config import load_config
from detect.backend import create_backend


def _resolve_video_path(config_path: Path, video_arg: str | None) -> Path:
    if video_arg:
        return Path(video_arg)

    config = load_config(config_path)
    for cam in config.cameras:
        if cam.source_type == "video_file" and cam.path:
            return Path(cam.path)
    raise SystemExit("no --video and no video_file camera in config")


def main() -> int:
    parser = argparse.ArgumentParser(description="SafetyZone offline pipeline demo")
    parser.add_argument("--config", default="configs/config.example.json")
    parser.add_argument("--video", help="Video file path (overrides config camera path)")
    parser.add_argument("--engine", default="models/stock/yolov8s.engine")
    parser.add_argument("--station", help="Station id (default: first enabled)")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--quiet", action="store_true", help="Only print signal changes")
    args = parser.parse_args()

    config_path = Path(args.config)
    video_path = _resolve_video_path(config_path, args.video)
    if not video_path.is_file():
        print(f"ERROR: video not found: {video_path}", file=sys.stderr)
        return 1

    engine_path = Path(args.engine)
    if not engine_path.is_file():
        print(f"ERROR: engine not found: {engine_path}", file=sys.stderr)
        print("Run: bash tools/build_engine.sh", file=sys.stderr)
        return 1

    with create_backend("tensorrt", engine_path) as backend:
        backend.warmup(2)
        signals, runner = run_video_file(
            video_path=video_path,
            backend=backend,
            config=config_path,
            station_id=args.station,
            max_frames=args.max_frames,
            fps=args.fps,
        )

    print(f"station={runner.station.id} frames={len(signals)} video={video_path}")
    prev = object()
    for index, signal in enumerate(signals):
        if not args.quiet or signal != prev:
            print(f"frame={index:04d} signal={signal}")
        prev = signal

    if signals:
        print(f"final_signal={signals[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
