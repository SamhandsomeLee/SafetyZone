"""CLI for ONNX export and inbox send."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from windows_studio.export_send.export import ExportConfig, export_onnx
from windows_studio.export_send.send import SendConfig, send_to_inbox


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SafetyZone studio — export ONNX and send inbox")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="Export ONNX from .pt weights")
    export.add_argument("--weights", type=Path, required=True)
    export.add_argument("--export-dir", type=Path, default=Path("windows_studio_data/export"))
    export.add_argument("--dry-run", action="store_true")

    send = sub.add_parser("send", help="Send ONNX to Jetson inbox (local copy or rsync)")
    send.add_argument("--onnx", type=Path, required=True)
    send.add_argument(
        "--inbox",
        required=True,
        help="Local inbox dir or rsync://user@host:/path/inbox",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "export":
        config = ExportConfig(weights_path=args.weights, export_dir=args.export_dir)
        try:
            result = export_onnx(config, force_dry_run=args.dry_run)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0

    config = SendConfig(onnx_path=args.onnx, inbox=args.inbox)
    try:
        result = send_to_inbox(config)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
