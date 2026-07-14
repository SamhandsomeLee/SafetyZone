"""Training progress events and interruptible dry-run simulation (#54)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from windows_studio.train.trainer import TrainConfig, TrainResult, run_training

ProgressCallback = Callable[["TrainProgress"], None]


@dataclass
class TrainProgress:
    """One epoch (or terminal) progress snapshot for the GUI."""

    epoch: int
    total_epochs: int
    loss: float
    eta_seconds: float | None = None
    message: str = ""
    finished: bool = False
    cancelled: bool = False
    result: TrainResult | None = None

    @property
    def fraction(self) -> float:
        if self.total_epochs <= 0:
            return 0.0
        return min(1.0, max(0.0, self.epoch / self.total_epochs))


@dataclass
class InterruptibleTrainSession:
    """Runs a simulated epoch loop then ``run_training`` (dry-run by default).

    The GUI can call ``request_cancel`` from the UI thread; the worker checks
    the event between epochs.
    """

    config: TrainConfig
    force_dry_run: bool = True
    epoch_sleep_s: float = 0.05
    _cancel: threading.Event = field(default_factory=threading.Event, init=False)

    def request_cancel(self) -> None:
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self, on_progress: ProgressCallback | None = None) -> TrainProgress:
        """Blocking run; emit progress each epoch. Safe to call from a QThread."""
        total = max(1, int(self.config.epochs))
        losses: list[float] = []
        t0 = time.monotonic()

        for epoch in range(1, total + 1):
            if self._cancel.is_set():
                prog = TrainProgress(
                    epoch=epoch - 1,
                    total_epochs=total,
                    loss=losses[-1] if losses else 0.0,
                    eta_seconds=0.0,
                    message="训练已中断",
                    finished=True,
                    cancelled=True,
                )
                if on_progress:
                    on_progress(prog)
                return prog

            # Simple decreasing loss curve for dry-run / UI smoke (not real YOLO).
            loss = max(0.05, 1.2 / epoch + 0.15)
            losses.append(loss)
            elapsed = time.monotonic() - t0
            remaining = (elapsed / epoch) * (total - epoch) if epoch < total else 0.0
            prog = TrainProgress(
                epoch=epoch,
                total_epochs=total,
                loss=loss,
                eta_seconds=remaining,
                message=f"epoch {epoch}/{total}",
            )
            if on_progress:
                on_progress(prog)
            if epoch < total and self.epoch_sleep_s > 0:
                # Sleep in small slices so cancel is responsive.
                deadline = time.monotonic() + self.epoch_sleep_s
                while time.monotonic() < deadline:
                    if self._cancel.is_set():
                        break
                    time.sleep(min(0.02, deadline - time.monotonic()))

        if self._cancel.is_set():
            prog = TrainProgress(
                epoch=total,
                total_epochs=total,
                loss=losses[-1] if losses else 0.0,
                eta_seconds=0.0,
                message="训练已中断",
                finished=True,
                cancelled=True,
            )
            if on_progress:
                on_progress(prog)
            return prog

        # Ensure dataset layout exists for dry-run artifact writer.
        train_images = self.config.dataset_dir / "train" / "images"
        if not train_images.is_dir():
            train_images.mkdir(parents=True, exist_ok=True)
            (train_images / "placeholder.jpg").write_bytes(b"placeholder")
            labels = self.config.dataset_dir / "train" / "labels"
            labels.mkdir(parents=True, exist_ok=True)
            (labels / "placeholder.txt").write_text(
                "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
            )

        result = run_training(self.config, force_dry_run=self.force_dry_run)
        final = TrainProgress(
            epoch=total,
            total_epochs=total,
            loss=losses[-1] if losses else 0.0,
            eta_seconds=0.0,
            message=result.message,
            finished=True,
            cancelled=False,
            result=result,
        )
        if on_progress:
            on_progress(final)
        return final


def format_eta(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    m, rem = divmod(s, 60)
    if m < 60:
        return f"{m}m{rem:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def default_train_config(workspace: Path, *, epochs: int = 5) -> TrainConfig:
    return TrainConfig(
        dataset_dir=workspace / "dataset",
        runs_dir=workspace / "runs",
        epochs=epochs,
    )
