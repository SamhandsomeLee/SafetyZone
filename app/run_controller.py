"""Start/stop inference worker for the main window."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject

from app.inference_worker import InferenceWorker
from core.config import AppConfig

logger = logging.getLogger(__name__)


class RunController(QObject):
    """Owns the inference worker lifecycle."""

    def __init__(
        self,
        *,
        config: AppConfig | Path | str,
        engine_path: Path | str,
        station_id: str | None = None,
        project_root: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._engine_path = engine_path
        self._station_id = station_id
        self._project_root = project_root
        self._worker: InferenceWorker | None = None

    @property
    def worker(self) -> InferenceWorker | None:
        return self._worker

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def start(self) -> InferenceWorker:
        if self.is_running:
            raise RuntimeError("detection already running")
        self._worker = InferenceWorker(
            config=self._config,
            engine_path=self._engine_path,
            station_id=self._station_id,
            project_root=self._project_root,
            parent=self,
        )
        self._worker.start()
        logger.info("inference worker started")
        return self._worker

    def stop(self, *, wait_ms: int = 8000) -> None:
        worker = self._worker
        if worker is None:
            return
        if worker.isRunning():
            worker.request_stop()
            if not worker.wait(wait_ms):
                logger.warning("inference worker did not stop within %dms; terminating", wait_ms)
                worker.terminate()
                worker.wait(2000)
        self._worker = None
        logger.info("inference worker stopped")
