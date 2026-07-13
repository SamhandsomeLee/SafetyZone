"""Dataset layout and overlap validation (#42)."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from windows_studio.review_ui import ReviewItem, load_review_manifest

DATASET_MANIFEST = "dataset_manifest.json"
TRAIN_DIR = "train"
TEST_DIR = "test"


class DatasetOverlapError(ValueError):
    """Raised when train and test sets share the same frame."""

    def __init__(self, overlaps: list[str]) -> None:
        self.overlaps = overlaps
        super().__init__(f"train/test overlap detected: {', '.join(overlaps)}")


@dataclass(frozen=True)
class DatasetConfig:
    review_dir: Path
    dataset_dir: Path
    test_ratio: float = 0.0
    """Fraction of confirmed cases reserved for test (0 = all train for studio dry-run)."""

    test_case_ids: frozenset[str] = frozenset()
    """Explicit test case IDs override ratio split."""

    @classmethod
    def from_dict(cls, data: dict) -> DatasetConfig:
        test_ids = data.get("test_case_ids", [])
        return cls(
            review_dir=Path(data.get("review_dir", "windows_studio_data/review")),
            dataset_dir=Path(data.get("dataset_dir", "windows_studio_data/dataset")),
            test_ratio=float(data.get("test_ratio", 0.0)),
            test_case_ids=frozenset(str(x) for x in test_ids),
        )

    def to_dict(self) -> dict:
        return {
            "review_dir": str(self.review_dir),
            "dataset_dir": str(self.dataset_dir),
            "test_ratio": self.test_ratio,
            "test_case_ids": sorted(self.test_case_ids),
        }


def frame_fingerprint(image_path: Path) -> str:
    """Stable ID for overlap checks — basename for studio; hash if file exists."""
    if image_path.is_file():
        digest = hashlib.sha256()
        digest.update(image_path.read_bytes())
        return digest.hexdigest()[:16]
    return image_path.name


def collect_frame_ids(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    ids: set[str] = set()
    for image in directory.rglob("*"):
        if image.is_file() and image.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
            ids.add(frame_fingerprint(image))
    return ids


def find_overlaps(train_dir: Path, test_dir: Path) -> list[str]:
    train_ids = collect_frame_ids(train_dir)
    test_ids = collect_frame_ids(test_dir)
    shared = sorted(train_ids & test_ids)
    return shared


def assert_no_overlap(train_dir: Path, test_dir: Path) -> None:
    overlaps = find_overlaps(train_dir, test_dir)
    if overlaps:
        raise DatasetOverlapError(overlaps)


def _split_items(
    items: list[ReviewItem],
    config: DatasetConfig,
) -> tuple[list[ReviewItem], list[ReviewItem]]:
    confirmed = [i for i in items if i.confirmed]
    if not confirmed:
        return [], []

    if config.test_case_ids:
        test = [i for i in confirmed if i.case_id in config.test_case_ids]
        train = [i for i in confirmed if i.case_id not in config.test_case_ids]
        return train, test

    if config.test_ratio <= 0:
        return confirmed, []

    test_count = max(1, int(len(confirmed) * config.test_ratio))
    train = confirmed[:-test_count] if test_count < len(confirmed) else confirmed
    test = confirmed[-test_count:] if test_count < len(confirmed) else []
    return train, test


def _copy_split(items: list[ReviewItem], dest_root: Path) -> None:
    images = dest_root / "images"
    labels = dest_root / "labels"
    images.mkdir(parents=True, exist_ok=True)
    labels.mkdir(parents=True, exist_ok=True)
    for item in items:
        src_image = item.image_path
        if src_image.is_file():
            shutil.copy2(src_image, images / f"{item.case_id}{src_image.suffix.lower()}")
        if item.label_path.is_file():
            shutil.copy2(item.label_path, labels / f"{item.case_id}.txt")


def build_dataset(config: DatasetConfig) -> dict:
    """Materialize train/test trees from reviewed labels; reject on overlap."""
    items = load_review_manifest(config.review_dir)
    if not items:
        raise FileNotFoundError(f"no review manifest in {config.review_dir}")

    train_items, test_items = _split_items(items, config)
    dataset_dir = config.dataset_dir
    train_dir = dataset_dir / TRAIN_DIR
    test_dir = dataset_dir / TEST_DIR

    if dataset_dir.exists():
        shutil.rmtree(dataset_dir)
    dataset_dir.mkdir(parents=True)

    _copy_split(train_items, train_dir)
    _copy_split(test_items, test_dir)
    assert_no_overlap(train_dir / "images", test_dir / "images")

    manifest = {
        "train_cases": [i.case_id for i in train_items],
        "test_cases": [i.case_id for i in test_items],
        "train_images": str(train_dir / "images"),
        "test_images": str(test_dir / "images"),
        "overlap_check": "passed",
    }
    (dataset_dir / DATASET_MANIFEST).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def load_dataset_manifest(dataset_dir: Path) -> dict:
    path = dataset_dir / DATASET_MANIFEST
    if not path.is_file():
        raise FileNotFoundError(f"dataset manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
