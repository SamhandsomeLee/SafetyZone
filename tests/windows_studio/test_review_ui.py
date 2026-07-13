"""Tests for windows_studio review_ui (#41)."""

from __future__ import annotations

import json
from pathlib import Path

from windows_studio.ingest import HardCase
from windows_studio.review_ui import (
    MISSING_LABEL_HINT,
    apply_edit_command,
    build_review_queue,
    is_suspect_case,
    load_review_manifest,
    read_labels,
    review_cases_batch,
    write_labels,
)


def _case(case_id: str, tmp_path: Path, *, with_label: bool, reason: str = "") -> HardCase:
    image = tmp_path / f"{case_id}.jpg"
    image.write_bytes(b"img")
    label = None
    if with_label:
        label = tmp_path / f"{case_id}.txt"
        label.write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    meta = {"reason": reason} if reason else {}
    return HardCase(case_id=case_id, image_path=image, label_path=label, metadata=meta)


def test_is_suspect_case(tmp_path: Path) -> None:
    assert is_suspect_case(HardCase("a", Path("a.jpg"), metadata={"reason": "missed_detection"}))
    assert is_suspect_case(HardCase("b", Path("b.jpg"), metadata={"score": 0.2}))
    assert is_suspect_case(HardCase("c", Path("c.jpg"), label_path=None))
    label = tmp_path / "d.txt"
    label.write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    assert not is_suspect_case(
        HardCase("d", tmp_path / "d.jpg", label_path=label, metadata={"reason": "ok"})
    )


def test_edit_confirm_add_del(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    cases = [_case("person_a", tmp_path, with_label=True)]
    items = build_review_queue(cases, review_dir)
    item = items[0]

    assert len(item.boxes) == 1
    err = apply_edit_command(item, "add 0 0.1 0.2 0.3 0.4")
    assert err is None
    assert len(item.boxes) == 2

    err = apply_edit_command(item, "edit 0 0 0.55 0.55 0.25 0.35")
    assert err is None
    assert item.boxes[0].cx == 0.55

    err = apply_edit_command(item, "del 1")
    assert err is None
    assert len(item.boxes) == 1

    err = apply_edit_command(item, "confirm")
    assert err is None
    assert item.confirmed

    write_labels(item.label_path, item.boxes)
    reloaded = read_labels(item.label_path)
    assert len(reloaded) == 1
    assert "宁可多标" in MISSING_LABEL_HINT


def test_batch_review_manifest(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    cases = [
        _case("a", tmp_path, with_label=True),
        _case("b", tmp_path, with_label=False, reason="missed_detection"),
    ]
    commands = {
        "b": ["add 0 0.5 0.5 0.2 0.3", "confirm"],
        "a": ["confirm"],
    }
    items = review_cases_batch(cases, review_dir, commands=commands)
    assert all(i.confirmed for i in items)
    assert items[1].suspect

    loaded = load_review_manifest(review_dir)
    assert len(loaded) == 2
    manifest = json.loads((review_dir / "review_manifest.json").read_text(encoding="utf-8"))
    assert manifest[0]["box_count"] >= 1
