"""YOLO label parsing and serialization for review_ui."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class YoloBox:
    """Normalized YOLO detection: class cx cy w h."""

    class_id: int
    cx: float
    cy: float
    w: float
    h: float

    def to_line(self) -> str:
        return f"{self.class_id} {self.cx:.6f} {self.cy:.6f} {self.w:.6f} {self.h:.6f}"

    @classmethod
    def from_line(cls, line: str) -> YoloBox:
        parts = line.strip().split()
        if len(parts) != 5:
            raise ValueError(f"expected 5 fields, got {len(parts)}: {line!r}")
        class_id = int(parts[0])
        cx, cy, w, h = (float(x) for x in parts[1:])
        return cls(class_id=class_id, cx=cx, cy=cy, w=w, h=h)


def read_labels(path: Path | None) -> list[YoloBox]:
    if path is None or not path.is_file():
        return []
    boxes: list[YoloBox] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        boxes.append(YoloBox.from_line(stripped))
    return boxes


def write_labels(path: Path, boxes: list[YoloBox]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(box.to_line() for box in boxes)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")
