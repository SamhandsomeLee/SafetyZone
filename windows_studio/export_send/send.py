"""Send ONNX artifacts to Jetson inbox (#44)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

RSYNC_PREFIX = "rsync://"
ALLOWED_SEND_SUFFIXES = frozenset({".onnx"})


@dataclass
class SendConfig:
    onnx_path: Path
    inbox: str
    """Local inbox directory or ``rsync://user@host:/path/inbox``."""

    sent_log_dir: Path = Path("windows_studio_data/export")

    def to_dict(self) -> dict:
        return {
            "onnx_path": str(self.onnx_path),
            "inbox": self.inbox,
            "sent_log_dir": str(self.sent_log_dir),
        }


@dataclass
class SendResult:
    mode: str
    destination: str
    sent_files: list[str]
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "destination": self.destination,
            "sent_files": list(self.sent_files),
            "message": self.message,
        }


def _is_rsync_target(target: str) -> bool:
    return target.startswith(RSYNC_PREFIX)


def _parse_rsync_target(target: str) -> tuple[str, str]:
    body = target[len(RSYNC_PREFIX) :]
    remote, remote_path = body.split(":", 1)
    return remote, remote_path


def _assert_onnx_only(path: Path) -> None:
    if path.suffix.lower() not in ALLOWED_SEND_SUFFIXES:
        raise ValueError(f"inbox send accepts ONNX only, got: {path.name}")
    if not path.is_file():
        raise FileNotFoundError(f"onnx file not found: {path}")


def send_to_inbox(config: SendConfig) -> SendResult:
    _assert_onnx_only(config.onnx_path)

    if _is_rsync_target(config.inbox):
        remote, remote_path = _parse_rsync_target(config.inbox)
        dest = f"{remote}:{remote_path.rstrip('/')}/"
        cmd = ["rsync", "-av", str(config.onnx_path), dest]
        logger.info("rsync send: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(
                f"rsync send failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout}"
            )
        result = SendResult(
            mode="rsync",
            destination=dest,
            sent_files=[config.onnx_path.name],
            message="ONNX sent via rsync",
        )
    else:
        inbox_dir = Path(config.inbox)
        inbox_dir.mkdir(parents=True, exist_ok=True)
        target = inbox_dir / config.onnx_path.name
        shutil.copy2(config.onnx_path, target)
        result = SendResult(
            mode="local_copy",
            destination=str(target),
            sent_files=[config.onnx_path.name],
            message="ONNX copied to local inbox",
        )

    config.sent_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = config.sent_log_dir / "send_log.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **result.to_dict(),
        "onnx_path": str(config.onnx_path),
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return result
