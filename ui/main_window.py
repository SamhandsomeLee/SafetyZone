"""SafetyZone main window (Sprint UI-1 + Wave2 #35 multi-station tabs)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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
from ui.param_group_dialog import ParamGroupDialog
from ui.plc_dialog import PlcConfigDialog
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
        self._config: AppConfig = load_config(config_path)

        initial, _ = resolve_station(self._config, station_id)
        self._station_id = initial.id

        self._last_ui_frame_t = 0.0
        self._latest_payload: FramePayload | None = None
        self._station_views: dict[str, StationView] = {}
        self._station_tab_index: dict[str, int] = {}
        self._syncing_station_ui = False

        self.setWindowTitle(f"SafetyZone · {STOCK_BADGE}")
        self.resize(1280, 800)

        self._run = RunController(
            config=config_path,
            engine_path=engine_path,
            station_id=self._station_id,
            project_root=project_root,
            parent=self,
        )

        self._build_menus()
        self._build_toolbar()
        self._build_central()
        self._build_status_bar()
        self._log_panel.install()
        self._refresh_plc_status()
        self._sync_station_selectors(self._station_id)

        logger.info("main window ready config=%s engine=%s", config_path, engine_path)

    def current_station_id(self) -> str:
        return self._station_id

    def _enabled_stations(self):
        return [st for st in self._config.stations if st.enabled]

    def _build_menus(self) -> None:
        menubar = self.menuBar()
        for title in ("系统", "相机", "文件", "查看"):
            menu = menubar.addMenu(title)
            stub = QAction("（Sprint UI-2+）", self)
            stub.setEnabled(False)
            menu.addAction(stub)

        station_menu = menubar.addMenu("工位")
        param_action = QAction("参数组…", self)
        param_action.triggered.connect(self._on_open_param_group_dialog)
        station_menu.addAction(param_action)

        plc_menu = menubar.addMenu("PLC")
        plc_action = QAction("PLC 配置…", self)
        plc_action.triggered.connect(self._on_open_plc_dialog)
        plc_menu.addAction(plc_action)

    def _build_toolbar(self) -> None:
        bar = QToolBar("主工具栏")
        bar.setMovable(False)
        self.addToolBar(bar)

        self._station_combo = QComboBox()
        for st in self._enabled_stations():
            self._station_combo.addItem(st.id, st.id)
        self._station_combo.currentIndexChanged.connect(self._on_toolbar_station_changed)
        bar.addWidget(QLabel(" 工位: "))
        bar.addWidget(self._station_combo)

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

        param_btn = QPushButton("参数组…")
        param_btn.setToolTip("编辑召回组 / 精度组参数（设计 §5.3）")
        param_btn.clicked.connect(self._on_open_param_group_dialog)
        bar.addWidget(param_btn)

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
            station_id=self._station_id,
        )
        self._camera_panel.setFixedWidth(260)
        self._camera_panel.apply_requested.connect(self._on_apply_camera_binding)
        self._camera_panel.station_activated.connect(self._on_station_activated)
        body.addWidget(self._camera_panel)

        self._tabs = QTabWidget()
        overview = QLabel("运行总览（多工位缩略图 · 后续 Sprint）")
        overview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tabs.addTab(overview, "运行总览")

        for st in self._enabled_stations():
            param = get_param_group(self._config, st.param_group_id)
            view = StationView(station_name=st.id, param_group=param)
            self._station_views[st.id] = view
            idx = self._tabs.addTab(view, f"{st.id} · 监控")
            self._station_tab_index[st.id] = idx

        self._tabs.currentChanged.connect(self._on_tab_changed)
        # Prefer first station monitor tab (index 1) when stations exist.
        if self._station_id in self._station_tab_index:
            self._tabs.setCurrentIndex(self._station_tab_index[self._station_id])
        body.addWidget(self._tabs, stretch=1)
        root.addLayout(body, stretch=1)

        self._log_panel = LogPanel()
        self._log_panel.setMaximumHeight(160)
        root.addWidget(self._log_panel)

    def _station_view(self, station_id: str | None = None) -> StationView:
        sid = station_id or self._station_id
        view = self._station_views.get(sid)
        if view is None:
            # Fallback: first available view
            view = next(iter(self._station_views.values()))
        return view

    def _sync_station_selectors(self, station_id: str) -> None:
        """Keep toolbar combo / tabs / camera panel on the same station."""
        self._syncing_station_ui = True
        try:
            self._station_id = station_id
            idx = self._station_combo.findData(station_id)
            if idx >= 0:
                self._station_combo.setCurrentIndex(idx)
            tab_idx = self._station_tab_index.get(station_id)
            if tab_idx is not None and self._tabs.currentIndex() != tab_idx:
                self._tabs.setCurrentIndex(tab_idx)
            self._camera_panel.set_station(station_id)
            if not self._run.is_running:
                self._run.set_station_id(station_id)
        finally:
            self._syncing_station_ui = False

    def _on_toolbar_station_changed(self, _index: int) -> None:
        if self._syncing_station_ui:
            return
        data = self._station_combo.currentData()
        if data is None:
            return
        self._activate_station(str(data))

    def _on_tab_changed(self, index: int) -> None:
        if self._syncing_station_ui:
            return
        for sid, tab_idx in self._station_tab_index.items():
            if tab_idx == index:
                self._activate_station(sid)
                return

    def _on_station_activated(self, station_id: str) -> None:
        if self._syncing_station_ui:
            return
        self._activate_station(station_id)

    def _activate_station(self, station_id: str) -> None:
        if station_id == self._station_id and self._camera_panel.station_id == station_id:
            # Still sync RunController when idle.
            if not self._run.is_running:
                try:
                    self._run.set_station_id(station_id)
                except RuntimeError:
                    pass
            return
        logger.info("active station → %s", station_id)
        self._sync_station_selectors(station_id)

    def _build_status_bar(self) -> None:
        sb = self.statusBar()
        self._st_camera = QLabel("相机: 待机")
        self._st_comm = QLabel("通讯: 仿真")
        self._st_plc = QLabel("PLC: 仿真")
        self._st_program = QLabel("程序: 待启动")
        self._st_signal = QLabel("状态: —")
        for widget in (self._st_camera, self._st_comm, self._st_plc, self._st_program, self._st_signal):
            sb.addPermanentWidget(widget)

    def _refresh_plc_status(self, *, last_int16: int | None = None) -> None:
        plc = self._config.plc
        if plc.simulate or not plc.enabled:
            self._st_comm.setText("通讯: 仿真")
            if last_int16 is not None:
                self._st_plc.setText(f"PLC: 拟写入 {last_int16}")
            elif plc.enabled:
                self._st_plc.setText("PLC: 仿真·已启用")
            else:
                self._st_plc.setText("PLC: 仿真")
        else:
            self._st_comm.setText("通讯: 真机")
            if last_int16 is not None:
                self._st_plc.setText(f"PLC: 写入 {last_int16}")
            else:
                self._st_plc.setText("PLC: 真机·待连接")

    def _on_open_param_group_dialog(self) -> None:
        station, param = resolve_station(self._config, self._station_id)
        dlg = ParamGroupDialog(
            config=self._config,
            config_path=self._config_path,
            param_group_id=param.id,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._config = load_config(self._config_path)
        self._run.reload_config(self._config)
        # Refresh any StationView whose param_group was edited.
        saved_id = dlg.saved_param_group_id()
        for st in self._enabled_stations():
            if saved_id is not None and st.param_group_id != saved_id:
                continue
            view = self._station_views.get(st.id)
            if view is None:
                continue
            try:
                pg = get_param_group(self._config, st.param_group_id)
            except KeyError:
                continue
            view.set_param_group(pg)
        logger.info(
            "param group saved id=%s (station=%s)",
            saved_id,
            station.id,
        )
        QMessageBox.information(self, "已保存", "参数组已写入 config。")

    def _on_open_plc_dialog(self) -> None:
        dlg = PlcConfigDialog(
            config=self._config,
            config_path=self._config_path,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        saved = dlg.plc_config()
        if saved is None:
            return
        self._config = load_config(self._config_path)
        self._run.reload_plc_config(saved)
        self._refresh_plc_status()
        logger.info(
            "plc config saved simulate=%s enabled=%s ip=%s",
            saved.simulate,
            saved.enabled,
            saved.ip,
        )
        QMessageBox.information(self, "已保存", "PLC 配置已写入 config。")

    def _on_start(self) -> None:
        if not self._apply_editor_zones(persist=False):
            return
        self._run.reload_config(self._config)
        if not self._run.is_running:
            self._run.set_station_id(self._station_id)
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
        worker.source_opened.connect(self._on_source_opened)

        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._camera_panel.set_running(True)
        self._st_program.setText("程序: 运行中")
        self._st_camera.setText("相机: 启动中…")
        logger.info("detection started station=%s", self._station_id)

    def _on_stop(self) -> None:
        self._run.stop()
        for view in self._station_views.values():
            view.show_idle("已停止")
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._camera_panel.set_running(False)
        self._camera_panel.refresh(self._config)
        self._st_program.setText("程序: 待启动")
        self._st_camera.setText("相机: 待机")
        self._st_signal.setText("状态: —")
        self._refresh_plc_status()
        logger.info("detection stopped")

    def _on_source_opened(
        self,
        camera_id: str,
        source_type: str,
        degraded: bool,
        message: str,
    ) -> None:
        if degraded:
            self._st_camera.setText(f"相机: 降级→{camera_id}({source_type})")
            self._camera_panel.refresh(
                self._config,
                opened_camera_id=camera_id,
                opened_source_type=source_type,
                degraded=True,
                message=message,
            )
            if message:
                QMessageBox.warning(self, "相机源已降级", message)
        else:
            label = "USB" if source_type == "usb" else "视频回放"
            self._st_camera.setText(f"相机: {label}·{camera_id}")
            self._camera_panel.refresh(
                self._config,
                opened_camera_id=camera_id,
                opened_source_type=source_type,
                degraded=False,
            )

    def _on_apply_camera_binding(self) -> None:
        if self._run.is_running:
            QMessageBox.warning(self, "无法切换", "请先停止检测，再切换输入源绑定。")
            return
        cam_id = self._camera_panel.selected_camera_id()
        if not cam_id:
            return
        station, _ = resolve_station(self._config, self._station_id)
        station.camera_id = cam_id
        try:
            validate_config(self._config)
            save_config(self._config, self._config_path)
            self._config = load_config(self._config_path)
        except (ConfigError, OSError) as exc:
            QMessageBox.warning(self, "保存绑定失败", str(exc))
            return
        self._run.reload_config(self._config)
        self._camera_panel.refresh(self._config)
        logger.info("camera binding saved station=%s camera_id=%s", station.id, cam_id)
        QMessageBox.information(self, "已保存", f"工位 {station.id} 已绑定相机 {cam_id}。")

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

        view = self._station_views.get(payload.station_id)
        if view is not None:
            view.update_frame(payload)
        elif self._station_id in self._station_views:
            self._station_views[self._station_id].update_frame(payload)

        label = signal_label(payload.signal, fault=payload.fault)
        sim = plc_sim_value(payload.signal, fault=payload.fault)
        self._st_signal.setText(f"状态: {payload.station_id} signal={payload.signal}({label})")
        self._run.write_plc_signal(payload.signal, fault=payload.fault)
        status = self._run.poll_plc_status()
        last_int16 = status.last_plc_int16 if status is not None else sim
        self._refresh_plc_status(last_int16=last_int16 if last_int16 is not None else sim)

    def _apply_editor_zones(self, *, persist: bool) -> bool:
        """Copy ZoneEditor polygons into in-memory config; optionally save to disk."""
        view = self._station_view()
        slow, stop = view.get_polygons()
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
                view.set_param_group(param)
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
