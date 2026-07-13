#!/usr/bin/env python3
"""Validate frozen testset MANIFEST and optional train↔testset overlap (#46)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python tools/check_testset_overlap.py` from repo root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from jetson_update.testset.manifest import ManifestError, load_manifest
from jetson_update.testset.overlap import FrozenTestsetOverlapError, assert_no_overlap_with_train


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate jetson_update/testset MANIFEST and check train overlap.",
    )
    parser.add_argument(
        "--testset",
        type=Path,
        default=_ROOT / "jetson_update" / "testset",
        help="Frozen testset directory (contains MANIFEST.json)",
    )
    parser.add_argument(
        "--train",
        type=Path,
        default=None,
        help="Training images directory to check for content overlap",
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Only validate MANIFEST schema (empty frames OK)",
    )
    parser.add_argument(
        "--require-files",
        action="store_true",
        help="Require each MANIFEST frame image/label to exist on disk",
    )
    args = parser.parse_args(argv)

    testset = args.testset.resolve()
    try:
        manifest = load_manifest(testset, require_files=args.require_files)
    except ManifestError as exc:
        print(f"[FAIL] MANIFEST: {exc}", file=sys.stderr)
        return 1

    print(
        f"[OK] MANIFEST schema_version={manifest.schema_version} "
        f"frames={manifest.frame_count} locked={manifest.locked} "
        f"never_train={manifest.never_train}"
    )

    if args.manifest_only and args.train is None:
        return 0

    if args.train is None:
        if args.manifest_only:
            return 0
        print(
            "[FAIL] provide --train DIR for overlap check, or pass --manifest-only",
            file=sys.stderr,
        )
        return 2

    train = args.train.resolve()
    if not train.is_dir():
        print(f"[FAIL] train directory not found: {train}", file=sys.stderr)
        return 1

    try:
        assert_no_overlap_with_train(train, testset)
    except FrozenTestsetOverlapError as exc:
        print(f"[FAIL] overlap: {exc}", file=sys.stderr)
        for item in exc.overlaps:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(f"[OK] no overlap between train={train} and testset={testset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
