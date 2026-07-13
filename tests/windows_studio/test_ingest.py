"""Tests for windows_studio ingest (#40)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from windows_studio.ingest import IngestConfig, ingest_cases, list_cases, load_staged_cases
from windows_studio.ingest.source import discover_cases, is_rsync_source, parse_rsync_source


def _make_outbox(root: Path) -> None:
    (root / "case_a.jpg").write_bytes(b"fake-jpeg-a")
    (root / "case_a.txt").write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    (root / "case_b.png").write_bytes(b"fake-png-b")
    meta = {"reason": "low_confidence", "score": 0.31}
    (root / "case_b.json").write_text(json.dumps(meta), encoding="utf-8")


def test_discover_cases_local(tmp_path: Path) -> None:
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    _make_outbox(outbox)

    cases = discover_cases(outbox)
    assert len(cases) == 2
    ids = {c.case_id for c in cases}
    assert ids == {"case_a", "case_b"}

    case_a = next(c for c in cases if c.case_id == "case_a")
    assert case_a.has_labels
    assert case_a.label_path is not None

    case_b = next(c for c in cases if c.case_id == "case_b")
    assert not case_b.has_labels
    assert case_b.metadata["reason"] == "low_confidence"


def test_list_and_pull_local(tmp_path: Path) -> None:
    outbox = tmp_path / "remote_outbox"
    outbox.mkdir()
    _make_outbox(outbox)

    config = IngestConfig(source=str(outbox), staging_dir=tmp_path / "staging")
    listed = list_cases(config)
    assert len(listed) == 2

    pulled = ingest_cases(config)
    assert len(pulled) == 2
    assert (config.staging_dir / "outbox" / "case_a.jpg").is_file()
    assert (config.staging_dir / "ingest_manifest.json").is_file()

    staged = load_staged_cases(config.staging_dir)
    assert {c.case_id for c in staged} == {"case_a", "case_b"}


def test_rsync_source_parsing() -> None:
    assert is_rsync_source("rsync://jetson@192.168.1.10:/data/outbox")
    remote, path = parse_rsync_source("rsync://jetson@192.168.1.10:/data/outbox")
    assert remote == "jetson@192.168.1.10"
    assert path == "/data/outbox"

    with pytest.raises(ValueError):
        parse_rsync_source("/local/outbox")
