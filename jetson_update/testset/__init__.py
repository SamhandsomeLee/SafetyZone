"""Frozen field testset layout, MANIFEST validation, and overlap checks (#46)."""

from jetson_update.testset.manifest import (
    MANIFEST_NAME,
    ManifestError,
    TestsetManifest,
    load_manifest,
    validate_manifest_dict,
    write_example_manifest,
)
from jetson_update.testset.overlap import (
    FrozenTestsetOverlapError,
    assert_no_overlap_with_train,
    collect_frame_ids,
    find_overlaps_with_train,
    frame_fingerprint,
)

__all__ = [
    "MANIFEST_NAME",
    "ManifestError",
    "TestsetManifest",
    "FrozenTestsetOverlapError",
    "assert_no_overlap_with_train",
    "collect_frame_ids",
    "find_overlaps_with_train",
    "frame_fingerprint",
    "load_manifest",
    "validate_manifest_dict",
    "write_example_manifest",
]
