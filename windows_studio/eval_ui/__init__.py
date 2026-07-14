"""Studio evaluation UI (#54) — recall-first metrics + miss→review jump.

Does **not** replace Jetson ``jetson_update.acceptance``.
"""

from windows_studio.eval_ui.metrics import EvalMetrics, metrics_from_counts, mock_eval_metrics
from windows_studio.eval_ui.panel import EvalPanel

__all__ = [
    "EvalMetrics",
    "EvalPanel",
    "metrics_from_counts",
    "mock_eval_metrics",
]
