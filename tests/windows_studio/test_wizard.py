"""Tests for windows_studio wizard (#45)."""

from __future__ import annotations

import json
from pathlib import Path

from windows_studio.wizard import WizardConfig, run_wizard


def test_wizard_dry_run_end_to_end(tmp_path: Path) -> None:
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    (outbox / "w.jpg").write_bytes(b"img")
    (outbox / "w.txt").write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")

    config = WizardConfig(
        workspace=tmp_path / "ws",
        outbox_source=str(outbox),
        inbox_target=str(tmp_path / "jetson_inbox"),
        dry_run=True,
    )
    result = run_wizard(config)
    assert result.success
    assert result.steps["ingest"]["case_count"] == 1
    assert result.steps["review"]["confirmed"] >= 1
    assert result.steps["train"]["mode"] == "dry_run"
    assert result.steps["export"]["mode"] == "dry_run"
    assert result.steps["send"]["mode"] == "local_copy"
    assert (tmp_path / "jetson_inbox").is_dir()
    assert any((tmp_path / "jetson_inbox").glob("*.onnx"))
    saved = json.loads((config.workspace / "wizard_result.json").read_text(encoding="utf-8"))
    assert saved["success"] is True
