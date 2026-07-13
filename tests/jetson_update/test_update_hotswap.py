"""Tests for jetson_update.hotswap (#50) — acceptance gate + EngineHotSwap."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from detect.backend import BackendKind, InferBackend
from detect.hotswap import EngineHotSwap
from detect.letterbox import DEFAULT_INPUT_SIZE
from jetson_update.acceptance import AcceptanceResult, DEFAULT_RECALL_THRESHOLD
from jetson_update.hotswap import RuntimeHotswap, promote_if_accepted, rollback


class TrackingBackend(InferBackend):
    """Fake backend that records path / warmup / close (no TensorRT)."""

    def __init__(self, *, tag: str, input_size: int = DEFAULT_INPUT_SIZE) -> None:
        self.tag = tag
        self.input_size = input_size
        self.loaded_path: Path | None = None
        self.warmup_count = 0
        self.closed = False

    @property
    def engine_path(self) -> Path | None:
        return self.loaded_path

    def load(self, model_path: str | Path) -> None:
        self.loaded_path = Path(model_path)
        self.closed = False

    def infer_batch(self, batch: np.ndarray) -> np.ndarray:
        return np.zeros((1, 84, 8400), dtype=np.float32)

    def warmup(self, n: int = 3) -> None:
        self.warmup_count += max(1, n)

    def close(self) -> None:
        self.closed = True


def _factory(*tags: str):
    tag_iter = iter(tags)

    def factory(kind: BackendKind, path: Path, kwargs: dict) -> InferBackend:
        del kind
        tag = next(tag_iter)
        backend = TrackingBackend(tag=tag, input_size=int(kwargs.get("input_size", DEFAULT_INPUT_SIZE)))
        backend.load(path)
        return backend

    return factory


def _pass(reason: str = "ok") -> AcceptanceResult:
    return AcceptanceResult(
        passed=True,
        recall=0.99,
        reason=reason,
        threshold=DEFAULT_RECALL_THRESHOLD,
        frame_count=1,
    )


def _fail(reason: str = "recall too low") -> AcceptanceResult:
    return AcceptanceResult(
        passed=False,
        recall=0.5,
        reason=reason,
        threshold=DEFAULT_RECALL_THRESHOLD,
        frame_count=1,
    )


def test_promote_pass_commits_candidate() -> None:
    active = TrackingBackend(tag="v1")
    active.load("models/v1.engine")
    swap = EngineHotSwap(active, backend_factory=_factory("v2"))
    gate = RuntimeHotswap(swap)

    result = gate.promote("models/v2.engine", acceptance=_pass(), warmup_n=1)

    assert result.switched is True
    assert result.acceptance is not None
    assert result.acceptance.allows_hotswap is True
    assert swap.active_path == Path("models/v2.engine")
    assert swap.previous_path == Path("models/v1.engine")
    assert swap.active_backend.tag == "v2"


def test_promote_fail_keeps_active() -> None:
    active = TrackingBackend(tag="v1")
    active.load("models/v1.engine")
    # factory should never be called on reject
    called: list[Path] = []

    def factory(kind: BackendKind, path: Path, kwargs: dict) -> InferBackend:
        called.append(path)
        backend = TrackingBackend(tag="should_not")
        backend.load(path)
        return backend

    swap = EngineHotSwap(active, backend_factory=factory)
    result = RuntimeHotswap(swap).promote("models/v2.engine", acceptance=_fail())

    assert result.switched is False
    assert "rejected" in result.reason
    assert swap.active_path == Path("models/v1.engine")
    assert swap.active_backend.tag == "v1"
    assert swap.candidate_path is None
    assert called == []


def test_promote_if_accepted_helper() -> None:
    active = TrackingBackend(tag="v1")
    active.load("models/v1.engine")
    swap = EngineHotSwap(active, backend_factory=_factory("v2"))

    ok = promote_if_accepted(swap, "models/v2.engine", acceptance=_pass(), warmup_n=1)
    assert ok.switched is True

    fail = promote_if_accepted(swap, "models/v3.engine", acceptance=_fail())
    assert fail.switched is False
    assert swap.active_path == Path("models/v2.engine")


def test_rollback_restores_previous() -> None:
    active = TrackingBackend(tag="v1")
    active.load("models/v1.engine")
    swap = EngineHotSwap(active, backend_factory=_factory("v2"))
    gate = RuntimeHotswap(swap)

    assert gate.promote("models/v2.engine", acceptance=_pass(), warmup_n=1).switched
    rb = gate.rollback()

    assert rb.switched is True
    assert swap.active_path == Path("models/v1.engine")
    assert swap.previous_path is None


def test_rollback_unavailable_without_previous() -> None:
    active = TrackingBackend(tag="v1")
    active.load("models/v1.engine")
    swap = EngineHotSwap(active, backend_factory=_factory("v2"))

    result = rollback(swap)
    assert result.switched is False
    assert "unavailable" in result.reason


def test_promote_runs_acceptance_when_not_provided(tmp_path: Path) -> None:
    """Inject evaluate_fn via acceptance_config path (no GPU)."""
    import json

    from jetson_update.acceptance import AcceptanceConfig, EvalMetrics
    from jetson_update.testset.manifest import MANIFEST_SCHEMA_VERSION

    cand = tmp_path / "cand.engine"
    cand.write_bytes(b"fake")
    testset = tmp_path / "testset"
    testset.mkdir()
    (testset / "MANIFEST.json").write_text(
        json.dumps(
            {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "locked": True,
                "never_train": True,
                "class_names": ["person"],
                "description": "",
                "created_at": "",
                "frames": [{"id": "f1", "image": "images/a.jpg", "label": "labels/a.txt"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    active = TrackingBackend(tag="v1")
    active.load("models/v1.engine")
    swap = EngineHotSwap(active, backend_factory=_factory("v2"))
    cfg = AcceptanceConfig(engine_path=cand, testset_dir=testset, recall_threshold=0.95)

    # Below threshold → no commit
    fail = RuntimeHotswap(swap).promote(
        cand,
        acceptance_config=cfg,
        evaluate_fn=lambda _c, _m: EvalMetrics(true_positives=1, false_positives=0, false_negatives=1),
        warmup_n=1,
    )
    assert fail.switched is False
    assert swap.active_path == Path("models/v1.engine")

    # At threshold → commit
    ok = RuntimeHotswap(swap).promote(
        cand,
        acceptance_config=cfg,
        evaluate_fn=lambda _c, _m: EvalMetrics(true_positives=19, false_positives=0, false_negatives=1),
        warmup_n=1,
    )
    assert ok.switched is True
    assert swap.active_path == Path(cand)
