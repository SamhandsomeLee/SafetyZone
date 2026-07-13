"""Background inference thread (detection must not run on UI thread)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.camera_source import open_source_for_station
from app.frame_bridge import FramePayload
from app.pipeline import StationRunner, resolve_station
from app.visualize import render_monitor_frame
from camera.base import SourceType
from core.config import AppConfig, load_config
from detect.backend import create_backend
from record.event_recorder import EventRecorder

logger = logging.getLogger(__name__)


class InferenceWorker(QThread):
    """Read frames, run TRT pipeline, emit annotated payloads to the UI."""

    frame_ready = Signal(object)
    error_occurred = Signal(str)
    running_changed = Signal(bool)
    source_opened = Signal(str, str, bool, str)  # camera_id, source_type, degraded, message

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
        self._config_path: Path | None = None
        if isinstance(config, AppConfig):
            self._config = config
        else:
            self._config_path = Path(config)
            self._config = load_config(self._config_path)
        self._engine_path = Path(engine_path)
        self._station_id = station_id
        self._project_root = project_root or Path.cwd()
        self._stop_requested = False
        self._runner: StationRunner | None = None

    def request_stop(self) -> None:
        self._stop_requested = True

    def reload_config(self, config: AppConfig | None = None) -> None:
        """Apply updated param groups while the worker loop is running."""
        if config is not None:
            self._config = config
        elif self._config_path is not None:
            self._config = load_config(self._config_path)
        else:
            return

        if self._runner is not None:
            _, param = resolve_station(self._config, self._station_id)
            self._runner.param = param
            logger.info("inference worker reloaded param group %s", param.id)

    def run(self) -> None:
        self._stop_requested = False
        self.running_changed.emit(True)
        try:
            self._run_loop()
        except Exception as exc:  # pragma: no cover - surfaced to UI
            logger.exception("inference worker failed")
            self.error_occurred.emit(str(exc))
        finally:
            self.running_changed.emit(False)

    def _run_loop(self) -> None:
        station, param = resolve_station(self._config, self._station_id)
        self._runner = StationRunner(station=station, param=param)
        runner = self._runner

        opened = open_source_for_station(self._config, station, root=self._project_root)
        stream = opened.stream
        effective = opened.effective

        if not self._engine_path.is_file():
            raise FileNotFoundError(f"engine not found: {self._engine_path}")

        stream.start()
        self.source_opened.emit(
            effective.id,
            str(effective.source_type),
            opened.degraded,
            opened.message or "",
        )
        if opened.degraded:
            logger.warning("%s", opened.message)

        recorder = EventRecorder(
            config=self._config.record,
            output_dir=self._project_root / "records",
            station_id=station.id,
            save_on_slow=False,
        )

        frame_index = 0
        run_t0 = time.perf_counter()
        is_video = stream.source_type == SourceType.VIDEO_FILE
        video_loop = bool(getattr(effective, "loop", True)) if is_video else True

        try:
            with create_backend("tensorrt", self._engine_path) as backend:
                backend.warmup(2)
                while not self._stop_requested:
                    t0 = time.perf_counter()
                    frame = stream.get_frame()
                    if frame is None:
                        # USB / degraded wait; video EOF only ends when not looping.
                        if is_video and not video_loop:
                            break
                        continue

                    param = runner.param
                    ref_size = (param.ref_width, param.ref_height)

                    signal, zone_hit, detections, fault = runner.process(
                        frame,
                        backend=backend,
                        frame_index=frame_index,
                        timestamp_ms=frame_index * (1000.0 / 15.0),
                    )
                    # Snapshot on STOP rising edge; never block the loop on I/O errors.
                    try:
                        event = recorder.on_signal(signal, frame)
                        if event is not None:
                            logger.info(
                                "alarm snapshot saved station=%s kind=%s path=%s",
                                event.station_id,
                                event.kind,
                                event.path,
                            )
                    except Exception:  # pragma: no cover - keep inference alive
                        logger.exception("event recorder failed")

                    infer_ms = (time.perf_counter() - t0) * 1000.0
                    elapsed = time.perf_counter() - run_t0
                    process_fps = (frame_index + 1) / elapsed if elapsed > 0 else 0.0

                    overlay = render_monitor_frame(
                        frame,
                        detections=detections,
                        slow_polygon=param.slow_polygon,
                        stop_polygon=param.stop_polygon,
                        ref_size=ref_size,
                        anchor_mode=station.detect_mode,
                        min_overlap=param.min_overlap,
                        signal=signal,
                        frame_index=frame_index,
                        infer_ms=infer_ms,
                        process_fps=process_fps,
                        fault=fault,
                        draw_zone_polygons=False,
                    )

                    payload = FramePayload(
                        station_id=station.id,
                        frame_index=frame_index,
                        signal=signal,
                        zone_hit=zone_hit,
                        detections=tuple(detections),
                        infer_ms=infer_ms,
                        process_fps=process_fps,
                        fault=fault,
                        overlay_bgr=overlay,
                    )
                    self.frame_ready.emit(payload)
                    frame_index += 1
        finally:
            stream.stop()
            recorder.reset()
            self._runner = None
