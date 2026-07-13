"""TensorRT FP16 inference backend for Jetson."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from detect.backend import InferBackend
from detect.letterbox import DEFAULT_INPUT_SIZE, preprocess_bgr

try:
    import tensorrt as trt
except ImportError:  # pragma: no cover - Win dev machines
    trt = None  # type: ignore[assignment]

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]


class TensorRTBackend(InferBackend):
    """Deserialize a TensorRT engine and run YOLOv8 inference."""

    def __init__(self, *, input_size: int = DEFAULT_INPUT_SIZE) -> None:
        self.input_size = input_size
        self._engine_path: Path | None = None
        self._logger: object | None = None
        self._runtime: object | None = None
        self._engine: object | None = None
        self._context: object | None = None
        self._input_name: str | None = None
        self._output_name: str | None = None
        self._input_tensor: object | None = None
        self._output_tensor: object | None = None
        self._stream: object | None = None
        self._pin_batch: object | None = None

    @property
    def engine_path(self) -> Path | None:
        """Path of the loaded engine (``None`` when closed)."""
        return self._engine_path

    def load(self, model_path: str | Path) -> None:
        if trt is None:
            raise RuntimeError("tensorrt is not installed")
        if torch is None or not torch.cuda.is_available():
            raise RuntimeError("PyTorch with CUDA is required for TensorRT backend on Jetson")

        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(f"TensorRT engine not found: {path}")

        self.close()

        logger = trt.Logger(trt.Logger.WARNING)
        runtime = trt.Runtime(logger)
        with path.open("rb") as handle:
            engine = runtime.deserialize_cuda_engine(handle.read())
        if engine is None:
            raise RuntimeError(f"failed to deserialize TensorRT engine: {path}")

        context = engine.create_execution_context()
        input_name, output_name = _io_tensor_names(engine)
        context.set_input_shape(input_name, (1, 3, self.input_size, self.input_size))

        input_tensor = _allocate_tensor(engine, context, input_name, torch.float32)
        output_tensor = _allocate_tensor(engine, context, output_name, torch.float32)
        stream = torch.cuda.Stream()
        pin_shape = (1, 3, self.input_size, self.input_size)
        pin_batch = torch.empty(pin_shape, dtype=torch.float32, pin_memory=True)

        self._engine_path = path
        self._logger = logger
        self._runtime = runtime
        self._engine = engine
        self._context = context
        self._input_name = input_name
        self._output_name = output_name
        self._input_tensor = input_tensor
        self._output_tensor = output_tensor
        self._stream = stream
        self._pin_batch = pin_batch

    def infer_batch(self, batch: np.ndarray) -> np.ndarray:
        if self._context is None or self._input_tensor is None or self._output_tensor is None:
            raise RuntimeError("backend not loaded; call load() first")

        if not batch.flags["C_CONTIGUOUS"]:
            batch = np.ascontiguousarray(batch)
        self._pin_batch.copy_(torch.from_numpy(batch))
        self._input_tensor.copy_(self._pin_batch, non_blocking=True)

        context = self._context
        context.set_tensor_address(self._input_name, int(self._input_tensor.data_ptr()))
        context.set_tensor_address(self._output_name, int(self._output_tensor.data_ptr()))

        ok = context.execute_async_v3(self._stream.cuda_stream)
        if not ok:
            raise RuntimeError("TensorRT execute_async_v3 failed")
        self._stream.synchronize()

        return self._output_tensor.detach().cpu().numpy()

    def infer_raw(self, bgr: np.ndarray) -> np.ndarray:
        batch, _meta = preprocess_bgr(bgr, input_size=self.input_size)
        return self.infer_batch(batch)

    def warmup(self, n: int = 3) -> None:
        dummy = np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8)
        for _ in range(max(1, n)):
            self.infer_raw(dummy)

    def close(self) -> None:
        self._engine_path = None
        self._logger = None
        self._runtime = None
        self._engine = None
        self._context = None
        self._input_name = None
        self._output_name = None
        self._input_tensor = None
        self._output_tensor = None
        self._stream = None
        self._pin_batch = None


def _io_tensor_names(engine: object) -> tuple[str, str]:
    input_name: str | None = None
    output_name: str | None = None
    for index in range(engine.num_io_tensors):
        name = engine.get_tensor_name(index)
        mode = engine.get_tensor_mode(name)
        if mode == trt.TensorIOMode.INPUT:
            input_name = name
        elif mode == trt.TensorIOMode.OUTPUT:
            output_name = name
    if not input_name or not output_name:
        raise RuntimeError("engine must expose one input and one output tensor")
    return input_name, output_name


def _allocate_tensor(engine: object, context: object, name: str, torch_dtype: object) -> object:
    trt_dtype = engine.get_tensor_dtype(name)
    np_dtype = trt.nptype(trt_dtype)
    torch_type = torch.from_numpy(np.array(0, dtype=np_dtype)).dtype
    shape = tuple(context.get_tensor_shape(name))
    return torch.empty(shape, dtype=torch_type, device="cuda")
