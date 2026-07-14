"""Sample list filters for review UX (#53 + #54 case-id jump)."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from enum import Enum

from windows_studio.review_ui.editor import ReviewItem


class SampleFilter(str, Enum):
    ALL = "all"
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    SUSPECT = "suspect"


FILTER_LABELS: tuple[tuple[SampleFilter, str], ...] = (
    (SampleFilter.ALL, "全部"),
    (SampleFilter.UNCONFIRMED, "未确认"),
    (SampleFilter.CONFIRMED, "已确认"),
    (SampleFilter.SUSPECT, "疑似漏检"),
)


def filter_review_items(
    items: list[ReviewItem],
    mode: SampleFilter,
) -> list[ReviewItem]:
    """Return items matching *mode* (order preserved)."""
    if mode is SampleFilter.ALL:
        return list(items)
    if mode is SampleFilter.UNCONFIRMED:
        return [i for i in items if not i.confirmed]
    if mode is SampleFilter.CONFIRMED:
        return [i for i in items if i.confirmed]
    if mode is SampleFilter.SUSPECT:
        return [i for i in items if i.suspect]
    return list(items)


def filter_by_case_ids(
    items: Sequence[ReviewItem],
    case_ids: Collection[str],
) -> list[ReviewItem]:
    """Narrow to the given case ids (order of *items* preserved). Used by eval miss→review."""
    wanted = set(case_ids)
    if not wanted:
        return []
    return [i for i in items if i.case_id in wanted]
