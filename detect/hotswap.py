"""Runtime TensorRT engine hot-swap: load → warmup → atomic replace.

Designed for ``jetson_update`` to call after acceptance; not wired into the
running UI in this sprint (#27 skeleton).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from detect.backend import BackendKind, InferBackend, create_backend

logger = logging.getLogger(__name__)

BackendFactory = Callable[[BackendKind, Path, dict[str, Any]], InferBackend]


@dataclass
class _Candidate:
    backend: InferBackend
    path: Path
    warmed: bool = False


class EngineHotSwap(InferBackend):
    """Wrap an inference backend with load → warmup → atomic engine replacement.

    ``infer_batch`` / ``infer_raw`` hold an internal lock for the full call so
    ``commit()`` never swaps the active backend mid-frame.
    """

    def __init__(
        self,
        backend: InferBackend,
        *,
        lock: threading.RLock | None = None,
        backend_factory: BackendFactory | None = None,
    ) -> None:
        self._lock = lock or threading.RLock()
        self._backend_factory = backend_factory or _default_backend_factory
        self._active = backend
        self._previous: InferBackend | None = None
        self._previous_path: Path | None = _backend_path(backend)
        self._candidate: _Candidate | None = None

    @property
    def input_size(self) -> int:
        return self._active.input_size

    @input_size.setter
    def input_size(self, value: int) -> None:
        self._active.input_size = value

    @property
    def active_backend(self) -> InferBackend:
        return self._active

    @property
    def active_path(self) -> Path | None:
        return _backend_path(self._active)

    @property
    def previous_path(self) -> Path | None:
        return self._previous_path

    @property
    def candidate_path(self) -> Path | None:
        return self._candidate.path if self._candidate is not None else None

    @property
    def candidate_ready(self) -> bool:
        return self._candidate is not None and self._candidate.warmed

    def load(self, model_path: str | Path) -> None:
        """Replace the active backend (initial load or full reset, not hot-swap)."""
        with self._lock:
            self._discard_candidate_unlocked()
            self._close_previous_unlocked()
            new_backend = self._backend_factory(
                BackendKind.TENSORRT,
                Path(model_path),
                {"input_size": self.input_size},
            )
            self._active = new_backend
            self._previous = None
            self._previous_path = _backend_path(new_backend)

    def prepare(
        self,
        model_path: str | Path,
        *,
        kind: str | BackendKind = BackendKind.TENSORRT,
        **factory_kwargs: Any,
    ) -> None:
        """Load a candidate engine without affecting the active backend."""
        path = Path(model_path)
        kwargs = {"input_size": self.input_size, **factory_kwargs}
        candidate = self._backend_factory(BackendKind(kind), path, kwargs)
        with self._lock:
            self._discard_candidate_unlocked()
            self._candidate = _Candidate(backend=candidate, path=path)
        logger.info("hotswap candidate prepared: %s", path)

    def warmup_candidate(self, n: int = 3) -> None:
        """Warm up the prepared candidate before ``commit()``."""
        candidate = self._require_candidate()
        candidate.backend.warmup(n)
        candidate.warmed = True
        logger.info("hotswap candidate warmed (%d runs): %s", max(1, n), candidate.path)

    def commit(self) -> Path:
        """Atomically promote the warmed candidate to active; retain previous for rollback."""
        with self._lock:
            candidate = self._require_candidate()
            if not candidate.warmed:
                raise RuntimeError("candidate not warmed; call warmup_candidate() before commit()")

            self._close_previous_unlocked()
            self._previous = self._active
            self._previous_path = _backend_path(self._active)
            self._active = candidate.backend
            committed_path = candidate.path
            self._candidate = None
            logger.info(
                "hotswap committed: active=%s previous=%s",
                committed_path,
                self._previous_path,
            )
            return committed_path

    def discard_candidate(self) -> None:
        """Drop a prepared candidate without swapping."""
        with self._lock:
            self._discard_candidate_unlocked()

    def rollback(self) -> bool:
        """Restore the previous engine if one was retained after ``commit()``."""
        with self._lock:
            if self._previous is None:
                return False
            self._discard_candidate_unlocked()
            old_active = self._active
            self._active = self._previous
            self._previous = None
            self._previous_path = None
            old_active.close()
            logger.info("hotswap rolled back to: %s", self._previous_path)
            return True

    def infer_batch(self, batch: np.ndarray) -> np.ndarray:
        with self._lock:
            return self._active.infer_batch(batch)

    def warmup(self, n: int = 3) -> None:
        with self._lock:
            self._active.warmup(n)

    def close(self) -> None:
        with self._lock:
            self._discard_candidate_unlocked()
            self._close_previous_unlocked()
            self._active.close()

    def _require_candidate(self) -> _Candidate:
        if self._candidate is None:
            raise RuntimeError("no candidate prepared; call prepare() first")
        return self._candidate

    def _discard_candidate_unlocked(self) -> None:
        if self._candidate is None:
            return
        self._candidate.backend.close()
        self._candidate = None

    def _close_previous_unlocked(self) -> None:
        if self._previous is None:
            return
        self._previous.close()
        self._previous = None
        self._previous_path = None


def create_hotswap(
    kind: str | BackendKind,
    model_path: str | Path,
    *,
    backend_factory: BackendFactory | None = None,
    **kwargs: Any,
) -> EngineHotSwap:
    """Create a hot-swap wrapper with an initially loaded backend."""
    factory = backend_factory or _default_backend_factory
    backend = factory(BackendKind(kind), Path(model_path), kwargs)
    return EngineHotSwap(backend, backend_factory=factory)


def _default_backend_factory(kind: BackendKind, path: Path, kwargs: dict[str, Any]) -> InferBackend:
    backend = create_backend(kind, path, **kwargs)
    return backend


def _backend_path(backend: InferBackend) -> Path | None:
    engine_path = getattr(backend, "engine_path", None)
    if engine_path is not None:
        return Path(engine_path)
    load_path = getattr(backend, "_engine_path", None)
    if load_path is not None:
        return Path(load_path)
    return None
