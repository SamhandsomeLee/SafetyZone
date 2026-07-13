"""Tests for windows_studio train (#43)."""

from __future__ import annotations

import json
from pathlib import Path

from windows_studio.train import TrainConfig, cuda_available, run_training


def _minimal_dataset(tmp_path: Path) -> Path:
    images = tmp_path / "train" / "images"
    labels = tmp_path / "train" / "labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    (images / "a.jpg").write_bytes(b"img-a")
    (labels / "a.txt").write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    return tmp_path


def test_dry_run_without_gpu(tmp_path: Path) -> None:
    config = TrainConfig(
        dataset_dir=_minimal_dataset(tmp_path / "dataset"),
        runs_dir=tmp_path / "runs",
        epochs=1,
    )
    result = run_training(config, force_dry_run=True)
    assert result.mode == "dry_run"
    assert result.best_weights is not None
    assert result.best_weights.is_file()
    assert result.run_dir is not None
    assert (result.run_dir / "DRY_RUN.md").is_file()
    manifest = json.loads((result.run_dir / "train_result.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "dry_run"
    assert "yolo" in " ".join(manifest["command"])


def test_data_yaml_written(tmp_path: Path) -> None:
    config = TrainConfig(
        dataset_dir=_minimal_dataset(tmp_path / "dataset"),
        runs_dir=tmp_path / "runs",
    )
    result = run_training(config, force_dry_run=True)
    assert result.data_yaml is not None
    text = result.data_yaml.read_text(encoding="utf-8")
    assert "train: train/images" in text
    assert "person" in text


def test_cuda_available_is_bool() -> None:
    assert isinstance(cuda_available(), bool)
