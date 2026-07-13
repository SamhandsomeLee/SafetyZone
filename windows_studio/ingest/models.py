"""Data models for Jetson outbox hard-case ingest."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".webp"})


@dataclass(frozen=True)
class IngestConfig:
    """Where to read outbox data and where to stage pulled cases."""

    source: str
    """Local directory path or ``rsync://user@host:/path/outbox``."""

    staging_dir: Path
    """Windows studio workspace directory for ingested cases."""

    @classmethod
    def from_dict(cls, data: dict) -> IngestConfig:
        return cls(
            source=str(data["source"]),
            staging_dir=Path(data.get("staging_dir", "windows_studio_data/ingest")),
        )

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "staging_dir": str(self.staging_dir),
        }


@dataclass
class HardCase:
    """One hard case: image plus optional YOLO pre-label and metadata."""

    case_id: str
    image_path: Path
    label_path: Path | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def has_labels(self) -> bool:
        return self.label_path is not None and self.label_path.is_file()

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "image_path": str(self.image_path),
            "label_path": str(self.label_path) if self.label_path else None,
            "metadata": dict(self.metadata),
            "has_labels": self.has_labels,
        }
