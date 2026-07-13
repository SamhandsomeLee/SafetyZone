"""Export ONNX from trained weights (#44)."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ALLOWED_EXPORT_SUFFIXES = frozenset({".pt"})


@dataclass
class ExportConfig:
    weights_path: Path
    export_dir: Path = Path("windows_studio_data/export")
    imgsz: int = 640
    opset: int = 12

    def to_dict(self) -> dict:
        return {
            "weights_path": str(self.weights_path),
            "export_dir": str(self.export_dir),
            "imgsz": self.imgsz,
            "opset": self.opset,
        }


@dataclass
class ExportResult:
    mode: str
    onnx_path: Path | None
    message: str = ""
    command: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "onnx_path": str(self.onnx_path) if self.onnx_path else None,
            "message": self.message,
            "command": list(self.command) if self.command else None,
        }


def _validate_weights(weights_path: Path) -> None:
    if not weights_path.is_file():
        raise FileNotFoundError(f"weights not found: {weights_path}")
    if weights_path.suffix.lower() not in ALLOWED_EXPORT_SUFFIXES:
        raise ValueError(f"export only supports PyTorch weights (.pt), got: {weights_path.suffix}")


def _build_export_command(config: ExportConfig) -> list[str]:
    return [
        "yolo",
        "export",
        f"model={config.weights_path}",
        "format=onnx",
        f"imgsz={config.imgsz}",
        f"opset={config.opset}",
    ]


def _dry_run_onnx(config: ExportConfig, command: list[str]) -> ExportResult:
    config.export_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    onnx_path = config.export_dir / f"safetyzone_{stamp}.onnx"
    # Minimal valid-enough placeholder for inbox send dry-run (not a real ONNX graph).
    onnx_path.write_bytes(b"\x08\x03PLACEHOLDER_ONNX_DRY_RUN\n")
    readme = config.export_dir / "EXPORT_DRY_RUN.md"
    readme.write_text(
        "\n".join(
            [
                "# ONNX export dry-run",
                "",
                "未安装 ultralytics 或强制 dry-run：仅生成占位 ONNX 文件。",
                "请在 Windows GPU 环境执行：",
                " ".join(command),
                "",
            ]
        ),
        encoding="utf-8",
    )
    manifest = config.export_dir / "export_result.json"
    result = ExportResult(
        mode="dry_run",
        onnx_path=onnx_path,
        message="placeholder ONNX written (not a deployable model)",
        command=command,
    )
    manifest.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return result


def _ultralytics_available() -> bool:
    try:
        import ultralytics  # noqa: F401

        return True
    except ImportError:
        return False


def export_onnx(config: ExportConfig, *, force_dry_run: bool = False) -> ExportResult:
    _validate_weights(config.weights_path)
    command = _build_export_command(config)

    if force_dry_run or not _ultralytics_available():
        logger.warning("onnx export dry-run: ultralytics=%s force=%s", _ultralytics_available(), force_dry_run)
        return _dry_run_onnx(config, command)

    logger.info("running yolo export: %s", " ".join(command))
    proc = subprocess.run(command, capture_output=True, text=True, check=False, cwd=config.weights_path.parent)
    if proc.returncode != 0:
        raise RuntimeError(
            f"yolo export failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout}"
        )

    onnx_path = config.weights_path.with_suffix(".onnx")
    if not onnx_path.is_file():
        candidates = sorted(config.weights_path.parent.glob("*.onnx"))
        if not candidates:
            raise FileNotFoundError("yolo export finished but no .onnx file found")
        onnx_path = candidates[-1]

    dest = config.export_dir / onnx_path.name
    config.export_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(onnx_path.read_bytes())

    result = ExportResult(
        mode="export",
        onnx_path=dest,
        message="ONNX exported via ultralytics",
        command=command,
    )
    (config.export_dir / "export_result.json").write_text(
        json.dumps(result.to_dict(), indent=2),
        encoding="utf-8",
    )
    return result
