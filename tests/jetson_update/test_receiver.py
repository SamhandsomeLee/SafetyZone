"""Tests for inbox ONNX receiver (#47)."""

from __future__ import annotations

from pathlib import Path

from jetson_update.receiver import (
    list_pending_onnx,
    mark_processed,
    on_onnx_received,
    scan_once,
)


def test_scan_once_triggers_callback(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    onnx = inbox / "model.onnx"
    onnx.write_bytes(b"fake-onnx-bytes")

    seen: list[Path] = []

    def _cb(path: Path) -> None:
        seen.append(path)
        assert path.is_file()
        assert path.name == "model.onnx"

    handled = scan_once(inbox, callback=_cb, mark=True)
    assert len(handled) == 1
    assert seen == [handled[0].path]
    assert not onnx.exists()
    assert (inbox / "processed" / "model.onnx").is_file()


def test_repeat_scan_does_not_retrigger(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "model.onnx").write_bytes(b"fake-onnx")

    calls: list[str] = []
    scan_once(inbox, callback=lambda p: calls.append(p.name), mark=True)
    scan_once(inbox, callback=lambda p: calls.append(p.name), mark=True)
    assert calls == ["model.onnx"]


def test_bad_files_skipped(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "empty.onnx").write_bytes(b"")
    (inbox / "notes.txt").write_text("nope", encoding="utf-8")
    (inbox / "model.onnx.tmp").write_bytes(b"partial")
    (inbox / "good.onnx").write_bytes(b"ok")

    pending = list_pending_onnx(inbox)
    assert [p.path.name for p in pending] == ["good.onnx"]

    seen: list[str] = []
    scan_once(inbox, callback=lambda p: seen.append(p.name), mark=True)
    assert seen == ["good.onnx"]
    assert (inbox / "empty.onnx").is_file()
    assert (inbox / "notes.txt").is_file()
    assert (inbox / "model.onnx.tmp").is_file()


def test_done_marker_gate(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    waiting = inbox / "a.onnx"
    waiting.write_bytes(b"a")
    ready = inbox / "b.onnx"
    ready.write_bytes(b"b")
    (inbox / "b.onnx.done").write_text("", encoding="utf-8")

    pending = list_pending_onnx(inbox)
    assert [p.path.name for p in pending] == ["b.onnx"]

    scan_once(inbox, callback=lambda _p: None, mark=True)
    assert waiting.is_file()
    assert not ready.exists()
    assert (inbox / "processed" / "b.onnx").is_file()
    assert not (inbox / "b.onnx.done").exists()


def test_mark_processed_collision(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    processed = inbox / "processed"
    processed.mkdir(parents=True)
    (processed / "model.onnx").write_bytes(b"old")
    src = inbox / "model.onnx"
    src.write_bytes(b"new")
    dest = mark_processed(src, inbox=inbox)
    assert dest.name == "model_1.onnx"
    assert dest.read_bytes() == b"new"


def test_stub_callback_prints(tmp_path: Path, capsys) -> None:
    path = tmp_path / "x.onnx"
    path.write_bytes(b"x")
    on_onnx_received(path)
    out = capsys.readouterr().out
    assert "ONNX received" in out
    assert "x.onnx" in out
