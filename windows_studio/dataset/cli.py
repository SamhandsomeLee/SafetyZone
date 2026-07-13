"""CLI for dataset build and overlap checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from windows_studio.dataset.split import (
    DatasetConfig,
    DatasetOverlapError,
    assert_no_overlap,
    build_dataset,
    find_overlaps,
    load_dataset_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SafetyZone studio dataset — train/test isolation")
    parser.add_argument("--review-dir", default="windows_studio_data/review")
    parser.add_argument("--dataset-dir", default="windows_studio_data/dataset")
    parser.add_argument("--test-ratio", type=float, default=0.0)
    parser.add_argument("--test-case", action="append", default=[], dest="test_cases")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="Build dataset from reviewed cases")
    check = sub.add_parser("check-overlap", help="Check train/test overlap only")
    check.add_argument("--train-images", type=Path)
    check.add_argument("--test-images", type=Path)
    sub.add_parser("show", help="Show dataset manifest")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "check-overlap":
        train = args.train_images or Path("windows_studio_data/dataset/train/images")
        test = args.test_images or Path("windows_studio_data/dataset/test/images")
        overlaps = find_overlaps(train, test)
        print(json.dumps({"overlaps": overlaps}, indent=2))
        return 1 if overlaps else 0

    if args.command == "show":
        manifest = load_dataset_manifest(Path(args.dataset_dir))
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0

    config = DatasetConfig(
        review_dir=Path(args.review_dir),
        dataset_dir=Path(args.dataset_dir),
        test_ratio=args.test_ratio,
        test_case_ids=frozenset(args.test_cases),
    )
    try:
        manifest = build_dataset(config)
    except DatasetOverlapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
