"""Inbox ONNX receiver (#47).

Windows studio (#44) drops **only** ``.onnx`` into the Jetson inbox.
This module scans (or polls) that directory, validates candidates, invokes a
callback (stub for #48/#49 chain), and marks files processed so they are not
re-triggered.

Default inbox
-------------
``jetson_update/inbox/`` relative to the repo root (override with ``--inbox``).
Processed files move to ``<inbox>/processed/``.

Drop conventions (compatible with ``windows_studio.export_send.send``)
----------------------------------------------------------------------
- Ready artifact: non-empty ``*.onnx`` regular file at the inbox root.
- Optional atomic / complete marker: sibling ``<name>.onnx.done`` (empty ok).
  If **any** ``*.done`` exists in the inbox root, every ``.onnx`` must have a
  matching ``.done`` before it is accepted (partial rsync / rename staging).
- Skip: empty files, non-``.onnx``, names under ``processed/``, already marked
  ``*.onnx.processed``, and staging suffixes ``.tmp`` / ``.partial`` / ``.part``.

CLI
---
::

    PYTHONPATH=. python -m jetson_update.receiver --once
    PYTHONPATH=. python -m jetson_update.receiver --watch --interval 2
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_INBOX = Path("jetson_update/inbox")
PROCESSED_DIRNAME = "processed"
STAGING_SUFFIXES = (".tmp", ".partial", ".part")
DONE_SUFFIX = ".done"
PROCESSED_MARKER_SUFFIX = ".processed"

OnnxReceivedCallback = Callable[[Path], None]


@dataclass(frozen=True)
class PendingOnnx:
    """A validated inbox ONNX ready for the update pipeline."""

    path: Path
    """Absolute path to the ``.onnx`` file in the inbox root."""


def default_inbox_path(repo_root: Path | None = None) -> Path:
    """Return the default inbox directory (``jetson_update/inbox``)."""
    root = repo_root if repo_root is not None else Path.cwd()
    return (root / DEFAULT_INBOX).resolve()


def on_onnx_received(path: Path) -> None:
    """Stub callback for #48/#49: log that an ONNX was received."""
    logger.info("ONNX received (stub): %s", path)
    print(f"[jetson_update.receiver] ONNX received: {path}", flush=True)


def _is_staging_name(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(suf) for suf in STAGING_SUFFIXES)


def _done_marker_for(onnx_path: Path) -> Path:
    return Path(str(onnx_path) + DONE_SUFFIX)


def _processed_marker_for(onnx_path: Path) -> Path:
    return Path(str(onnx_path) + PROCESSED_MARKER_SUFFIX)


def _inbox_requires_done(inbox: Path) -> bool:
    return any(p.is_file() and p.name.endswith(DONE_SUFFIX) for p in inbox.iterdir())


def _is_valid_candidate(path: Path, *, require_done: bool) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() != ".onnx":
        return False
    if _is_staging_name(path.name):
        return False
    if path.stat().st_size <= 0:
        logger.warning("skip empty ONNX: %s", path)
        return False
    if _processed_marker_for(path).is_file():
        return False
    if require_done and not _done_marker_for(path).is_file():
        logger.debug("waiting for .done marker: %s", path.name)
        return False
    return True


def list_pending_onnx(inbox: Path) -> list[PendingOnnx]:
    """Return validated, not-yet-processed ``.onnx`` files in ``inbox`` root."""
    inbox = inbox.resolve()
    if not inbox.is_dir():
        return []

    require_done = _inbox_requires_done(inbox)
    pending: list[PendingOnnx] = []
    for child in sorted(inbox.iterdir(), key=lambda p: p.name):
        if child.name == PROCESSED_DIRNAME:
            continue
        if child.name.endswith(DONE_SUFFIX) or child.name.endswith(PROCESSED_MARKER_SUFFIX):
            continue
        if _is_valid_candidate(child, require_done=require_done):
            pending.append(PendingOnnx(path=child.resolve()))
    return pending


def mark_processed(path: Path, inbox: Path | None = None) -> Path:
    """Move ``path`` into ``<inbox>/processed/`` (and clean companion markers).

    Returns the destination path under ``processed/``.
    """
    src = path.resolve()
    inbox_dir = inbox.resolve() if inbox is not None else src.parent
    dest_dir = inbox_dir / PROCESSED_DIRNAME
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        n = 1
        while True:
            candidate = dest_dir / f"{stem}_{n}{suffix}"
            if not candidate.exists():
                dest = candidate
                break
            n += 1
    shutil.move(str(src), str(dest))

    done = _done_marker_for(src)
    if done.is_file():
        done.unlink(missing_ok=True)
    marker = _processed_marker_for(src)
    if marker.is_file():
        marker.unlink(missing_ok=True)
    # Keep a lightweight marker next to the moved file for idempotent scans.
    Path(str(dest) + PROCESSED_MARKER_SUFFIX).write_text("ok\n", encoding="utf-8")
    return dest


def scan_once(
    inbox: Path,
    *,
    callback: OnnxReceivedCallback | None = None,
    mark: bool = True,
) -> list[PendingOnnx]:
    """Scan inbox once, invoke ``callback`` for each pending ONNX, optionally mark.

    Returns the list of tasks that were handed to the callback (in scan order).
    """
    cb = callback if callback is not None else on_onnx_received
    inbox = inbox.resolve()
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / PROCESSED_DIRNAME).mkdir(parents=True, exist_ok=True)

    pending = list_pending_onnx(inbox)
    handled: list[PendingOnnx] = []
    for task in pending:
        logger.info("trigger pipeline for %s", task.path)
        cb(task.path)
        if mark:
            mark_processed(task.path, inbox=inbox)
        handled.append(task)
    return handled


def watch_inbox(
    inbox: Path,
    *,
    callback: OnnxReceivedCallback | None = None,
    interval_s: float = 2.0,
    mark: bool = True,
    stop_after: int | None = None,
) -> int:
    """Poll inbox until interrupted; return total number of triggered files.

    ``stop_after`` is for tests: stop after that many successful triggers.
    """
    total = 0
    logger.info(
        "watching inbox %s (interval=%.1fs); Ctrl+C to stop",
        inbox.resolve(),
        interval_s,
    )
    try:
        while True:
            handled = scan_once(inbox, callback=callback, mark=mark)
            total += len(handled)
            if stop_after is not None and total >= stop_after:
                return total
            time.sleep(interval_s)
    except KeyboardInterrupt:
        logger.info("watch stopped (%d file(s) triggered)", total)
        return total


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SafetyZone jetson_update — scan inbox for ONNX (#47)",
    )
    parser.add_argument(
        "--inbox",
        type=Path,
        default=None,
        help=f"Inbox directory (default: {DEFAULT_INBOX})",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--once",
        action="store_true",
        help="Single scan then exit",
    )
    mode.add_argument(
        "--watch",
        action="store_true",
        help="Poll inbox until Ctrl+C",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Watch poll interval in seconds (default: 2)",
    )
    parser.add_argument(
        "--no-mark",
        action="store_true",
        help="Do not move/mark processed files (debug)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="DEBUG logging",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    inbox = args.inbox if args.inbox is not None else default_inbox_path()
    mark = not args.no_mark

    if args.once:
        handled = scan_once(inbox, mark=mark)
        print(f"scan done: {len(handled)} file(s) triggered", flush=True)
        return 0

    watch_inbox(inbox, interval_s=args.interval, mark=mark)
    return 0


if __name__ == "__main__":
    sys.exit(main())
