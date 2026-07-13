"""Build candidate TensorRT FP16 engines from ONNX (#48).

Wraps the same ``trtexec`` flags as ``tools/build_engine.sh`` so inbox ONNX
(from ``receiver``) can be compiled on-device into a candidate ``.engine``
before acceptance (#49).

API
---
::

    from jetson_update.build_engine import build_engine
    engine = build_engine(Path("model.onnx"), out_dir=Path("jetson_update/candidates"))

CLI
---
::

    PYTHONPATH=. python -m jetson_update.build_engine --onnx path/to/model.onnx
    PYTHONPATH=. python -m jetson_update.build_engine --onnx model.onnx --out candidates/ --dry-run

``--dry-run`` prints the ``trtexec`` command and writes a placeholder marker
at the would-be engine path (for tests / CI without GPU).
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TRTEXEC = Path("/usr/src/tensorrt/bin/trtexec")
DEFAULT_OUT_DIR = Path("jetson_update/candidates")
DRY_RUN_MARKER = "DRY_RUN_PLACEHOLDER\n"


class TrtexecNotFoundError(RuntimeError):
    """Raised when ``trtexec`` is missing and dry-run was not requested."""


class BuildEngineError(RuntimeError):
    """Raised when ``trtexec`` exits non-zero or the engine file is missing."""


def resolve_trtexec(trtexec: Path | str | None = None) -> Path | None:
    """Locate ``trtexec``: explicit path → ``TRTEXEC`` env → default → ``PATH``.

    Returns ``None`` if not found / not executable.
    """
    candidates: list[Path] = []
    if trtexec is not None:
        candidates.append(Path(trtexec))
    env = os.environ.get("TRTEXEC")
    if env:
        candidates.append(Path(env))
    candidates.append(DEFAULT_TRTEXEC)
    which = shutil.which("trtexec")
    if which:
        candidates.append(Path(which))

    seen: set[Path] = set()
    for path in candidates:
        resolved = path.expanduser()
        try:
            resolved = resolved.resolve()
        except OSError:
            pass
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def engine_path_for(onnx_path: Path, out_dir: Path) -> Path:
    """Return ``<out_dir>/<onnx_stem>.engine``."""
    return out_dir / f"{onnx_path.stem}.engine"


def trtexec_command(
    onnx_path: Path,
    engine_path: Path,
    *,
    trtexec: Path,
    fp16: bool = True,
) -> list[str]:
    """Build the ``trtexec`` argv (same style as ``tools/build_engine.sh``)."""
    cmd = [
        str(trtexec),
        f"--onnx={onnx_path}",
        f"--saveEngine={engine_path}",
    ]
    if fp16:
        cmd.append("--fp16")
    cmd.append("--skipInference")
    return cmd


def build_engine(
    onnx_path: Path | str,
    out_dir: Path | str | None = None,
    *,
    fp16: bool = True,
    dry_run: bool = False,
    trtexec: Path | str | None = None,
    timeout_s: float | None = None,
) -> Path:
    """Compile ``onnx_path`` to a candidate FP16 ``.engine`` under ``out_dir``.

    Returns the path to the written ``.engine`` (or dry-run placeholder).

    Raises
    ------
    FileNotFoundError
        ONNX missing.
    TrtexecNotFoundError
        ``trtexec`` not found and ``dry_run`` is False.
    BuildEngineError
        ``trtexec`` failed or did not produce the engine file.
    """
    onnx = Path(onnx_path).expanduser().resolve()
    if not onnx.is_file():
        raise FileNotFoundError(f"ONNX not found: {onnx}")

    dest_dir = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
    dest_dir = dest_dir.expanduser()
    if not dest_dir.is_absolute():
        dest_dir = (Path.cwd() / dest_dir).resolve()
    else:
        dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    engine = engine_path_for(onnx, dest_dir)
    exe = resolve_trtexec(trtexec)

    if dry_run:
        # Dry-run does not require a real trtexec binary.
        placeholder = exe if exe is not None else DEFAULT_TRTEXEC
        cmd = trtexec_command(onnx, engine, trtexec=placeholder, fp16=fp16)
        rendered = " ".join(cmd)
        logger.info("dry-run trtexec: %s", rendered)
        print(f"[jetson_update.build_engine] dry-run: {rendered}", flush=True)
        engine.write_text(DRY_RUN_MARKER, encoding="utf-8")
        print(f"[jetson_update.build_engine] placeholder: {engine}", flush=True)
        return engine

    if exe is None:
        raise TrtexecNotFoundError(
            "trtexec not found. Set TRTEXEC=/path/to/trtexec, install TensorRT, "
            "or pass --dry-run to print the command without building."
        )

    cmd = trtexec_command(onnx, engine, trtexec=exe, fp16=fp16)
    logger.info("Building engine: %s", " ".join(cmd))
    print(f"[jetson_update.build_engine] Building FP16 engine", flush=True)
    print(f"  ONNX:   {onnx}", flush=True)
    print(f"  ENGINE: {engine}", flush=True)
    print(f"  TRT:    {exe}", flush=True)

    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise BuildEngineError(
            f"trtexec timed out after {timeout_s}s for {onnx}"
        ) from exc

    if completed.stdout:
        logger.debug("trtexec stdout:\n%s", completed.stdout)
    if completed.stderr:
        logger.debug("trtexec stderr:\n%s", completed.stderr)

    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip()
        if len(tail) > 800:
            tail = tail[-800:]
        raise BuildEngineError(
            f"trtexec failed (exit {completed.returncode}) for {onnx}"
            + (f":\n{tail}" if tail else "")
        )

    if not engine.is_file() or engine.stat().st_size <= 0:
        raise BuildEngineError(
            f"trtexec exited 0 but engine missing/empty: {engine}"
        )

    print(f"[jetson_update.build_engine] Engine ready: {engine}", flush=True)
    return engine


def make_build_callback(
    out_dir: Path | str | None = None,
    *,
    fp16: bool = True,
    dry_run: bool = False,
) -> Callable[[Path], None]:
    """Return a ``receiver``-compatible callback that runs ``build_engine``.

    Full inbox → build → acceptance chain is wired in #49; this helper lets
    callers opt in early::

        from jetson_update.build_engine import make_build_callback
        from jetson_update.receiver import scan_once
        scan_once(inbox, callback=make_build_callback())
    """

    def _cb(path: Path) -> None:
        engine = build_engine(path, out_dir=out_dir, fp16=fp16, dry_run=dry_run)
        logger.info("built candidate engine: %s", engine)

    return _cb


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SafetyZone jetson_update — ONNX → FP16 engine via trtexec (#48)",
    )
    parser.add_argument(
        "--onnx",
        type=Path,
        required=True,
        help="Path to input ONNX model",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Output directory for .engine (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--no-fp16",
        action="store_true",
        help="Disable --fp16 (not recommended; default is FP16)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print trtexec command and write a placeholder engine marker",
    )
    parser.add_argument(
        "--trtexec",
        type=Path,
        default=None,
        help="Path to trtexec (default: TRTEXEC env or /usr/src/tensorrt/bin/trtexec)",
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
    try:
        engine = build_engine(
            args.onnx,
            out_dir=args.out,
            fp16=not args.no_fp16,
            dry_run=args.dry_run,
            trtexec=args.trtexec,
        )
    except (FileNotFoundError, TrtexecNotFoundError, BuildEngineError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(str(engine), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
