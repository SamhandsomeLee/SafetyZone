"""Train GUI panel: progress / ETA / loss curve / interrupt (#54)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from windows_studio.train.progress import (
    InterruptibleTrainSession,
    TrainProgress,
    default_train_config,
    format_eta,
)
from windows_studio.train.trainer import TrainConfig


class LossCurveWidget(QWidget):
    """Minimal QPainter polyline for loss history (no matplotlib)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._losses: list[float] = []
        self.setMinimumHeight(120)
        self.setMinimumWidth(160)

    def set_losses(self, losses: list[float]) -> None:
        self._losses = list(losses)
        self.update()

    def clear(self) -> None:
        self._losses.clear()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt API
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e293b"))
        painter.setPen(QPen(QColor("#64748b")))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if len(self._losses) < 2:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "loss 曲线")
            painter.end()
            return

        pad = 8
        w = max(1, self.width() - 2 * pad)
        h = max(1, self.height() - 2 * pad)
        lo = min(self._losses)
        hi = max(self._losses)
        span = hi - lo if hi > lo else 1.0
        n = len(self._losses)
        points = []
        for i, loss in enumerate(self._losses):
            x = pad + int(i * (w - 1) / (n - 1))
            y = pad + int((1.0 - (loss - lo) / span) * (h - 1))
            points.append((x, y))

        pen = QPen(QColor("#38bdf8"))
        pen.setWidth(2)
        painter.setPen(pen)
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            painter.drawLine(x0, y0, x1, y1)
        painter.end()


class _TrainWorker(QObject):
    progress = Signal(object)  # TrainProgress
    finished = Signal(object)  # TrainProgress

    def __init__(self, session: InterruptibleTrainSession) -> None:
        super().__init__()
        self._session = session

    @Slot()
    def run(self) -> None:
        def _cb(prog: TrainProgress) -> None:
            self.progress.emit(prog)

        final = self._session.run(on_progress=_cb)
        self.finished.emit(final)


class TrainPanel(QWidget):
    """Right-pane training controls: start / stop / epoch·ETA·loss + curve."""

    training_finished = Signal(object)  # TrainProgress
    status_message = Signal(str)

    def __init__(
        self,
        workspace: Path,
        *,
        epochs: int = 5,
        force_dry_run: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._epochs = epochs
        self._force_dry_run = force_dry_run
        self._session: InterruptibleTrainSession | None = None
        self._thread: QThread | None = None
        self._worker: _TrainWorker | None = None
        self._losses: list[float] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("训练")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)

        self._epoch_label = QLabel("epoch: — / —")
        self._eta_label = QLabel("ETA: —")
        self._loss_label = QLabel("loss: —")
        self._gpu_label = QLabel(
            "GPU: dry-run（无 CUDA 时写占位产物）" if force_dry_run else "GPU: 尝试本机 CUDA"
        )
        for lab in (self._epoch_label, self._eta_label, self._loss_label, self._gpu_label):
            lab.setWordWrap(True)
            layout.addWidget(lab)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        layout.addWidget(self._bar)

        self._curve = LossCurveWidget()
        layout.addWidget(self._curve)

        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("开始训练")
        self._start_btn.clicked.connect(self.start_training)
        self._stop_btn = QPushButton("中断")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.request_cancel)
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._stop_btn)
        layout.addLayout(btn_row)

        hint = QLabel("进度可中断；曲线为 dry-run 占位或真实 epoch 回调。#55 增量入口另议。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(hint)
        layout.addStretch(1)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._shutdown_worker(wait_ms=3000)
        super().closeEvent(event)

    def _shutdown_worker(self, wait_ms: int = 3000) -> None:
        if self._session is not None:
            self._session.request_cancel()
        if self._thread is not None:
            if self._thread.isRunning():
                self._thread.quit()
                self._thread.wait(wait_ms)
            self._thread = None
        self._worker = None
        self._session = None
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def set_workspace(self, workspace: Path) -> None:
        self._workspace = workspace

    def set_epochs(self, epochs: int) -> None:
        self._epochs = max(1, epochs)

    def build_config(self) -> TrainConfig:
        return default_train_config(self._workspace, epochs=self._epochs)

    def start_training(self) -> None:
        if self.is_running:
            return
        self._losses.clear()
        self._curve.clear()
        self._bar.setValue(0)
        config = self.build_config()
        self._session = InterruptibleTrainSession(
            config=config,
            force_dry_run=self._force_dry_run,
            epoch_sleep_s=0.05,
        )
        self._thread = QThread()
        self._worker = _TrainWorker(self._session)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self.status_message.emit("训练中…")
        self._thread.start()

    def request_cancel(self) -> None:
        if self._session is not None:
            self._session.request_cancel()
            self.status_message.emit("正在中断训练…")
            self._stop_btn.setEnabled(False)

    @Slot(object)
    def _on_progress(self, prog: TrainProgress) -> None:
        if prog.cancelled and prog.finished:
            self._epoch_label.setText(
                f"epoch: {prog.epoch} / {prog.total_epochs}（已中断）"
            )
            self._loss_label.setText(f"loss: {prog.loss:.4f}")
            self._bar.setValue(int(prog.fraction * 100))
            return
        if prog.epoch > 0 and not prog.finished:
            if len(self._losses) < prog.epoch:
                self._losses.append(prog.loss)
            elif self._losses:
                self._losses[-1] = prog.loss
            self._curve.set_losses(self._losses)
        self._epoch_label.setText(f"epoch: {prog.epoch} / {prog.total_epochs}")
        self._eta_label.setText(f"ETA: {format_eta(prog.eta_seconds)}")
        self._loss_label.setText(f"loss: {prog.loss:.4f}")
        self._bar.setValue(int(prog.fraction * 100))

    @Slot(object)
    def _on_finished(self, prog: TrainProgress) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        if prog.cancelled:
            self._epoch_label.setText(
                f"epoch: {prog.epoch} / {prog.total_epochs}（已中断）"
            )
            self.status_message.emit("训练已中断")
        else:
            self._bar.setValue(100)
            self.status_message.emit(prog.message or "训练完成")
        self.training_finished.emit(prog)

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
        self._session = None
