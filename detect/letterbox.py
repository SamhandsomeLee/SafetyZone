"""Letterbox preprocessing (Ultralytics-compatible) for YOLO inference."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_INPUT_SIZE = 640
DEFAULT_PAD_COLOR = (114, 114, 114)


@dataclass(frozen=True)
class LetterboxMeta:
    """Metadata to map detections from letterbox space back to the source frame."""

    ratio: float
    pad_w: float
    pad_h: float
    input_size: int
    orig_width: int
    orig_height: int


def letterbox(
    image: np.ndarray,
    new_shape: int = DEFAULT_INPUT_SIZE,
    pad_color: tuple[int, int, int] = DEFAULT_PAD_COLOR,
) -> tuple[np.ndarray, LetterboxMeta]:
    """
    Resize with unchanged aspect ratio and pad to a square.

    Returns BGR uint8 image (new_shape, new_shape, 3) and mapping metadata.
    """
    import cv2

    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"expected BGR image HxWx3, got shape {image.shape}")

    orig_h, orig_w = image.shape[:2]
    ratio = min(new_shape / orig_h, new_shape / orig_w)
    new_unpad_w = int(round(orig_w * ratio))
    new_unpad_h = int(round(orig_h * ratio))

    resized = cv2.resize(image, (new_unpad_w, new_unpad_h), interpolation=cv2.INTER_LINEAR)

    pad_w = (new_shape - new_unpad_w) / 2.0
    pad_h = (new_shape - new_unpad_h) / 2.0
    top = int(round(pad_h - 0.1))
    bottom = int(round(pad_h + 0.1))
    left = int(round(pad_w - 0.1))
    right = int(round(pad_w + 0.1))

    padded = cv2.copyMakeBorder(
        resized,
        top,
        bottom,
        left,
        right,
        cv2.BORDER_CONSTANT,
        value=pad_color,
    )

    meta = LetterboxMeta(
        ratio=ratio,
        pad_w=pad_w,
        pad_h=pad_h,
        input_size=new_shape,
        orig_width=orig_w,
        orig_height=orig_h,
    )
    return padded, meta


class BatchBuffer:
    """Reusable NCHW batch buffer for letterbox preprocess (avoids per-frame alloc)."""

    __slots__ = ("input_size", "batch", "_boxed")

    def __init__(self, input_size: int = DEFAULT_INPUT_SIZE) -> None:
        self.input_size = input_size
        self.batch = np.empty((1, 3, input_size, input_size), dtype=np.float32)
        self._boxed = np.empty((input_size, input_size, 3), dtype=np.uint8)


def preprocess_bgr_into(
    image: np.ndarray,
    buffer: BatchBuffer,
) -> LetterboxMeta:
    """Letterbox + normalize into ``buffer.batch`` without new allocations."""
    meta = letterbox_into(image, buffer._boxed, new_shape=buffer.input_size)
    chw = buffer._boxed.transpose(2, 0, 1)
    np.multiply(chw, 1.0 / 255.0, out=buffer.batch[0], casting="unsafe")
    return meta


def letterbox_into(
    image: np.ndarray,
    out: np.ndarray,
    new_shape: int = DEFAULT_INPUT_SIZE,
    pad_color: tuple[int, int, int] = DEFAULT_PAD_COLOR,
) -> LetterboxMeta:
    """Letterbox into pre-allocated ``out`` (new_shape, new_shape, 3) uint8 buffer."""
    import cv2

    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"expected BGR image HxWx3, got shape {image.shape}")

    orig_h, orig_w = image.shape[:2]
    ratio = min(new_shape / orig_h, new_shape / orig_w)
    new_unpad_w = int(round(orig_w * ratio))
    new_unpad_h = int(round(orig_h * ratio))

    resized = cv2.resize(image, (new_unpad_w, new_unpad_h), interpolation=cv2.INTER_LINEAR)

    pad_w = (new_shape - new_unpad_w) / 2.0
    pad_h = (new_shape - new_unpad_h) / 2.0
    top = int(round(pad_h - 0.1))
    bottom = int(round(pad_h + 0.1))
    left = int(round(pad_w - 0.1))
    right = int(round(pad_w + 0.1))

    out.fill(pad_color[0])
    out[top : top + new_unpad_h, left : left + new_unpad_w] = resized

    return LetterboxMeta(
        ratio=ratio,
        pad_w=pad_w,
        pad_h=pad_h,
        input_size=new_shape,
        orig_width=orig_w,
        orig_height=orig_h,
    )


def preprocess_bgr(
    image: np.ndarray,
    *,
    input_size: int = DEFAULT_INPUT_SIZE,
) -> tuple[np.ndarray, LetterboxMeta]:
    """
    Letterbox + HWC→CHW + normalize to [0, 1] float32 contiguous NCHW batch.
    """
    boxed, meta = letterbox(image, new_shape=input_size)
    chw = boxed.transpose(2, 0, 1).astype(np.float32) / 255.0
    batch = np.ascontiguousarray(chw[np.newaxis, ...])
    return batch, meta


def scale_boxes_xyxy(
    boxes: np.ndarray,
    meta: LetterboxMeta,
) -> np.ndarray:
    """
    Map xyxy boxes from letterbox space to original image coordinates.

    `boxes` shape (N, 4): x1, y1, x2, y2.
    """
    if boxes.size == 0:
        return boxes.reshape(0, 4)

    out = boxes.astype(np.float64, copy=True)
    out[:, [0, 2]] -= meta.pad_w
    out[:, [1, 3]] -= meta.pad_h
    out[:, :4] /= meta.ratio

    out[:, [0, 2]] = out[:, [0, 2]].clip(0, meta.orig_width)
    out[:, [1, 3]] = out[:, [1, 3]].clip(0, meta.orig_height)
    return out
