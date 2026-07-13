"""Train/test dataset isolation and overlap checks (#42)."""

from windows_studio.dataset.split import (
    DATASET_MANIFEST,
    TEST_DIR,
    TRAIN_DIR,
    DatasetConfig,
    DatasetOverlapError,
    assert_no_overlap,
    build_dataset,
    collect_frame_ids,
    find_overlaps,
    frame_fingerprint,
    load_dataset_manifest,
)

__all__ = [
    "DATASET_MANIFEST",
    "TEST_DIR",
    "TRAIN_DIR",
    "DatasetConfig",
    "DatasetOverlapError",
    "assert_no_overlap",
    "build_dataset",
    "collect_frame_ids",
    "find_overlaps",
    "frame_fingerprint",
    "load_dataset_manifest",
]
