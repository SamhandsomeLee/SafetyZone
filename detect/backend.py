"""Inference backend abstraction (platform adapters implement this)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path

import numpy as np

from detect.letterbox import DEFAULT_INPUT_SIZE


class BackendKind(str, Enum):
    TENSORRT = "tensorrt"
    ONNX = "onnx"


class InferBackend(ABC):
    """Load a model and run raw YOLO inference (postprocess stays in core)."""

    input_size: int = DEFAULT_INPUT_SIZE

    @abstractmethod
    def load(self, model_path: str | Path) -> None:
        """Load engine / ONNX session from disk."""

    @abstractmethod
    def infer_batch(self, batch: np.ndarray) -> np.ndarray:
        """Run inference on NCHW float32 batch (1, 3, H, W)."""

    def infer_raw(self, bgr: np.ndarray) -> np.ndarray:
        """Letterbox + infer; returns raw YOLO output in letterbox space."""
        from detect.letterbox import preprocess_bgr

        batch, _meta = preprocess_bgr(bgr, input_size=self.input_size)
        return self.infer_batch(batch)

    @abstractmethod
    def warmup(self, n: int = 3) -> None:
        """Run dummy inferences to allocate GPU resources."""

    @abstractmethod
    def close(self) -> None:
        """Release GPU / file handles."""

    def __enter__(self) -> InferBackend:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def create_backend(kind: str | BackendKind, model_path: str | Path, **kwargs: object) -> InferBackend:
    """Factory for inference backends."""
    key = BackendKind(kind.lower())

    if key is BackendKind.TENSORRT:
        from detect.trt_backend import TensorRTBackend

        backend = TensorRTBackend(input_size=int(kwargs.get("input_size", DEFAULT_INPUT_SIZE)))
        backend.load(model_path)
        return backend

    if key is BackendKind.ONNX:
        from detect.onnx_backend import OnnxBackend

        backend = OnnxBackend(input_size=int(kwargs.get("input_size", DEFAULT_INPUT_SIZE)))
        backend.load(model_path)
        return backend

    raise ValueError(f"unsupported backend kind: {kind!r}")
