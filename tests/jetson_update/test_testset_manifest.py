"""Tests for frozen testset MANIFEST + overlap (#46)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jetson_update.testset.manifest import (
    ManifestError,
    example_manifest_dict,
    load_manifest,
    validate_manifest_dict,
    write_example_manifest,
)
from jetson_update.testset.overlap import (
    FrozenTestsetOverlapError,
    assert_no_overlap_with_train,
    find_overlaps_with_train,
    frame_fingerprint,
)


def test_empty_manifest_valid() -> None:
    m = validate_manifest_dict(example_manifest_dict())
    assert m.frame_count == 0
    assert m.never_train is True
    assert "person" in m.class_names


def test_never_train_must_be_true() -> None:
    data = example_manifest_dict()
    data["never_train"] = False
    with pytest.raises(ManifestError, match="never_train"):
        validate_manifest_dict(data)


def test_repo_testset_manifest_only() -> None:
    root = Path(__file__).resolve().parents[2]
    testset = root / "jetson_update" / "testset"
    m = load_manifest(testset, require_files=False)
    assert m.frame_count == 0


def test_write_example_and_overlap_clean(tmp_path: Path) -> None:
    testset = tmp_path / "testset"
    write_example_manifest(testset)
    train = tmp_path / "train"
    train.mkdir()
    (train / "a.jpg").write_bytes(b"train-only")
    assert find_overlaps_with_train(train, testset) == []
    assert_no_overlap_with_train(train, testset)


def test_overlap_detected(tmp_path: Path) -> None:
    testset = tmp_path / "testset"
    write_example_manifest(testset)
    payload = b"same-bytes-for-overlap"
    (testset / "images" / "t1.jpg").write_bytes(payload)
    (testset / "labels" / "t1.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    data = example_manifest_dict()
    data["frames"] = [
        {"id": "t1", "image": "images/t1.jpg", "label": "labels/t1.txt"},
    ]
    (testset / "MANIFEST.json").write_text(json.dumps(data), encoding="utf-8")

    train = tmp_path / "train"
    train.mkdir()
    (train / "dup.jpg").write_bytes(payload)

    overlaps = find_overlaps_with_train(train, testset)
    assert frame_fingerprint(train / "dup.jpg") in overlaps
    with pytest.raises(FrozenTestsetOverlapError):
        assert_no_overlap_with_train(train, testset)


def test_require_files_missing(tmp_path: Path) -> None:
    testset = tmp_path / "testset"
    write_example_manifest(testset)
    data = example_manifest_dict()
    data["frames"] = [
        {"id": "missing", "image": "images/nope.jpg", "label": "labels/nope.txt"},
    ]
    (testset / "MANIFEST.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ManifestError, match="missing image"):
        load_manifest(testset, require_files=True)


def test_cli_manifest_only(tmp_path: Path) -> None:
    import importlib.util

    root = Path(__file__).resolve().parents[2]
    cli_path = root / "tools" / "check_testset_overlap.py"
    spec = importlib.util.spec_from_file_location("check_testset_overlap", cli_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    testset = tmp_path / "testset"
    write_example_manifest(testset)
    assert mod.main(["--testset", str(testset), "--manifest-only"]) == 0
