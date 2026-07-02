"""Inference adapters: letterbox, backend factory, TensorRT / ONNX."""

from detect.backend import BackendKind, InferBackend, create_backend
from detect.letterbox import LetterboxMeta, letterbox, preprocess_bgr, scale_boxes_xyxy

__all__ = [
    "BackendKind",
    "InferBackend",
    "LetterboxMeta",
    "create_backend",
    "letterbox",
    "preprocess_bgr",
    "scale_boxes_xyxy",
]
