"""Start/stop inference worker for the main window."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject

from app.inference_worker import InferenceWorker
from core.config import AppConfig, PlcConfig, load_config
from plc.process_worker import PlcProcessGateway

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
        self._plc_gateway: PlcProcessGateway | None = None

    @property
    def worker(self) -> InferenceWorker | None:
        return self._worker

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _resolve_config(self) -> AppConfig:
        if isinstance(self._config, AppConfig):
            return self._config
        return load_config(self._config)

    def reload_config(self, config: AppConfig | Path | str) -> None:
        """Reload config; hot-update running worker param groups when possible."""
        if isinstance(config, AppConfig):
            self._config = config
            cfg = config
        else:
            self._config = Path(config)
            cfg = load_config(self._config)

        worker = self._worker
        if worker is not None:
            worker.reload_config(cfg)
        if self.is_running:
            self._restart_plc_gateway(cfg.plc)
        logger.info("run controller config reloaded")

    def reload_plc_config(self, plc: PlcConfig) -> None:
        """Apply PLC section only; restart gateway when detection is running."""
        cfg = self._resolve_config()
        if isinstance(self._config, AppConfig):
            self._config = replace(cfg, plc=plc)
        if self.is_running:
            self._restart_plc_gateway(plc)
        logger.info(
            "plc config reloaded simulate=%s enabled=%s",
            plc.simulate,
            plc.enabled,
        )

    def _restart_plc_gateway(self, plc: PlcConfig) -> None:
        self._stop_plc_gateway()
        self._start_plc_gateway(plc)

    def _start_plc_gateway(self, plc: PlcConfig) -> None:
        if not (plc.simulate or plc.enabled):
            return
        self._plc_gateway = PlcProcessGateway(plc)
        self._plc_gateway.start()

    def _stop_plc_gateway(self) -> None:
        gw = self._plc_gateway
        if gw is not None:
            gw.stop()
        self._plc_gateway = None

    def write_plc_signal(self, signal: int, *, fault: bool = False) -> None:
        """Enqueue signal write to PLC worker (non-blocking)."""
        gw = self._plc_gateway
        if gw is None or not gw.is_running:
            return
        try:
            gw.send_signal(signal, fault=fault)
        except RuntimeError:
            logger.debug("plc gateway not ready for signal write")
        except Exception:
            logger.exception("plc send_signal failed")

    def poll_plc_status(self):
        gw = self._plc_gateway
        if gw is None:
            return None
        return gw.poll_status()

    def set_station_id(self, station_id: str | None) -> None:
        """Select which station the next start() will run (ignored while running)."""
        if self.is_running:
            raise RuntimeError("cannot change station while detection is running")
        self._station_id = station_id
        logger.info("run controller station_id=%s", station_id)

    def start(self) -> InferenceWorker:
        if self.is_running:
            raise RuntimeError("detection already running")
        # Prefer in-memory AppConfig (includes unsaved editor sync / last save).
        config = self._config
        self._worker = InferenceWorker(
            config=config,
            engine_path=self._engine_path,
            station_id=self._station_id,
            project_root=self._project_root,
            parent=self,
        )
        self._worker.start()
        self._start_plc_gateway(self._resolve_config().plc)
        logger.info("inference worker started")
        return self._worker

    def stop(self, *, wait_ms: int = 8000) -> None:
        self._stop_plc_gateway()
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
