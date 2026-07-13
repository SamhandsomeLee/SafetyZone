"""CLI for LocalCuda training."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from windows_studio.train.trainer import TrainConfig, cuda_available, run_training


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SafetyZone studio train — LocalCuda YOLO fine-tune (dry-run without GPU)",
    )
    parser.add_argument("--dataset-dir", default="windows_studio_data/dataset")
    parser.add_argument("--runs-dir", default="windows_studio_data/runs")
    parser.add_argument("--base-model", default="yolov8s.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run even if CUDA present")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = TrainConfig(
        dataset_dir=Path(args.dataset_dir),
        runs_dir=Path(args.runs_dir),
        base_model=args.base_model,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=args.device,
    )

    print(f"cuda_available={cuda_available()}", file=sys.stderr)
    try:
        result = run_training(config, force_dry_run=args.dry_run)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    if result.mode == "dry_run":
        print(
            "NOTE: dry-run only — deploy on Windows GPU for real fine-tuning.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
