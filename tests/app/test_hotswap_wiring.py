"""App-side hotswap wiring (#50) — worker/controller hold EngineHotSwap."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from app.inference_worker import InferenceWorker
from app.run_controller import RunController
from core.config import AppConfig, ParamGroup, StationConfig
from detect.backend import BackendKind, InferBackend
from detect.hotswap import EngineHotSwap
from detect.letterbox import DEFAULT_INPUT_SIZE
from jetson_update.acceptance import AcceptanceResult, DEFAULT_RECALL_THRESHOLD


class TrackingBackend(InferBackend):
    def __init__(self, *, tag: str, input_size: int = DEFAULT_INPUT_SIZE) -> None:
        self.tag = tag
        self.input_size = input_size
        self.loaded_path: Path | None = None
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
        return None

    def close(self) -> None:
        self.closed = True


def _factory(*tags: str):
    tag_iter = iter(tags)

    def factory(kind: BackendKind, path: Path, kwargs: dict) -> InferBackend:
        del kind
        backend = TrackingBackend(tag=next(tag_iter), input_size=int(kwargs.get("input_size", DEFAULT_INPUT_SIZE)))
        backend.load(path)
        return backend

    return factory


def _pass() -> AcceptanceResult:
    return AcceptanceResult(
        passed=True,
        recall=1.0,
        reason="pass",
        threshold=DEFAULT_RECALL_THRESHOLD,
        frame_count=1,
    )


def _fail() -> AcceptanceResult:
    return AcceptanceResult(
        passed=False,
        recall=0.0,
        reason="fail",
        threshold=DEFAULT_RECALL_THRESHOLD,
        frame_count=1,
    )


def _minimal_config() -> AppConfig:
    return AppConfig(
        cameras=[],
        param_groups=[
            ParamGroup(
                id="default",
                ref_width=640,
                ref_height=480,
                slow_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
                stop_polygon=[[20, 20], [80, 20], [80, 80], [20, 80]],
            )
        ],
        stations=[
            StationConfig(
                id="station0",
                camera_id="cam0",
                param_group_id="default",
                detect_mode="person",
                enabled=True,
            )
        ],
    )


def test_worker_promote_pass_and_rollback() -> None:
    active = TrackingBackend(tag="v1")
    active.load("models/v1.engine")
    swap = EngineHotSwap(active, backend_factory=_factory("v2"))

    worker = InferenceWorker(config=_minimal_config(), engine_path="models/v1.engine")
    worker._hotswap = swap  # simulate live loop holding EngineHotSwap

    ok = worker.promote_engine("models/v2.engine", acceptance=_pass(), warmup_n=1)
    assert ok.switched is True
    assert worker.hotswap is not None
    assert worker.hotswap.active_path == Path("models/v2.engine")

    rb = worker.rollback_engine()
    assert rb.switched is True
    assert worker.hotswap.active_path == Path("models/v1.engine")


def test_worker_promote_fail_keeps_old() -> None:
    active = TrackingBackend(tag="v1")
    active.load("models/v1.engine")
    swap = EngineHotSwap(active, backend_factory=_factory("v2"))

    worker = InferenceWorker(config=_minimal_config(), engine_path="models/v1.engine")
    worker._hotswap = swap

    result = worker.promote_engine("models/v2.engine", acceptance=_fail())
    assert result.switched is False
    assert swap.active_path == Path("models/v1.engine")
    assert swap.active_backend.tag == "v1"


def test_worker_without_live_hotswap_refuses() -> None:
    worker = InferenceWorker(config=_minimal_config(), engine_path="models/v1.engine")
    result = worker.promote_engine("models/v2.engine", acceptance=_pass())
    assert result.switched is False
    assert "no live" in result.reason


def test_run_controller_delegates_when_running() -> None:
    active = TrackingBackend(tag="v1")
    active.load("models/v1.engine")
    swap = EngineHotSwap(active, backend_factory=_factory("v2"))

    ctrl = RunController(config=_minimal_config(), engine_path="models/v1.engine")
    worker = InferenceWorker(config=_minimal_config(), engine_path="models/v1.engine")
    worker._hotswap = swap
    ctrl._worker = worker
    # Pretend QThread is running without starting Qt event loop.
    worker.isRunning = MagicMock(return_value=True)  # type: ignore[method-assign]

    ok = ctrl.promote_engine("models/v2.engine", acceptance=_pass(), warmup_n=1)
    assert ok.switched is True
    assert ctrl.engine_path == Path("models/v2.engine")

    fail = ctrl.promote_engine("models/v3.engine", acceptance=_fail())
    assert fail.switched is False
    assert ctrl.engine_path == Path("models/v2.engine")

    rb = ctrl.rollback_engine()
    assert rb.switched is True
    assert ctrl.engine_path == Path("models/v1.engine")


def test_run_controller_refuses_when_not_running() -> None:
    ctrl = RunController(config=_minimal_config(), engine_path="models/v1.engine")
    result = ctrl.promote_engine("models/v2.engine", acceptance=_pass())
    assert result.switched is False
    assert "not running" in result.reason
