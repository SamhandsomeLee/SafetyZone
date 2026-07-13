"""Outbox source adapters: local directory and rsync."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from windows_studio.ingest.models import IMAGE_SUFFIXES, HardCase

logger = logging.getLogger(__name__)

RSYNC_PREFIX = "rsync://"


def is_rsync_source(source: str) -> bool:
    return source.startswith(RSYNC_PREFIX)


def parse_rsync_source(source: str) -> tuple[str, str]:
    """Parse ``rsync://user@host:/remote/outbox`` → (remote, remote_path)."""
    if not is_rsync_source(source):
        raise ValueError(f"not an rsync source: {source}")
    body = source[len(RSYNC_PREFIX) :]
    if ":" not in body:
        raise ValueError(f"invalid rsync source (missing path): {source}")
    remote, remote_path = body.split(":", 1)
    if not remote or not remote_path:
        raise ValueError(f"invalid rsync source: {source}")
    return remote, remote_path


def discover_cases(root: Path) -> list[HardCase]:
    """Scan *root* for image + optional sidecar ``.txt`` label files."""
    if not root.is_dir():
        raise FileNotFoundError(f"outbox directory not found: {root}")

    images = sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )
    cases: list[HardCase] = []
    for image_path in images:
        case_id = image_path.stem
        label_path = image_path.with_suffix(".txt")
        if not label_path.is_file():
            label_path = None
        meta_path = image_path.with_suffix(".json")
        metadata: dict = {}
        if meta_path.is_file():
            try:
                import json

                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 — surface as metadata fault flag
                metadata = {"_meta_error": str(exc)}
        cases.append(
            HardCase(
                case_id=case_id,
                image_path=image_path,
                label_path=label_path,
                metadata=metadata,
            )
        )
    return cases


def list_outbox_cases(source: str) -> list[HardCase]:
    """List hard cases at *source* without copying to staging."""
    if is_rsync_source(source):
        remote, remote_path = parse_rsync_source(source)
        # Dry listing via rsync --list-only when available; else require local mirror.
        result = subprocess.run(
            ["rsync", "--list-only", f"{remote}:{remote_path}/"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"rsync list failed ({result.returncode}): {result.stderr.strip() or result.stdout}"
            )
        return _cases_from_rsync_listing(result.stdout, remote, remote_path)
    return discover_cases(Path(source))


def _cases_from_rsync_listing(
    listing: str,
    remote: str,
    remote_path: str,
) -> list[HardCase]:
    """Build placeholder HardCase entries from ``rsync --list-only`` output."""
    cases: list[HardCase] = []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        name = parts[-1]
        if name in (".", "..", "./", "../"):
            continue
        path = Path(name)
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        remote_image = f"{remote}:{remote_path.rstrip('/')}/{name}"
        cases.append(
            HardCase(
                case_id=path.stem,
                image_path=Path(remote_image),
                label_path=Path(f"{remote}:{remote_path.rstrip('/')}/{path.stem}.txt"),
                metadata={"remote": True},
            )
        )
    return cases


def pull_outbox(source: str, staging_dir: Path) -> list[HardCase]:
    """Copy outbox contents into *staging_dir* and return discovered cases."""
    staging_dir.mkdir(parents=True, exist_ok=True)

    if is_rsync_source(source):
        remote, remote_path = parse_rsync_source(source)
        dest = staging_dir / "outbox"
        dest.mkdir(parents=True, exist_ok=True)
        cmd = [
            "rsync",
            "-av",
            "--include=*.jpg",
            "--include=*.jpeg",
            "--include=*.png",
            "--include=*.bmp",
            "--include=*.webp",
            "--include=*.txt",
            "--include=*.json",
            "--include=*/",
            "--exclude=*",
            f"{remote}:{remote_path.rstrip('/')}/",
            str(dest) + "/",
        ]
        logger.info("running rsync pull: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"rsync pull failed ({result.returncode}): {result.stderr.strip() or result.stdout}"
            )
        return discover_cases(dest)

    src = Path(source)
    dest = staging_dir / "outbox"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return discover_cases(dest)
