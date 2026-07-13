"""SafetyZone main window (Sprint UI-1 Bootstrap skeleton)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.frame_bridge import FramePayload
from app.pipeline import resolve_station
from app.run_controller import RunController
from app.signal_display import STOCK_BADGE, plc_sim_value, signal_label
from core.config import AppConfig, ConfigError, get_param_group, load_config, save_config, validate_config
from ui.camera_panel import CameraPanel
from ui.log_panel import LogPanel
from ui.station_view import StationView

logger = logging.getLogger(__name__)

UI_FPS_LIMIT = 15.0


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        config_path: Path,
        engine_path: Path,
        project_root: Path,
        station_id: str | None = None,
    ) -> None:
        super().__init__()
        self._config_path = config_path
        self._engine_path = engine_path
        self._project_root = project_root
        self._station_id = station_id
        self._config: AppConfig = load_config(config_path)

        self._last_ui_frame_t = 0.0
        self._latest_payload: FramePayload | None = None

        self.setWindowTitle(f"SafetyZone · {STOCK_BADGE}")
        self.resize(1280, 800)

        self._run = RunController(
            config=config_path,
            engine_path=engine_path,
            station_id=station_id,
            project_root=project_root,
            parent=self,
        )

        self._build_menus()
        self._build_toolbar()
        self._build_central()
        self._build_status_bar()
        self._log_panel.install()

        logger.info("main window ready config=%s engine=%s", config_path, engine_path)

    def _build_menus(self) -> None:
        menubar = self.menuBar()
        for title in ("系统", "工位", "相机", "PLC", "文件", "查看"):
            menu = menubar.addMenu(title)
            stub = QAction("（Sprint UI-2+）", self)
            stub.setEnabled(False)
            menu.addAction(stub)

    def _build_toolbar(self) -> None:
        bar = QToolBar("主工具栏")
        bar.setMovable(False)
        self.addToolBar(bar)

        station_combo = QComboBox()
        for st in self._config.stations:
            if st.enabled:
                station_combo.addItem(st.id, st.id)
        station_combo.setEnabled(False)
        bar.addWidget(QLabel(" 工位: "))
        bar.addWidget(station_combo)

        bar.addSeparator()
        bar.addWidget(QLabel("  用户: 管理员  "))
        bar.addSeparator()

        self._btn_start = QPushButton("全部开始")
        self._btn_start.clicked.connect(self._on_start)
        bar.addWidget(self._btn_start)

        self._btn_stop = QPushButton("全部停止")
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setEnabled(False)
        bar.addWidget(self._btn_stop)

        bar.addSeparator()
        calib = QPushButton("标定向导")
        calib.setEnabled(False)
        calib.setToolTip("Phase C：双目深度标定")
        bar.addWidget(calib)

        save_zone = QPushButton("保存当前工位划区")
        save_zone.setToolTip("将 slow/stop 多边形写入 config（相对 ref 坐标）")
        save_zone.clicked.connect(self._on_save_zones)
        self._btn_save_zone = save_zone
        bar.addWidget(save_zone)

        badge = QLabel(f"  {STOCK_BADGE}  ")
        badge.setObjectName("stockBadge")
        bar.addWidget(badge)

    def _build_central(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)

        body = QHBoxLayout()
        self._camera_panel = CameraPanel(
            config=self._config,
            project_root=self._project_root,
        )
        self._camera_panel.setFixedWidth(240)
        body.addWidget(self._camera_panel)

        tabs = QTabWidget()
        overview = QLabel("运行总览（Sprint 2.5 多工位缩略图）")
        overview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tabs.addTab(overview, "运行总览")

        station, param = resolve_station(self._config, self._station_id)
        self._station_view = StationView(station_name=station.id, param_group=param)
        tabs.addTab(self._station_view, f"{station.id} · 监控")
        tabs.setCurrentIndex(1)
        body.addWidget(tabs, stretch=1)
        root.addLayout(body, stretch=1)

        self._log_panel = LogPanel()
        self._log_panel.setMaximumHeight(160)
        root.addWidget(self._log_panel)

    def _build_status_bar(self) -> None:
        sb = self.statusBar()
        self._st_camera = QLabel("相机: 待机")
        self._st_comm = QLabel("通讯: 仿真")
        self._st_plc = QLabel("PLC: 仿真")
        self._st_program = QLabel("程序: 待启动")
        self._st_signal = QLabel("状态: —")
        for widget in (self._st_camera, self._st_comm, self._st_plc, self._st_program, self._st_signal):
            sb.addPermanentWidget(widget)

    def _on_start(self) -> None:
        if not self._apply_editor_zones(persist=False):
            return
        self._run.reload_config(self._config)
        try:
            worker = self._run.start()
        except RuntimeError:
            return
        except Exception as exc:
            QMessageBox.critical(self, "启动失败", str(exc))
            return

        worker.frame_ready.connect(self._on_frame_ready)
        worker.error_occurred.connect(self._on_worker_error)
        worker.running_changed.connect(self._on_running_changed)

        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._st_program.setText("程序: 运行中")
        self._st_camera.setText("相机: 视频回放")
        logger.info("detection started")

    def _on_stop(self) -> None:
        self._run.stop()
        self._station_view.show_idle("已停止")
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._st_program.setText("程序: 待启动")
        self._st_signal.setText("状态: —")
        self._st_plc.setText("PLC: 仿真")
        logger.info("detection stopped")

    def _on_running_changed(self, running: bool) -> None:
        if not running and not self._btn_start.isEnabled():
            self._on_stop()

    def _on_worker_error(self, message: str) -> None:
        logger.error("worker error: %s", message)
        QMessageBox.critical(self, "检测线程错误", message)
        self._on_stop()

    def _on_frame_ready(self, payload: object) -> None:
        if not isinstance(payload, FramePayload):
            return
        now = time.perf_counter()
        if now - self._last_ui_frame_t < (1.0 / UI_FPS_LIMIT):
            return
        self._last_ui_frame_t = now
        self._latest_payload = payload
        self._station_view.update_frame(payload)

        label = signal_label(payload.signal, fault=payload.fault)
        sim = plc_sim_value(payload.signal, fault=payload.fault)
        self._st_signal.setText(f"状态: {payload.station_id} signal={payload.signal}({label})")
        self._st_plc.setText(f"PLC: 拟写入 {sim}")

    def _apply_editor_zones(self, *, persist: bool) -> bool:
        """Copy ZoneEditor polygons into in-memory config; optionally save to disk."""
        slow, stop = self._station_view.get_polygons()
        if len(slow) < 3 or len(stop) < 3:
            QMessageBox.warning(
                self,
                "划区无效",
                "SLOW 与 STOP 多边形各至少需要 3 个顶点。",
            )
            return False

        try:
            station, _ = resolve_station(self._config, self._station_id)
            param = get_param_group(self._config, station.param_group_id)
            param.slow_polygon = slow
            param.stop_polygon = stop
            validate_config(self._config)
            if persist:
                save_config(self._config, self._config_path)
                self._config = load_config(self._config_path)
                _, param = resolve_station(self._config, self._station_id)
                self._station_view.set_param_group(param)
        except ConfigError as exc:
            QMessageBox.warning(self, "保存失败" if persist else "划区无效", str(exc))
            return False
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return False
        return True

    def _on_save_zones(self) -> None:
        station, _ = resolve_station(self._config, self._station_id)
        if not self._apply_editor_zones(persist=True):
            return

        self._run.reload_config(self._config)
        logger.info(
            "saved zones for station=%s param_group=%s",
            station.id,
            station.param_group_id,
        )
        QMessageBox.information(self, "保存成功", f"工位 {station.id} 划区已写入配置。")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._run.stop()
        super().closeEvent(event)
