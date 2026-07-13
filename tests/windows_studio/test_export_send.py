"""Tests for windows_studio export_send (#44)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from windows_studio.export_send import ExportConfig, SendConfig, export_onnx, send_to_inbox


def test_export_dry_run(tmp_path: Path) -> None:
    weights = tmp_path / "best.pt"
    weights.write_text("# fake weights\n", encoding="utf-8")
    config = ExportConfig(weights_path=weights, export_dir=tmp_path / "export")
    result = export_onnx(config, force_dry_run=True)
    assert result.mode == "dry_run"
    assert result.onnx_path is not None
    assert result.onnx_path.suffix == ".onnx"
    assert result.onnx_path.is_file()


def test_send_local_inbox(tmp_path: Path) -> None:
    onnx = tmp_path / "model.onnx"
    onnx.write_bytes(b"fake-onnx")
    inbox = tmp_path / "inbox"
    config = SendConfig(onnx_path=onnx, inbox=str(inbox), sent_log_dir=tmp_path / "logs")
    result = send_to_inbox(config)
    assert result.mode == "local_copy"
    assert (inbox / "model.onnx").is_file()
    log_lines = (tmp_path / "logs" / "send_log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 1
    assert json.loads(log_lines[0])["sent_files"] == ["model.onnx"]


def test_send_rejects_non_onnx(tmp_path: Path) -> None:
    bad = tmp_path / "model.engine"
    bad.write_bytes(b"engine")
    config = SendConfig(onnx_path=bad, inbox=str(tmp_path / "inbox"))
    with pytest.raises(ValueError, match="ONNX only"):
        send_to_inbox(config)
