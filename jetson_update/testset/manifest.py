"""Frozen testset MANIFEST schema and validation (#46)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_NAME = "MANIFEST.json"
MANIFEST_SCHEMA_VERSION = 1

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class ManifestError(ValueError):
    """Raised when MANIFEST.json fails schema or on-disk checks."""


@dataclass(frozen=True)
class TestsetFrame:
    """One locked evaluation frame (image + YOLO label)."""

    frame_id: str
    image: str
    label: str
    notes: str = ""


@dataclass(frozen=True)
class TestsetManifest:
    """In-memory representation of the frozen field testset."""

    schema_version: int
    locked: bool
    never_train: bool
    class_names: tuple[str, ...]
    frames: tuple[TestsetFrame, ...]
    description: str = ""
    created_at: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def frame_count(self) -> int:
        return len(self.frames)


def validate_manifest_dict(data: dict[str, Any], *, require_files: bool = False, root: Path | None = None) -> TestsetManifest:
    """Validate a MANIFEST dict. Empty ``frames`` is allowed (tooling smoke / pre-fill)."""
    if not isinstance(data, dict):
        raise ManifestError("MANIFEST root must be an object")

    try:
        schema_version = int(data.get("schema_version", 0))
    except (TypeError, ValueError) as exc:
        raise ManifestError("schema_version must be an int") from exc
    if schema_version != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(
            f"unsupported schema_version {schema_version!r}; expected {MANIFEST_SCHEMA_VERSION}"
        )

    if "locked" not in data or not isinstance(data["locked"], bool):
        raise ManifestError("locked must be a boolean")
    if "never_train" not in data or not isinstance(data["never_train"], bool):
        raise ManifestError("never_train must be a boolean")
    if data["never_train"] is not True:
        raise ManifestError("never_train must be true (frozen set must never enter training)")

    raw_classes = data.get("class_names")
    if not isinstance(raw_classes, list) or not raw_classes:
        raise ManifestError("class_names must be a non-empty list")
    class_names = tuple(str(c) for c in raw_classes)
    if "person" not in class_names:
        raise ManifestError("class_names must include 'person' (Bootstrap/Production class)")

    raw_frames = data.get("frames")
    if not isinstance(raw_frames, list):
        raise ManifestError("frames must be a list (may be empty before field fill)")

    frames: list[TestsetFrame] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(raw_frames):
        if not isinstance(item, dict):
            raise ManifestError(f"frames[{i}] must be an object")
        frame_id = str(item.get("id", "")).strip()
        image = str(item.get("image", "")).strip()
        label = str(item.get("label", "")).strip()
        if not frame_id:
            raise ManifestError(f"frames[{i}].id is required")
        if frame_id in seen_ids:
            raise ManifestError(f"duplicate frame id: {frame_id!r}")
        seen_ids.add(frame_id)
        if not image:
            raise ManifestError(f"frames[{i}].image is required")
        if not label:
            raise ManifestError(f"frames[{i}].label is required")
        if Path(image).suffix.lower() not in _IMAGE_SUFFIXES:
            raise ManifestError(f"frames[{i}].image has unsupported suffix: {image!r}")
        if not label.endswith(".txt"):
            raise ManifestError(f"frames[{i}].label must be a .txt YOLO label path")
        frames.append(
            TestsetFrame(
                frame_id=frame_id,
                image=image,
                label=label,
                notes=str(item.get("notes", "")),
            )
        )

    if require_files:
        if root is None:
            raise ManifestError("require_files=True needs root=testset directory")
        for fr in frames:
            img_path = root / fr.image
            lbl_path = root / fr.label
            if not img_path.is_file():
                raise ManifestError(f"missing image file: {fr.image}")
            if not lbl_path.is_file():
                raise ManifestError(f"missing label file: {fr.label}")

    known = {
        "schema_version",
        "locked",
        "never_train",
        "class_names",
        "frames",
        "description",
        "created_at",
    }
    extras = {k: v for k, v in data.items() if k not in known}

    return TestsetManifest(
        schema_version=schema_version,
        locked=bool(data["locked"]),
        never_train=True,
        class_names=class_names,
        frames=tuple(frames),
        description=str(data.get("description", "")),
        created_at=str(data.get("created_at", "")),
        extras=extras,
    )


def load_manifest(
    testset_dir: Path,
    *,
    require_files: bool = False,
) -> TestsetManifest:
    path = Path(testset_dir) / MANIFEST_NAME
    if not path.is_file():
        raise ManifestError(f"MANIFEST not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"MANIFEST JSON invalid: {exc}") from exc
    return validate_manifest_dict(data, require_files=require_files, root=Path(testset_dir))


def example_manifest_dict() -> dict[str, Any]:
    """Empty locked-capable template for field teams (frames filled on site)."""
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "locked": False,
        "never_train": True,
        "class_names": ["person"],
        "description": "Field frozen testset for Jetson FP16 recall acceptance (fill frames on site; then set locked=true).",
        "created_at": "",
        "frames": [],
    }


def write_example_manifest(testset_dir: Path) -> Path:
    testset_dir = Path(testset_dir)
    testset_dir.mkdir(parents=True, exist_ok=True)
    (testset_dir / "images").mkdir(exist_ok=True)
    (testset_dir / "labels").mkdir(exist_ok=True)
    path = testset_dir / MANIFEST_NAME
    path.write_text(
        json.dumps(example_manifest_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
