"""Optional ONNX Runtime backend for Win CPU/GPU smoke tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from detect.backend import InferBackend
from detect.letterbox import DEFAULT_INPUT_SIZE, preprocess_bgr

try:
    import onnxruntime as ort
except ImportError:  # pragma: no cover
    ort = None  # type: ignore[assignment]


class OnnxBackend(InferBackend):
    """ONNX Runtime session wrapper (optional dev / regression backend)."""

    def __init__(self, *, input_size: int = DEFAULT_INPUT_SIZE) -> None:
        self.input_size = input_size
        self._session: object | None = None
        self._input_name: str | None = None
        self._output_name: str | None = None

    def load(self, model_path: str | Path) -> None:
        if ort is None:
            raise RuntimeError("onnxruntime is not installed")

        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"ONNX model not found: {path}")

        self.close()
        session = ort.InferenceSession(str(path), providers=_select_providers())
        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if not inputs or not outputs:
            raise RuntimeError(f"invalid ONNX model: {path}")

        self._session = session
        self._input_name = inputs[0].name
        self._output_name = outputs[0].name

    def infer_batch(self, batch: np.ndarray) -> np.ndarray:
        if self._session is None or self._input_name is None or self._output_name is None:
            raise RuntimeError("backend not loaded; call load() first")

        outputs = self._session.run([self._output_name], {self._input_name: batch})
        return outputs[0]

    def infer_raw(self, bgr: np.ndarray) -> np.ndarray:
        batch, _meta = preprocess_bgr(bgr, input_size=self.input_size)
        return self.infer_batch(batch)

    def warmup(self, n: int = 3) -> None:
        dummy = np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8)
        for _ in range(max(1, n)):
            self.infer_raw(dummy)

    def close(self) -> None:
        self._session = None
        self._input_name = None
        self._output_name = None


def _select_providers() -> list[str]:
    available = ort.get_available_providers()
    if "CUDAExecutionProvider" in available:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]
