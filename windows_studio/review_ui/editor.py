"""Review state and CLI editor for pre-annotations (#41)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from windows_studio.ingest import HardCase
from windows_studio.review_ui.labels import YoloBox, read_labels, write_labels

REVIEW_MANIFEST = "review_manifest.json"
MISSING_LABEL_HINT = (
    "引导：宁可多标、勿漏标 — 漏标对安全系统更危险。"
    " 若画面有人但未画框，请用 add 补框。"
)
SUSPECT_REASONS = frozenset({"missed_detection", "near_zone", "low_confidence", "suspect"})


@dataclass
class ReviewItem:
    case_id: str
    image_path: Path
    label_path: Path
    boxes: list[YoloBox] = field(default_factory=list)
    pred_boxes: list[YoloBox] = field(default_factory=list)
    confirmed: bool = False
    suspect: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "image_path": str(self.image_path),
            "label_path": str(self.label_path),
            "box_count": len(self.boxes),
            "pred_box_count": len(self.pred_boxes),
            "confirmed": self.confirmed,
            "suspect": self.suspect,
            "notes": self.notes,
        }


def is_suspect_case(case: HardCase) -> bool:
    reason = str(case.metadata.get("reason", "")).lower()
    if reason in SUSPECT_REASONS:
        return True
    score = case.metadata.get("score")
    if isinstance(score, (int, float)) and score < 0.5:
        return True
    return not case.has_labels


def _load_pred_boxes(case: HardCase, review_dir: Path) -> list[YoloBox]:
    """Optional prediction layer: ``{id}.pred.txt`` or metadata ``pred_boxes``."""
    pred_path = review_dir / f"{case.case_id}.pred.txt"
    if pred_path.is_file():
        return read_labels(pred_path)
    raw = case.metadata.get("pred_boxes")
    if isinstance(raw, list):
        boxes: list[YoloBox] = []
        for row in raw:
            if isinstance(row, (list, tuple)) and len(row) == 5:
                boxes.append(
                    YoloBox(
                        class_id=int(row[0]),
                        cx=float(row[1]),
                        cy=float(row[2]),
                        w=float(row[3]),
                        h=float(row[4]),
                    )
                )
        return boxes
    return []


def build_review_queue(cases: list[HardCase], review_dir: Path) -> list[ReviewItem]:
    review_dir.mkdir(parents=True, exist_ok=True)
    items: list[ReviewItem] = []
    for case in cases:
        label_path = review_dir / f"{case.case_id}.txt"
        if label_path.is_file():
            boxes = read_labels(label_path)
        elif case.label_path and case.label_path.is_file():
            boxes = read_labels(case.label_path)
            write_labels(label_path, boxes)
        else:
            boxes = []
            write_labels(label_path, boxes)

        items.append(
            ReviewItem(
                case_id=case.case_id,
                image_path=case.image_path,
                label_path=label_path,
                boxes=boxes,
                pred_boxes=_load_pred_boxes(case, review_dir),
                suspect=is_suspect_case(case),
            )
        )
    return items


def save_review_manifest(review_dir: Path, items: list[ReviewItem]) -> None:
    payload = [item.to_dict() for item in items]
    (review_dir / REVIEW_MANIFEST).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_review_manifest(review_dir: Path) -> list[ReviewItem]:
    path = review_dir / REVIEW_MANIFEST
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    items: list[ReviewItem] = []
    for row in data:
        label_path = Path(row["label_path"])
        case_id = row["case_id"]
        pred_path = review_dir / f"{case_id}.pred.txt"
        pred_boxes = read_labels(pred_path) if pred_path.is_file() else []
        items.append(
            ReviewItem(
                case_id=case_id,
                image_path=Path(row["image_path"]),
                label_path=label_path,
                boxes=read_labels(label_path),
                pred_boxes=pred_boxes,
                confirmed=bool(row.get("confirmed")),
                suspect=bool(row.get("suspect")),
                notes=str(row.get("notes", "")),
            )
        )
    return items


def load_workspace_review(
    workspace: Path,
    *,
    review_dir: Path | None = None,
    staging_dir: Path | None = None,
) -> list[ReviewItem]:
    """Load review queue from workspace review/ or ingest staging.

    Prefer existing ``review_manifest.json``; otherwise build from staged
    ingest cases. Returns empty list when neither has data.
    """
    review = review_dir or (workspace / "review")
    items = load_review_manifest(review)
    if items:
        return items

    staging = staging_dir or (workspace / "ingest")
    from windows_studio.ingest import load_staged_cases

    cases = load_staged_cases(staging)
    if not cases:
        return []
    return build_review_queue(cases, review)


def format_item_summary(index: int, total: int, item: ReviewItem) -> str:
    flag = " [疑似漏检]" if item.suspect else ""
    status = "已确认" if item.confirmed else "待复核"
    lines = [
        f"--- [{index + 1}/{total}] {item.case_id}{flag} ({status}) ---",
        f"image: {item.image_path}",
        f"labels: {item.label_path}",
        f"boxes ({len(item.boxes)}):",
    ]
    if item.boxes:
        for i, box in enumerate(item.boxes):
            lines.append(f"  [{i}] class={box.class_id} cx={box.cx:.3f} cy={box.cy:.3f} "
                         f"w={box.w:.3f} h={box.h:.3f}")
    else:
        lines.append("  (无框 — 请检查是否漏标)")
    if item.suspect or not item.boxes:
        lines.append(MISSING_LABEL_HINT)
    return "\n".join(lines)


def apply_edit_command(item: ReviewItem, command: str) -> str | None:
    """Mutate *item* per CLI command. Returns error message or None."""
    parts = command.strip().split()
    if not parts:
        return "empty command"
    verb = parts[0].lower()

    if verb in {"confirm", "ok", "y"}:
        item.confirmed = True
        return None

    if verb in {"unconfirm", "n"}:
        item.confirmed = False
        return None

    if verb == "del" and len(parts) == 2:
        idx = int(parts[1])
        if idx < 0 or idx >= len(item.boxes):
            return f"index out of range: {idx}"
        item.boxes.pop(idx)
        write_labels(item.label_path, item.boxes)
        return None

    if verb == "edit" and len(parts) == 7:
        idx = int(parts[1])
        if idx < 0 or idx >= len(item.boxes):
            return f"index out of range: {idx}"
        item.boxes[idx] = YoloBox(
            class_id=int(parts[2]),
            cx=float(parts[3]),
            cy=float(parts[4]),
            w=float(parts[5]),
            h=float(parts[6]),
        )
        write_labels(item.label_path, item.boxes)
        return None

    if verb == "add" and len(parts) == 6:
        item.boxes.append(
            YoloBox(
                class_id=int(parts[1]),
                cx=float(parts[2]),
                cy=float(parts[3]),
                w=float(parts[4]),
                h=float(parts[5]),
            )
        )
        write_labels(item.label_path, item.boxes)
        return None

    if verb == "note" and len(parts) >= 2:
        item.notes = command.split(maxsplit=1)[1]
        return None

    return (
        "commands: confirm | unconfirm | del <i> | "
        "edit <i> <cls> <cx> <cy> <w> <h> | add <cls> <cx> <cy> <w> <h> | note <text> | skip"
    )


def review_cases_interactive(
    cases: list[HardCase],
    review_dir: Path,
    *,
    auto_confirm: bool = False,
) -> list[ReviewItem]:
    """Walk cases in CLI; edit labels and mark confirmed."""
    items = build_review_queue(cases, review_dir)
    total = len(items)

    for index, item in enumerate(items):
        if auto_confirm:
            item.confirmed = True
            write_labels(item.label_path, item.boxes)
            continue

        print(format_item_summary(index, total, item))
        while True:
            command = input("review> ").strip()
            if command in {"", "skip", "s"}:
                break
            if command in {"quit", "q"}:
                save_review_manifest(review_dir, items)
                return items
            err = apply_edit_command(item, command)
            if err:
                print(f"ERR: {err}")
                continue
            print(format_item_summary(index, total, item))

    save_review_manifest(review_dir, items)
    return items


def review_cases_batch(
    cases: list[HardCase],
    review_dir: Path,
    commands: dict[str, list[str]] | None = None,
) -> list[ReviewItem]:
    """Non-interactive review for tests and wizard dry-run."""
    items = build_review_queue(cases, review_dir)
    commands = commands or {}
    for item in items:
        for command in commands.get(item.case_id, ["confirm"]):
            apply_edit_command(item, command)
        write_labels(item.label_path, item.boxes)
    save_review_manifest(review_dir, items)
    return items
