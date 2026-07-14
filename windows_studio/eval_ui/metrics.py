"""Local hold-out / mock evaluation metrics (#54).

Studio eval is for debug UX only — Jetson ``acceptance`` remains the online gate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class EvalMetrics:
    """Recall-first metrics for the eval step."""

    recall: float
    precision: float
    split: str = "hold-out"
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    missed_case_ids: list[str] = field(default_factory=list)
    false_positive_case_ids: list[str] = field(default_factory=list)
    is_mock: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "recall": self.recall,
            "precision": self.precision,
            "split": self.split,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "missed_case_ids": list(self.missed_case_ids),
            "false_positive_case_ids": list(self.false_positive_case_ids),
            "is_mock": self.is_mock,
            "note": self.note,
        }


def mock_eval_metrics(
    case_ids: Sequence[str] | None = None,
    *,
    recall: float = 0.86,
    precision: float = 0.91,
) -> EvalMetrics:
    """Injectable metrics so GUI can be tested without a real model."""
    ids = list(case_ids or ["miss_demo_a", "miss_demo_b"])
    missed = ids[: max(1, min(2, len(ids)))] if ids else ["miss_demo_a"]
    fps = ids[2:3] if len(ids) > 2 else []
    return EvalMetrics(
        recall=recall,
        precision=precision,
        split="hold-out (mock)",
        true_positives=12,
        false_positives=len(fps) or 1,
        false_negatives=len(missed),
        missed_case_ids=missed,
        false_positive_case_ids=list(fps),
        is_mock=True,
        note="Studio mock — 不替代 Jetson acceptance（冻结集召回闸）",
    )


def metrics_from_counts(
    *,
    tp: int,
    fp: int,
    fn: int,
    missed_case_ids: Sequence[str] = (),
    false_positive_case_ids: Sequence[str] = (),
    split: str = "hold-out",
    is_mock: bool = False,
    note: str = "",
) -> EvalMetrics:
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    return EvalMetrics(
        recall=recall,
        precision=precision,
        split=split,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        missed_case_ids=list(missed_case_ids),
        false_positive_case_ids=list(false_positive_case_ids),
        is_mock=is_mock,
        note=note
        or (
            "Studio 本地评估 — 不替代 Jetson acceptance"
            if not is_mock
            else "Studio mock — 不替代 Jetson acceptance"
        ),
    )
