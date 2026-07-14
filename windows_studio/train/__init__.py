"""Local CUDA YOLO fine-tuning wrapper (#43 + #54 GUI)."""

from windows_studio.train.progress import (
    InterruptibleTrainSession,
    TrainProgress,
    default_train_config,
    format_eta,
)
from windows_studio.train.trainer import (
    DEFAULT_BASE_MODEL,
    TrainConfig,
    TrainResult,
    cuda_available,
    load_train_result,
    run_training,
)

__all__ = [
    "DEFAULT_BASE_MODEL",
    "InterruptibleTrainSession",
    "TrainConfig",
    "TrainProgress",
    "TrainResult",
    "cuda_available",
    "default_train_config",
    "format_eta",
    "load_train_result",
    "run_training",
]
