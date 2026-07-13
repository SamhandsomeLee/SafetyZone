"""Overlap checks between train images and the frozen Jetson testset (#46)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from jetson_update.testset.manifest import MANIFEST_NAME, TestsetManifest, load_manifest

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class FrozenTestsetOverlapError(ValueError):
    """Raised when training data shares frames with the frozen testset."""

    def __init__(self, overlaps: list[str]) -> None:
        self.overlaps = overlaps
        super().__init__(f"train/testset overlap detected: {', '.join(overlaps)}")


def frame_fingerprint(image_path: Path) -> str:
    """Stable content hash when file exists; otherwise basename (dry-run friendly)."""
    image_path = Path(image_path)
    if image_path.is_file():
        digest = hashlib.sha256()
        digest.update(image_path.read_bytes())
        return digest.hexdigest()[:16]
    return image_path.name


def collect_frame_ids(directory: Path) -> set[str]:
    directory = Path(directory)
    if not directory.is_dir():
        return set()
    ids: set[str] = set()
    for image in directory.rglob("*"):
        if image.is_file() and image.suffix.lower() in _IMAGE_SUFFIXES:
            ids.add(frame_fingerprint(image))
    return ids


def collect_testset_frame_ids(testset_dir: Path, manifest: TestsetManifest | None = None) -> set[str]:
    """Fingerprints from MANIFEST image paths, falling back to images/ tree."""
    testset_dir = Path(testset_dir)
    if manifest is None:
        manifest_path = testset_dir / MANIFEST_NAME
        if manifest_path.is_file():
            manifest = load_manifest(testset_dir, require_files=False)
        else:
            return collect_frame_ids(testset_dir / "images")

    ids: set[str] = set()
    for fr in manifest.frames:
        ids.add(frame_fingerprint(testset_dir / fr.image))
    if not ids:
        ids |= collect_frame_ids(testset_dir / "images")
    return ids


def find_overlaps_with_train(train_dir: Path, testset_dir: Path) -> list[str]:
    train_ids = collect_frame_ids(Path(train_dir))
    test_ids = collect_testset_frame_ids(Path(testset_dir))
    return sorted(train_ids & test_ids)


def assert_no_overlap_with_train(train_dir: Path, testset_dir: Path) -> None:
    overlaps = find_overlaps_with_train(train_dir, testset_dir)
    if overlaps:
        raise FrozenTestsetOverlapError(overlaps)
