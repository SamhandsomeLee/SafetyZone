"""Tests for windows_studio dataset (#42)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from windows_studio.dataset import (
    DatasetConfig,
    DatasetOverlapError,
    assert_no_overlap,
    build_dataset,
    find_overlaps,
)
from windows_studio.review_ui import ReviewItem, save_review_manifest


def _review_item(case_id: str, tmp_path: Path, *, confirmed: bool = True) -> ReviewItem:
    image = tmp_path / f"{case_id}.jpg"
    image.write_bytes(f"img-{case_id}".encode())
    label = tmp_path / f"{case_id}.txt"
    label.write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    return ReviewItem(
        case_id=case_id,
        image_path=image,
        label_path=label,
        confirmed=confirmed,
    )


def test_build_dataset_physical_isolation(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    items = [_review_item("a", tmp_path), _review_item("b", tmp_path)]
    save_review_manifest(review_dir, items)

    config = DatasetConfig(
        review_dir=review_dir,
        dataset_dir=tmp_path / "dataset",
        test_ratio=0.0,
    )
    manifest = build_dataset(config)
    assert manifest["train_cases"] == ["a", "b"]
    assert manifest["test_cases"] == []
    assert (config.dataset_dir / "train" / "images" / "a.jpg").is_file()
    assert (config.dataset_dir / "train" / "labels" / "a.txt").is_file()
    assert not (config.dataset_dir / "test" / "images").exists() or not any(
        (config.dataset_dir / "test" / "images").iterdir()
    )


def test_overlap_rejected(tmp_path: Path) -> None:
    train_images = tmp_path / "train" / "images"
    test_images = tmp_path / "test" / "images"
    train_images.mkdir(parents=True)
    test_images.mkdir(parents=True)
    same = train_images / "dup.jpg"
    same.write_bytes(b"same-bytes")
    shutil.copy2(same, test_images / "dup_copy.jpg")

    overlaps = find_overlaps(train_images, test_images)
    assert len(overlaps) == 1

    with pytest.raises(DatasetOverlapError):
        assert_no_overlap(train_images, test_images)


def test_explicit_test_split(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    items = [_review_item("train_me", tmp_path), _review_item("hold_out", tmp_path)]
    save_review_manifest(review_dir, items)

    config = DatasetConfig(
        review_dir=review_dir,
        dataset_dir=tmp_path / "dataset",
        test_case_ids=frozenset({"hold_out"}),
    )
    manifest = build_dataset(config)
    assert manifest["train_cases"] == ["train_me"]
    assert manifest["test_cases"] == ["hold_out"]
    assert (config.dataset_dir / "test" / "images" / "hold_out.jpg").is_file()

    saved = json.loads((config.dataset_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert saved["overlap_check"] == "passed"
