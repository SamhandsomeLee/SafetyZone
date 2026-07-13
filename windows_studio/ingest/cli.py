"""CLI for listing and pulling Jetson outbox hard cases."""

from __future__ import annotations

import argparse
import json
import sys

from windows_studio.ingest.models import IngestConfig
from windows_studio.ingest.service import ingest_cases, list_cases


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SafetyZone studio ingest — Jetson outbox")
    parser.add_argument(
        "--source",
        required=True,
        help="Local outbox directory or rsync://user@host:/path/outbox",
    )
    parser.add_argument(
        "--staging-dir",
        default="windows_studio_data/ingest",
        help="Local staging directory for pulled cases",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List hard cases at source (no copy)")
    sub.add_parser("pull", help="Pull hard cases into staging directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = IngestConfig(source=args.source, staging_dir=args.staging_dir)

    if args.command == "list":
        cases = list_cases(config)
    else:
        cases = ingest_cases(config)

    print(json.dumps([c.to_dict() for c in cases], indent=2, ensure_ascii=False))
    print(f"\n{len(cases)} case(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
