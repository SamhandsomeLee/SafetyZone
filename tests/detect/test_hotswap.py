"""Unit tests for detect.hotswap (mock backends, no TensorRT required)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest

from detect.backend import BackendKind, InferBackend
from detect.hotswap import EngineHotSwap, create_hotswap
from detect.letterbox import DEFAULT_INPUT_SIZE


class TrackingBackend(InferBackend):
    """Fake backend that records load/infer/warmup and can simulate slow infer."""

    _instances: dict[str, TrackingBackend] = {}

    def __init__(
        self,
        *,
        tag: str,
        input_size: int = DEFAULT_INPUT_SIZE,
        infer_delay_s: float = 0.0,
        output: np.ndarray | None = None,
    ) -> None:
        self.tag = tag
        self.input_size = input_size
        self.infer_delay_s = infer_delay_s
        self._output = output if output is not None else np.zeros((1, 84, 8400), dtype=np.float32)
        self.loaded_path: Path | None = None
        self.infer_count = 0
        self.warmup_count = 0
        self.infer_in_progress = False
        self.closed = False
        TrackingBackend._instances[tag] = self

    @property
    def engine_path(self) -> Path | None:
        return self.loaded_path

    def load(self, model_path: str | Path) -> None:
        self.loaded_path = Path(model_path)
        self.closed = False

    def infer_batch(self, batch: np.ndarray) -> np.ndarray:
        self.infer_in_progress = True
        self.infer_count += 1
        try:
            if self.infer_delay_s:
                time.sleep(self.infer_delay_s)
            return self._output
        finally:
            self.infer_in_progress = False

    def warmup(self, n: int = 3) -> None:
        self.warmup_count += max(1, n)

    def close(self) -> None:
        self.closed = True
        self.loaded_path = None


def _factory_for(*tags: str) -> dict[str, TrackingBackend]:
    tag_iter = iter(tags)

    def factory(kind: BackendKind, path: Path, kwargs: dict) -> InferBackend:
        tag = next(tag_iter)
        backend = TrackingBackend(tag=tag, input_size=int(kwargs.get("input_size", DEFAULT_INPUT_SIZE)))
        backend.load(path)
        return backend

    return {"factory": factory}


def test_prepare_warmup_commit_swaps_active_backend():
    active = TrackingBackend(tag="active")
    active.load("models/v1.engine")
    swap = EngineHotSwap(active, backend_factory=_factory_for("candidate")["factory"])

    swap.prepare("models/v2.engine")
    assert swap.candidate_path == Path("models/v2.engine")
    assert swap.active_path == Path("models/v1.engine")
    assert not swap.candidate_ready

    swap.warmup_candidate(2)
    assert swap.candidate_ready

    committed = swap.commit()
    assert committed == Path("models/v2.engine")
    assert swap.active_path == Path("models/v2.engine")
    assert swap.previous_path == Path("models/v1.engine")
    assert swap.candidate_path is None
    assert swap.active_backend.tag == "candidate"


def test_commit_requires_warmup():
    active = TrackingBackend(tag="active")
    swap = EngineHotSwap(active, backend_factory=_factory_for("candidate")["factory"])
    swap.prepare("models/v2.engine")

    with pytest.raises(RuntimeError, match="not warmed"):
        swap.commit()


def test_rollback_restores_previous_engine():
    active = TrackingBackend(tag="active")
    active.load("models/v1.engine")
    swap = EngineHotSwap(active, backend_factory=_factory_for("candidate")["factory"])

    swap.prepare("models/v2.engine")
    swap.warmup_candidate(1)
    swap.commit()
    assert swap.active_path == Path("models/v2.engine")

    assert swap.rollback() is True
    assert swap.active_path == Path("models/v1.engine")
    assert swap.previous_path is None


def test_rollback_false_when_no_previous():
    def factory(kind: BackendKind, path: Path, kwargs: dict) -> InferBackend:
        backend = TrackingBackend(tag="only")
        backend.load(path)
        return backend

    active = TrackingBackend(tag="active")
    swap = EngineHotSwap(active, backend_factory=factory)
    assert swap.rollback() is False


def test_discard_candidate_closes_without_swap():
    active = TrackingBackend(tag="active")
    swap = EngineHotSwap(active, backend_factory=_factory_for("candidate")["factory"])

    swap.prepare("models/v2.engine")
    candidate = TrackingBackend._instances["candidate"]
    swap.discard_candidate()

    assert swap.candidate_path is None
    assert candidate.closed is True
    assert swap.active_path == active.loaded_path


def test_commit_blocks_until_infer_finishes():
    active = TrackingBackend(tag="active", infer_delay_s=0.15)
    active.load("models/v1.engine")
    swap = EngineHotSwap(active, backend_factory=_factory_for("candidate")["factory"])
    swap.prepare("models/v2.engine")
    swap.warmup_candidate(1)

    batch = np.zeros((1, 3, DEFAULT_INPUT_SIZE, DEFAULT_INPUT_SIZE), dtype=np.float32)
    infer_started = threading.Event()
    infer_done = threading.Event()
    commit_done = threading.Event()
    active_tag_during_commit: list[str] = []

    def run_infer() -> None:
        infer_started.set()
        swap.infer_batch(batch)
        infer_done.set()

    def run_commit() -> None:
        infer_started.wait(timeout=1.0)
        time.sleep(0.02)
        active_tag_during_commit.append(swap.active_backend.tag)
        swap.commit()
        commit_done.set()

    infer_thread = threading.Thread(target=run_infer)
    commit_thread = threading.Thread(target=run_commit)
    infer_thread.start()
    commit_thread.start()
    infer_thread.join(timeout=2.0)
    commit_thread.join(timeout=2.0)

    assert infer_done.is_set()
    assert commit_done.is_set()
    assert active.infer_in_progress is False
    assert active_tag_during_commit == ["active"]
    assert swap.active_backend.tag == "candidate"


def test_infer_uses_same_backend_for_entire_call():
    active = TrackingBackend(tag="active", infer_delay_s=0.05)
    swap = EngineHotSwap(active, backend_factory=_factory_for("candidate")["factory"])
    swap.prepare("models/v2.engine")
    swap.warmup_candidate(1)

    batch = np.zeros((1, 3, DEFAULT_INPUT_SIZE, DEFAULT_INPUT_SIZE), dtype=np.float32)
    swapped_mid_infer = threading.Event()

    def delayed_commit() -> None:
        time.sleep(0.02)
        swap.commit()
        swapped_mid_infer.set()

    commit_thread = threading.Thread(target=delayed_commit)
    commit_thread.start()
    swap.infer_batch(batch)
    commit_thread.join(timeout=1.0)

    assert active.infer_count == 1
    assert TrackingBackend._instances["candidate"].infer_count == 0


def test_create_hotswap_factory():
    def factory(kind: BackendKind, path: Path, kwargs: dict) -> InferBackend:
        backend = TrackingBackend(tag="boot")
        backend.load(path)
        return backend

    wrapper = create_hotswap("tensorrt", "models/boot.engine", backend_factory=factory)
    assert wrapper.active_path == Path("models/boot.engine")
    wrapper.close()
