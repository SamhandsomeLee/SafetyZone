"""CLI entry for review_ui."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from windows_studio.ingest import load_staged_cases
from windows_studio.review_ui.editor import (
    load_review_manifest,
    review_cases_batch,
    review_cases_interactive,
    save_review_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SafetyZone studio review — edit pre-labels")
    parser.add_argument(
        "--staging-dir",
        default="windows_studio_data/ingest",
        help="Ingest staging directory with pulled cases",
    )
    parser.add_argument(
        "--review-dir",
        default="windows_studio_data/review",
        help="Directory for reviewed labels and manifest",
    )
    parser.add_argument(
        "--auto-confirm",
        action="store_true",
        help="Mark all cases confirmed without interactive prompts (dry-run)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List review manifest and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    review_dir = Path(args.review_dir)

    if args.list:
        items = load_review_manifest(review_dir)
        print(json.dumps([i.to_dict() for i in items], indent=2, ensure_ascii=False))
        return 0

    cases = load_staged_cases(Path(args.staging_dir))
    if not cases:
        print("ERROR: no staged cases; run ingest pull first", file=sys.stderr)
        return 1

    if args.auto_confirm:
        items = review_cases_batch(cases, review_dir)
    else:
        items = review_cases_interactive(cases, review_dir)

    save_review_manifest(review_dir, items)
    confirmed = sum(1 for i in items if i.confirmed)
    print(f"\nreviewed {len(items)} case(s), confirmed {confirmed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
