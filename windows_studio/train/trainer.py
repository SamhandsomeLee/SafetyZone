"""Local CUDA YOLO fine-tuning wrapper (#43)."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BASE_MODEL = "yolov8s.pt"


@dataclass
class TrainConfig:
    dataset_dir: Path
    runs_dir: Path = Path("windows_studio_data/runs")
    base_model: str = DEFAULT_BASE_MODEL
    epochs: int = 50
    batch: int = 8
    imgsz: int = 640
    device: str = "0"
    project_name: str = "safetyzone_finetune"

    @classmethod
    def from_dict(cls, data: dict) -> TrainConfig:
        return cls(
            dataset_dir=Path(data["dataset_dir"]),
            runs_dir=Path(data.get("runs_dir", "windows_studio_data/runs")),
            base_model=str(data.get("base_model", DEFAULT_BASE_MODEL)),
            epochs=int(data.get("epochs", 50)),
            batch=int(data.get("batch", 8)),
            imgsz=int(data.get("imgsz", 640)),
            device=str(data.get("device", "0")),
            project_name=str(data.get("project_name", "safetyzone_finetune")),
        )

    def to_dict(self) -> dict:
        return {
            "dataset_dir": str(self.dataset_dir),
            "runs_dir": str(self.runs_dir),
            "base_model": self.base_model,
            "epochs": self.epochs,
            "batch": self.batch,
            "imgsz": self.imgsz,
            "device": self.device,
            "project_name": self.project_name,
        }


@dataclass
class TrainResult:
    mode: str
    """``cuda`` | ``dry_run``"""

    run_dir: Path | None = None
    best_weights: Path | None = None
    data_yaml: Path | None = None
    message: str = ""
    command: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "run_dir": str(self.run_dir) if self.run_dir else None,
            "best_weights": str(self.best_weights) if self.best_weights else None,
            "data_yaml": str(self.data_yaml) if self.data_yaml else None,
            "message": self.message,
            "command": list(self.command),
        }


def cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


def _write_data_yaml(config: TrainConfig, yaml_path: Path) -> Path:
    train_images = config.dataset_dir / "train" / "images"
    if not train_images.is_dir():
        raise FileNotFoundError(f"train images not found: {train_images}")

    # Ultralytics expects path + train/val relative paths.
    content = "\n".join(
        [
            f"path: {config.dataset_dir.resolve()}",
            "train: train/images",
            "val: train/images",
            "names:",
            "  0: person",
            "",
        ]
    )
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(content, encoding="utf-8")
    return yaml_path


def _build_yolo_command(config: TrainConfig, data_yaml: Path) -> list[str]:
    return [
        "yolo",
        "detect",
        "train",
        f"model={config.base_model}",
        f"data={data_yaml}",
        f"epochs={config.epochs}",
        f"batch={config.batch}",
        f"imgsz={config.imgsz}",
        f"device={config.device}",
        f"project={config.runs_dir}",
        f"name={config.project_name}",
        "exist_ok=True",
    ]


def _dry_run_artifacts(config: TrainConfig, data_yaml: Path, command: list[str]) -> TrainResult:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = config.runs_dir / f"{config.project_name}_dryrun_{stamp}"
    weights_dir = run_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    best = weights_dir / "best.pt"
    best.write_text("# dry-run placeholder weights\n", encoding="utf-8")
    readme = run_dir / "DRY_RUN.md"
    readme.write_text(
        "\n".join(
            [
                "# SafetyZone studio train dry-run",
                "",
                "本机未检测到 CUDA GPU（或缺少 torch/ultralytics）。",
                "请在 **Windows 11 + NVIDIA GPU** 上安装 `pip install -e \".[windows]\"` 后重跑。",
                "",
                "将执行的命令：",
                " ".join(command),
                "",
            ]
        ),
        encoding="utf-8",
    )
    manifest = run_dir / "train_result.json"
    result = TrainResult(
        mode="dry_run",
        run_dir=run_dir,
        best_weights=best,
        data_yaml=data_yaml,
        message="CUDA unavailable — wrote dry-run artifacts only (not a real training run)",
        command=command,
    )
    manifest.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return result


def run_training(config: TrainConfig, *, force_dry_run: bool = False) -> TrainResult:
    """Run LocalCuda YOLO fine-tune, or dry-run when GPU unavailable."""
    data_yaml = _write_data_yaml(config, config.runs_dir / "data.yaml")
    command = _build_yolo_command(config, data_yaml)

    if force_dry_run or not cuda_available():
        logger.warning("training dry-run: cuda_available=%s force=%s", cuda_available(), force_dry_run)
        return _dry_run_artifacts(config, data_yaml, command)

    logger.info("launching yolo train: %s", " ".join(command))
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"yolo train failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout}"
        )

    run_dir = config.runs_dir / config.project_name
    best = run_dir / "weights" / "best.pt"
    if not best.is_file():
        raise FileNotFoundError(f"expected weights not found after train: {best}")

    result = TrainResult(
        mode="cuda",
        run_dir=run_dir,
        best_weights=best,
        data_yaml=data_yaml,
        message="training completed on local CUDA",
        command=command,
    )
    (run_dir / "train_result.json").write_text(
        json.dumps(result.to_dict(), indent=2),
        encoding="utf-8",
    )
    return result


def load_train_result(run_dir: Path) -> TrainResult:
    manifest = run_dir / "train_result.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return TrainResult(
            mode=data["mode"],
            run_dir=Path(data["run_dir"]) if data.get("run_dir") else None,
            best_weights=Path(data["best_weights"]) if data.get("best_weights") else None,
            data_yaml=Path(data["data_yaml"]) if data.get("data_yaml") else None,
            message=data.get("message", ""),
            command=list(data.get("command", [])),
        )
    best = run_dir / "weights" / "best.pt"
    if best.is_file():
        return TrainResult(mode="cuda", run_dir=run_dir, best_weights=best)
    raise FileNotFoundError(f"no train result in {run_dir}")
