"""Tests for jetson_update.build_engine (#48)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jetson_update.build_engine import (
    DRY_RUN_MARKER,
    BuildEngineError,
    TrtexecNotFoundError,
    build_engine,
    engine_path_for,
    make_build_callback,
    main,
    resolve_trtexec,
    trtexec_command,
)


def test_trtexec_command_matches_shell_style(tmp_path: Path) -> None:
    onnx = tmp_path / "m.onnx"
    engine = tmp_path / "m.engine"
    trt = Path("/usr/src/tensorrt/bin/trtexec")
    cmd = trtexec_command(onnx, engine, trtexec=trt, fp16=True)
    assert cmd == [
        str(trt),
        f"--onnx={onnx}",
        f"--saveEngine={engine}",
        "--fp16",
        "--skipInference",
    ]


def test_dry_run_writes_placeholder(tmp_path: Path) -> None:
    onnx = tmp_path / "cand.onnx"
    onnx.write_bytes(b"fake-onnx")
    out = tmp_path / "candidates"
    engine = build_engine(onnx, out_dir=out, dry_run=True)
    assert engine == out / "cand.engine"
    assert engine.is_file()
    assert engine.read_text(encoding="utf-8") == DRY_RUN_MARKER


def test_missing_onnx_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="ONNX not found"):
        build_engine(tmp_path / "missing.onnx", out_dir=tmp_path, dry_run=True)


def test_no_trtexec_clear_error(tmp_path: Path) -> None:
    onnx = tmp_path / "m.onnx"
    onnx.write_bytes(b"x")
    with patch("jetson_update.build_engine.resolve_trtexec", return_value=None):
        with pytest.raises(TrtexecNotFoundError, match="trtexec not found"):
            build_engine(onnx, out_dir=tmp_path, dry_run=False)


def test_build_engine_mocked_subprocess(tmp_path: Path) -> None:
    onnx = tmp_path / "model.onnx"
    onnx.write_bytes(b"onnx-bytes")
    out = tmp_path / "out"
    fake_trt = tmp_path / "trtexec"
    fake_trt.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_trt.chmod(0o755)

    def _fake_run(cmd, **_kwargs):  # type: ignore[no-untyped-def]
        # Simulate trtexec writing the engine.
        save = next(a for a in cmd if a.startswith("--saveEngine="))
        Path(save.split("=", 1)[1]).write_bytes(b"fake-engine")
        return MagicMock(returncode=0, stdout="ok", stderr="")

    with patch("jetson_update.build_engine.subprocess.run", side_effect=_fake_run):
        engine = build_engine(
            onnx,
            out_dir=out,
            dry_run=False,
            trtexec=fake_trt,
        )
    assert engine == out / "model.engine"
    assert engine.read_bytes() == b"fake-engine"


def test_build_engine_nonzero_exit(tmp_path: Path) -> None:
    onnx = tmp_path / "model.onnx"
    onnx.write_bytes(b"onnx")
    fake_trt = tmp_path / "trtexec"
    fake_trt.write_text("x", encoding="utf-8")
    fake_trt.chmod(0o755)

    with patch(
        "jetson_update.build_engine.subprocess.run",
        return_value=MagicMock(returncode=1, stdout="", stderr="boom"),
    ):
        with pytest.raises(BuildEngineError, match="trtexec failed"):
            build_engine(onnx, out_dir=tmp_path, trtexec=fake_trt)


def test_make_build_callback_dry_run(tmp_path: Path) -> None:
    onnx = tmp_path / "inbox_model.onnx"
    onnx.write_bytes(b"onnx")
    out = tmp_path / "candidates"
    cb = make_build_callback(out_dir=out, dry_run=True)
    cb(onnx)
    assert (out / "inbox_model.engine").is_file()


def test_cli_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    onnx = tmp_path / "cli.onnx"
    onnx.write_bytes(b"onnx")
    out = tmp_path / "engines"
    rc = main(["--onnx", str(onnx), "--out", str(out), "--dry-run"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "dry-run" in captured.out
    assert (out / "cli.engine").is_file()


def test_cli_missing_onnx(tmp_path: Path) -> None:
    rc = main(["--onnx", str(tmp_path / "nope.onnx"), "--dry-run"])
    assert rc == 1


def test_engine_path_for() -> None:
    assert engine_path_for(Path("a/b/foo.onnx"), Path("/out")) == Path("/out/foo.engine")


def test_resolve_trtexec_explicit(tmp_path: Path) -> None:
    exe = tmp_path / "my-trtexec"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    assert resolve_trtexec(exe) == exe.resolve()
