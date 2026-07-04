# Safety Zone Detector — 功能规格与迁移对照文档

> 用途：将 **既有 PyQt6 / Windows 版「安全区深度检测」** 的功能与 UI，迁移到本仓库 **SafetyZone（Jetson + PySide6 + TensorRT）** 时，按功能 ID 一一对应实现。  
> 版本基准：旧仓库 `safety_zone_detector/` 包结构 + 本仓库当前实现状态。  
> 最后整理：2026-07-04
>
> **配套文档**：[设计方案](安全区入侵检测系统_设计方案.md) · [执行方案](安全区入侵检测系统_执行方案.md)（**§1.2 为执行层摘要**）· [validation_phases.md](validation_phases.md) · [decisions.md](decisions.md)

---

## 目录

1. [项目定位与边界](#1-项目定位与边界)
2. [系统架构](#2-系统架构)
3. [技术栈对照表](#3-技术栈对照表)
4. [功能模块清单（迁移主表）](#4-功能模块清单迁移主表)
5. [检测流水线（核心）](#5-检测流水线核心)
6. [相机与采集](#6-相机与采集)
7. [立体标定与深度](#7-立体标定与深度)
8. [检测引擎](#8-检测引擎)
9. [安全区与入侵逻辑](#9-安全区与入侵逻辑)
10. [报警与录像](#10-报警与录像)
11. [PLC 与通讯](#11-plc-与通讯)
12. [多工位运行时](#12-多工位运行时)
13. [用户界面](#13-用户界面)
14. [权限与审计](#14-权限与审计)
15. [配置体系](#15-配置体系)
16. [数据模型](#16-数据模型)
17. [协议与接口规范](#17-协议与接口规范)
18. [状态机汇总](#18-状态机汇总)
19. [文件与目录布局](#19-文件与目录布局)
20. [迁移优先级建议](#20-迁移优先级建议)
21. [已知桩实现与差异](#21-已知桩实现与差异)

---

## 1. 项目定位与边界

### 1.1 产品定义

工业现场 **安全区视觉检测系统**：通过 USB 相机（单目或双目）实时检测人员/物体是否进入预设安全区，并根据 **距离** 输出 **减速 / 停止** 两档信号，联动产线 PLC 或 TCP 报警服务，同时 **事件录像留证**。

### 1.2 核心用户场景

| 场景 | 描述 |
|------|------|
| 多工位监控 | 1~N 路相机并行，每工位独立划区/标定/检测程序 |
| 人员距离检测 | YOLO 检人 + 双目深度 → 减速/停止 |
| 物体距离检测 | YOLO 检 COCO 物体 + 深度 → 同上 |
| 圆桶颜色识别 | HSV 颜色 + 轮廓 + 深度 → 产品分类报警 |
| PLC 联调 | S7 读写命令字、结果码、预设切换信号 |
| 权限管控 | 刷卡/账户登录，按角色限制操作 |
| 离线训练 | YOLO 标注、训练、应用到工位 |

### 1.3 不在范围内（迁移时可裁剪）

- `tools/` 中部分脚本为桩（`setup_yolo.py`、`generate_demo_calib.py`）
- PyInstaller 打包细节（`bootstrap_runtime_data`）可按新栈重写
- Windows 开机自启（`startup/windows_launch.py`）为平台特定

---

## 2. 系统架构

### 2.1 逻辑分层

```
┌─────────────────────────────────────────────────────────────┐
│  UI 层 (PyQt6)                                               │
│  MainWindow / StationView / Dialogs / Auth / CommCenter      │
├─────────────────────────────────────────────────────────────┤
│  协调层                                                       │
│  RunController / ConfigController / CommHost / FrameBridge   │
├─────────────────────────────────────────────────────────────┤
│  运行时层 (每工位 1 线程)                                     │
│  SafetyRuntime × N  ←  MultiCameraManager                    │
├─────────────────────────────────────────────────────────────┤
│  算法与服务层                                                 │
│  Capture │ Depth │ Detect │ Zone/FSM │ Alarm │ Recorder      │
├─────────────────────────────────────────────────────────────┤
│  外部集成                                                     │
│  TCP JSON │ S7 PLC │ 文件系统 (config/logs/records/models)   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 主数据流

```
相机帧
  → 立体校正 + SGBM 深度（单目可跳过）
  → YOLO/HOG/HSV 检测
  → 深度采样 + 地面映射 + 距离 EMA
  → 安全区判定 + 距离档位（slow/stop）
  → 入侵 FSM 防抖
  → result_code (0/1/2/3)
  ├→ UI 帧推送 (FrameBridge)
  ├→ TCP 报警 (AlarmDispatcher)
  ├→ 事件录像 (EventRecorder)
  └→ PLC 结果写入 (CommResultWriter)
```

### 2.3 关键源码目录

| 目录 | 职责 |
|------|------|
| `main.py` | 应用入口、单实例、日志、主题 |
| `config.py` / `unified_config.py` | 配置加载、工位合并、路径解析 |
| `pipeline/` | 单工位/多工位运行时 |
| `capture/` | 相机采集、共享池、设备探测 |
| `calibration/` | 立体标定、地面平面映射 |
| `depth/` | SGBM 深度、ROI 局部立体 |
| `detect/` | 人体/物体/圆桶检测 |
| `zone/` | 安全区、距离信号、入侵 FSM、预设 |
| `alarm/` | TCP 客户端、产线信号、录像 |
| `comm/` + `plc/` | 通讯中心、S7、工位命令 |
| `auth/` | 会话、权限、审计 |
| `ui/` | 全部界面 |
| `performance/` | 性能模式预设 |
| `storage/` | 录像保留策略 |
| `connectivity/` | PLC/相机 ping 监控 |
| `heartbeat/` | 心跳 UI/Runner |

---

## 3. 技术栈对照表

迁移时建议为每个模块指定目标栈等价物：

| 当前实现 | 用途 | 迁移替代方向（示例） |
|----------|------|----------------------|
| Python 3.12 | 主语言 | Node.js / Go / C# / Rust |
| PyQt6 | 桌面 GUI | Electron / Tauri / WPF / Web SPA |
| OpenCV (contrib) | 图像、SGBM、HOG、DNN-ONNX | OpenCV 绑定 / 自研 GPU 管线 |
| NumPy | 数组运算 | 同语言数值库 |
| Ultralytics YOLO | PT 推理 | ONNX Runtime / TensorRT / 云端 API |
| OpenCV DNN | ONNX 推理 | ONNX Runtime / TensorRT |
| PyYAML | 配置 | JSON/YAML/TOML + schema 校验 |
| python-snap7 | S7 PLC | snap7 绑定 / OPC UA / Modbus |
| TCP socket | JSON 行报警 | 同协议或 MQTT/gRPC |
| threading | 后台检测 | 原生线程 / async worker / 进程池 |
| QFileSystemWatcher | 配置热重载 | 等效文件监听 |

---

## 4. 功能模块清单（迁移主表）

> **迁移列**：填写目标栈中的模块/服务名。  
> **优先级**：P0 必须 / P1 重要 / P2 可后补。

| ID | 功能名称 | 当前模块 | 输入 | 输出 | 优先级 |
|----|----------|----------|------|------|--------|
| F01 | 应用启动与单实例 | `main.py`, `app_single_instance.py` | CLI 配置路径 | GUI 进程 | P0 |
| F02 | 配置加载/保存 | `config.py`, `unified_config.py` | YAML/JSON | `AppConfig` | P0 |
| F03 | 配置热重载 | `ui/config_controller.py` | 文件变更 | 运行时参数更新 | P1 |
| F04 | 多工位管理 | `stations_config.py`, `ui/station_dialog.py` | stations[] | CRUD + 合并配置 | P0 |
| F05 | 相机枚举与绑定 | `capture/camera_probe.py`, `ui/camera_list.py` | 本机设备 | 工位 cameras 配置 | P0 |
| F06 | 视频采集 | `capture/stereo_capture.py` | 设备 ID/ROI | left/right BGR | P0 |
| F07 | 共享相机池 | `capture/shared_camera_pool.py` | 多工位同设备 | 单打开多订阅 | P1 |
| F08 | 立体标定 | `calibration/stereo_calibrate.py`, `ui/calib_wizard.py` | 棋盘格图对 | `.npz` 参数 | P0 |
| F09 | 深度计算 | `depth/stereo_depth.py` | 校正后 L/R | depth_mm, disparity | P0 |
| F10 | ROI 局部立体 | `depth/roi_stereo.py` | 检测框 ROI | 局部 depth 合并 | P2 |
| F11 | 人体检测 YOLO | `detect/person_detector.py` | BGR 帧 | PersonBox[] | P0 |
| F12 | 物体检测 | `detect/object_zone.py` | BGR + depth | FusedPerson[] | P1 |
| F13 | 圆桶颜色 | `detect/barrel_color.py` | BGR + depth | FusedPerson[] | P2 |
| F14 | 深度融合 | `detect/depth_fusion.py` | boxes + depth | FusedPerson[] | P0 |
| F15 | 安全区管理 | `zone/zone_manager.py` | 多边形配置 | in_zone 判定 | P0 |
| F16 | 距离档位 | `zone/distance_signals.py`, `threat_eval.py` | depth + in_zone | slow/stop/"" | P0 |
| F17 | 入侵 FSM | `zone/intrusion_fsm.py` | FusedPerson[] | IntrusionEvent | P0 |
| F18 | 区域/距离预设 | `zone/zone_preset.py`, `range_preset.py` | preset id / PLC 信号 | 切换 zone/intrusion | P1 |
| F19 | 检测程序模式 | `detection_programs.py`, `plc/program_modes.py` | 配置/PLC | person/object/barrel | P1 |
| F20 | 单工位运行时 | `pipeline/runtime.py` | AppConfig | 帧+报警+result_code | P0 |
| F21 | 多工位管理器 | `pipeline/multi_runtime.py` | root AppConfig | N×SafetyRuntime | P0 |
| F22 | UI 帧桥接 | `pipeline/frame_bridge.py` | runtime payload | Qt 信号/帧存储 | P0 |
| F23 | TCP 报警 | `alarm/tcp_client.py`, `dispatcher.py` | IntrusionEvent | JSON 行 | P0 |
| F24 | 全局产线信号 | `alarm/line_signals.py` | 各工位 stop/slow | LINE_STOP/SLOW | P0 |
| F25 | 事件录像 | `alarm/recorder.py` | 帧流+触发 | avi/jpg/json | P1 |
| F26 | 录像保留清理 | `storage/retention.py` | record 配置 | 删除过期文件 | P2 |
| F27 | S7 PLC 读写 | `plc/s7_client.py`, `s7_codec.py` | DB 地址 | 原始字节 | P1 |
| F28 | 工位命令解析 | `comm/station_command.py` | PLC 命令字 | start/stop/switch | P1 |
| F29 | 结果回写 PLC | `comm/result_writer.py` | result_code | S7 写入 | P1 |
| F30 | 通讯管理中心 | `comm/host.py`, `ui/s7_config_dialog.py` | comm JSON | 轮询+解析 | P1 |
| F31 | 权限登录 | `auth/`, `ui/login_dialog.py` | 卡号/密码 | Session | P1 |
| F32 | 权限门控 UI | `ui/auth_ui_controller.py` | permission key | 控件 enable | P1 |
| F33 | 审计日志 | `auth/audit.py` | action+detail | audit 文件 | P2 |
| F34 | 性能模式 | `performance/profiles.py` | mode 名称 | 批量参数覆盖 | P2 |
| F35 | 连通性监控 | `connectivity/monitor.py` | host 列表 | ping 状态 | P2 |
| F36 | YOLO 标注训练 | `ui/yolo_studio_dialog.py` 等 | 数据集 | 模型文件 | P2 |
| F37 | 演示/模拟相机 | `capture/mock_camera.py` | 无硬件 | 合成帧 | P2 |
| F38 | 日志系统 | `log_setup.py`, `ui/log_panel.py` | logger | 文件+UI | P1 |

---

## 5. 检测流水线（核心）

### 5.1 SafetyRuntime 生命周期

**文件**：`pipeline/runtime.py`

| 状态 | 条件 | 行为 |
|------|------|------|
| Stopped | 未 start | 无线程 |
| Running | start() | 完整检测循环 |
| Parked | 工位切换/共用相机 | 只读帧，不做 AI |
| Startup Grace | 启动后 N 秒/帧 | 抑制 FSM 报警 |

### 5.2 每帧处理顺序（必须保持语义等价）

```
1. 打开/复用相机 (_open_camera)
2. [Parked] 仅读帧 → sleep → continue
3. 加锁读取当前 AppConfig
4. _read_frames() → (ok, left, right)；mono 时 right=left
5. _emit_preview(left) → 预览 Hub
6. 黑帧检测 mean(left) < 2.5
7. _compute_depth_data() → depth_mm, disparity, 校正图
8. _run_detection() → 按 program_mode 分支
9. _update_depth_rois() → 下帧 ROI 立体输入
10. _fsm.update(fused) → IntrusionEvent
11. _resolve_result_code() → 0/1/2/3
12. _stabilize_result_code() → 清除防抖保持
13. 绘制 overlay（安全区、检测框、深度色条）
14. _recorder.push_frame() → 环形缓冲
15. 计算 FPS
16. _build_payload() + 别名工位 payload
17. _emit_frames() → UI
18. [非 grace] _dispatch_signal_events() + GlobalLineSignals
19. sleep(1ms)
```

### 5.3 result_code 定义

| 值 | 含义 | 触发条件 |
|----|------|----------|
| 0 | OK | 无 slow/stop 威胁 |
| 1 | SLOW | slow FSM active |
| 2 | STOP | stop FSM active（优先于 slow） |
| 3 | ALARM/未就绪 | 引擎未就绪、配置缺失、视觉 NG 等 |

### 5.4 UI Payload 字段（FrameBridge）

迁移 UI 时必须支持的最小字段集：

```json
{
  "station_id": "cam03",
  "station_name": "工位3",
  "result_code": 0,
  "fps": 28.5,
  "stop_count": 0,
  "slow_count": 0,
  "is_line_stopped": false,
  "is_line_slow": false,
  "event": { "...IntrusionEvent 序列化..." },
  "program_mode": "person_distance",
  "camera_ok": true,
  "overlay_bgr": "<图像或共享内存句柄>",
  "left_bgr": "...",
  "right_bgr": "...",
  "depth_color_bgr": "...",
  "disparity_bgr": "..."
}
```

### 5.5 检测程序模式分支

**文件**：`detection_programs.py`, `plc/program_modes.py`

| mode | 处理器 | 说明 |
|------|--------|------|
| `idle` | 无 | 仅预览 |
| `person_distance` | PersonDetector + DepthFusion | 默认 |
| `object_distance` | ObjectZoneEvaluator | COCO 物体 |
| `barrel_color` | BarrelColorEvaluator | HSV 圆桶 |

---

## 6. 相机与采集

### 6.1 相机模式

**文件**：`capture/camera_mode.py`

| mode | 说明 | 是否需要立体标定 |
|------|------|------------------|
| `pick` | 占位，运行时解析 | 视子模式 |
| `mono` | 单 USB 相机 | 否（image_polygon 即可） |
| `split` / `usb_stereo` | 单路拼接左右眼 | 是 |
| `dual` | 两个 USB 设备 | 是 |

### 6.2 配置字段（工位级 cameras）

```yaml
cameras:
  mode: usb_stereo          # mono | split | dual | usb_stereo
  fps: 15
  width: 640
  height: 480
  left_id: 0                # OpenCV index
  right_id: 1               # dual 模式
  left_device: "Integrated Camera"
  left_device_id: "integrated camera@0"
  demo_mode: false          # 使用 mock 相机
  split:
    enabled: true
    total_width: 1280
    total_height: 480
    left_roi: [0, 0, 640, 480]
    right_roi: [640, 0, 640, 480]
    swap_eyes: false
```

### 6.3 功能点

| 功能 | 行为 | 源码 |
|------|------|------|
| 设备探测 | 后台扫描 OpenCV 可打开 index | `camera_probe.py` |
| DShow 预热 | Windows 首次打开加速 | `camera_probe.warmup_dshow_cache` |
| 双击绑定 | 列表项 → 当前工位 left_id | `ui/camera_list.py` |
| 共享池 | 同 physical fingerprint 只开一次 | `shared_camera_pool.py` |
| 工位切换 | activate_station 保持采集换配置 | `runtime.activate_station` |
| Mock 相机 | demo_mode 无硬件演示 | `mock_camera.py` |

### 6.4 迁移要点

- 抽象 `ICameraSource`：`open()`, `read()`, `close()`, `fingerprint()`
- ROI 裁剪必须在采集层完成，保证 left/right 尺寸一致
- MSMF 硬件变换禁用：`OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0`（Windows 性能）

---

## 7. 立体标定与深度

### 7.1 标定流程（UI：标定向导）

**文件**：`ui/calib_wizard.py`, `calibration/stereo_calibrate.py`

```
1. 停止当前工位检测线程
2. 打开相机，采集棋盘格左右图对
3. 至少 min_samples 组（默认 15）
4. 执行 stereoCalibrate → 保存 .npz
5. 路径：calibration.params_path（默认 calibration_data/<工位id>_stereo.npz）
```

### 7.2 NPZ 内容

| 键 | 用途 |
|----|------|
| K1, K2 | 内参 |
| D1, D2 | 畸变 |
| R, T | 外参 |
| Q | 视差→深度 |
| map1x/y, map2x/y | 校正映射 |
| baseline_mm | 基线 |

### 7.3 深度引擎

**文件**：`depth/stereo_depth.py`

**输入**：left/right BGR，可选 `measure_rois`  
**输出**：`DepthComputeResult`

| 字段 | 用途 |
|------|------|
| `depth_mm` | 报警测距（保守） |
| `depth_preview_mm` | UI 预览（WLS+时序平滑） |
| `disparity` | 视差图 |
| `rect_left/right` | 校正后图像 |

**算法链**：
```
加载 NPZ → remap 校正 → 灰度+CLAHE
→ SGBM 视差 → [可选 WLS 滤波]
→ reprojectImageTo3D(Q) → Z 通道
→ clip [min_mm, max_mm]
→ [可选 ROI 局部立体合并]
```

**关键配置**（`depth.*`）：

| 参数 | 典型值 | 说明 |
|------|--------|------|
| scale | 0.5~1.0 | 计算缩放，低配建议 0.5 |
| num_disparities | 64~160 | 视差搜索范围 |
| min_mm / max_mm | 200 / 8000 | 有效深度 |
| filter_mode | minimal/standard/full | 后处理强度 |
| wls_filter | true/false | 精度 vs 性能 |
| roi_stereo_enabled | true | 按检测框局部算深度 |

### 7.4 地面映射

**文件**：`calibration/ground_plane.py`

- `ground_polygon` 模式：像素+深度 → 地面 (X,Y) mm
- 用于地面坐标系划区

---

## 8. 检测引擎

### 8.1 人体检测

**文件**：`detect/person_detector.py`

**后端**（`detection.backend`）：

| 值 | 引擎 | 场景 |
|----|------|------|
| yolo | ONNX (OpenCV DNN) 或 Ultralytics | 默认 |
| hybrid | YOLO + HOG 补帧 | 隔帧加速 |
| hog | OpenCV HOG | 无 GPU/无模型 |

**PersonBox 字段**：
```
x1, y1, x2, y2, score, track_id
zone_point (中心), foot (底边中点)
```

**过滤规则**：
- 置信度、IoU NMS
- 宽高比 min/max
- min_height_px, min_area_ratio
- 与物体框重叠抑制（chair/bench 等）

**帧跳过**：`yolo_interval` — 每 N 帧推理一次，中间帧用 tracker 插值

### 8.2 深度融合

**文件**：`detect/depth_fusion.py`

```
对每个 PersonBox:
  1. 在 depth_mm 框内采样（有效像素比例）
  2. DistanceEmaBank 按 track_id 平滑
  3. 判定 in_zone（image_polygon 重叠比 / ground_polygon 包含）
  4. ThreatEvaluator.mark_levels → signal_level: "" | "slow" | "stop"
  5. refine_multi_person_depths 去重
```

**单目 fallback**（`intrusion.mono_*`）：
- 无 depth 时用框高估算距离

### 8.3 物体距离检测

**文件**：`detect/object_zone.py`

**测量策略**（`detection_programs.object_measure_strategy`）：

| 策略 | 行为 |
|------|------|
| detect_then_depth | 先 YOLO 再框内深度（默认） |
| depth_nearest | 安全区内最近有效深度点 |
| priority_class | 按类别优先级选目标 |
| largest | 最大面积目标 |

输出包装为 `FusedPerson[]` 以复用 FSM。

### 8.4 圆桶颜色

**文件**：`detect/barrel_color.py`, `detect/barrel_models.py`

```
HSV 颜色模型（多档可启用）
→ 轮廓检测 + 圆度过滤
→ 桶沿内外半径比
→ 区内外判定 + 深度
→ 匹配 product_code (A/B/C...)
```

配置在 `detection.barrel.color_models[]`（h/s/v 范围、display_bgr、product_code）。

### 8.5 跟踪

**文件**：`detect/box_tracker.py`  
配置：`tracking.enabled`, IoU 阈值  
用途：yolo_interval > 1 时保持 track_id 与 EMA 连续。

---

## 9. 安全区与入侵逻辑

### 9.1 安全区类型

**文件**：`zone/zone_manager.py`

| type | 配置 | 判定 |
|------|------|------|
| image_polygon | zone.image_points [[x,y],...] | 框与多边形重叠比 ≥ min_overlap |
| ground_polygon | zone.points_mm [[x_mm,y_mm],...] | 地面坐标点在多边形内 |

### 9.2 距离信号配置

**文件**：`zone/distance_signals.py`

```yaml
intrusion:
  enter_frames: 3          # 进入防抖（通用 fallback）
  exit_frames: 5           # 离开防抖
  startup_grace_sec: 2.5
  startup_grace_frames: 18
  fast_visual_result: true
  result_clear_hold_ms: 450
  result_clear_hold_frames: 3
  distance_signals:
    valid_min_mm: 200
    valid_max_mm: 8000
    resume_when_all_clear: true
    stop:
      enabled: true
      min_mm: 500
      max_mm: 1500
      event_on: LINE_STOP
      event_off: LINE_STOP_CLEAR
      action: stop
    slow:
      enabled: true
      min_mm: 1500
      max_mm: 2500
      event_on: LINE_SLOW
      event_off: LINE_SLOW_CLEAR
      action: slow
```

**分类规则**：
- 不在区 → `""`
- 在区 + depth ∈ stop 区间 → `"stop"`（优先）
- 在区 + depth ∈ slow 区间 → `"slow"`

### 9.3 入侵 FSM

**文件**：`zone/intrusion_fsm.py`

**结构**：slow / stop 两个独立 `_LevelFSM`

```
状态: IDLE | ACTIVE

IDLE:
  count > 0 连续 enter_n 帧 → ACTIVE, entered=True

ACTIVE:
  count == 0 连续 exit_n 帧 → IDLE, exited=True
```

**IntrusionEvent 输出**：
```
slow_entered, slow_exited, stop_entered, stop_exited
slow_count, stop_count
slow_persons[], stop_persons[]
is_slow_active, is_stop_active
```

### 9.4 预设系统

| 预设类型 | 存储 | 切换 API | PLC 绑定 |
|----------|------|----------|----------|
| 区域预设 zone_presets | 工位 YAML | apply_zone_preset(id) | bind_signal |
| 距离预设 range_presets | 工位 YAML | apply_range_preset(id) | bind_signal |

工位级信号：
- `zone_preset_signal` — PLC 写值切换区域
- `range_preset_signal` — PLC 写值切换距离档

**遗留迁移**：旧版全局 `intrusion.distance_signals` 自动转为单个 `range_presets` 行。

---

## 10. 报警与录像

### 10.1 TCP 报警协议

**文件**：`alarm/tcp_client.py`

- 传输：TCP 长连接
- 格式：**UTF-8 JSON + `\n` 换行**
- 配置：`alarm.tcp_host`, `alarm.tcp_port`（默认 5020）
- 心跳：每 `heartbeat_sec` 发送 `HEARTBEAT`
- 重连：间隔 `reconnect_sec`

**消息结构**：
```json
{
  "event": "LINE_STOP",
  "ts": "2026-07-04 12:00:00",
  "action": "stop",
  "station_id": "cam03",
  "station_name": "工位3",
  "count": 1,
  "xy": [[1200.5, 450.2]],
  "depths_mm": [1200.0]
}
```

**事件类型**：

| event | 时机 |
|-------|------|
| HEARTBEAT | 定时 online |
| LINE_STOP / LINE_STOP_CLEAR | 停止档 on/off |
| LINE_SLOW / LINE_SLOW_CLEAR | 减速档 on/off |
| LINE_STOP / LINE_RESUME | 全局产线（GlobalLineSignals） |
| ALARM_ON / ALARM_OFF | 遗留通用报警 |

### 10.2 报警分发器

**文件**：`alarm/dispatcher.py`

- 异步队列（max 256），独立 worker 线程
- 检测线程不阻塞网络/磁盘
- Job 类型：alarm_on/off, line_stop/resume, custom, record

### 10.3 全局产线信号

**文件**：`alarm/line_signals.py`

```
任一工位 stop active → 全局 LINE_STOP
全部工位 stop 解除 → LINE_STOP_CLEAR（当 resume_when_all_clear）
stop 优先于 slow（同理 LINE_SLOW）
```

### 10.4 事件录像

**文件**：`alarm/recorder.py`

**触发**：stop/slow 进入时（clear 不触发）

**输出目录**：`records/<工位slug>/<timestamp>/`

| 文件 | 内容 |
|------|------|
| alarm.avi | 预录 pre_sec + 后录 post_sec |
| snapshot.jpg | 触发帧 |
| depth.jpg | 深度伪彩（可选） |
| event.json | 人数、坐标、深度、station_id |

**配置**（`record.*`）：
```yaml
record:
  enabled: true
  dir: records
  pre_sec: 2
  post_sec: 3
  fps: 15
  save_snapshot: true
  save_depth: true
  cleanup_interval_hours: 6
  retention_days: 30
  max_disk_gb: 50
```

---

## 11. PLC 与通讯

### 11.1 配置文件

| 文件 | 内容 |
|------|------|
| config/comm_manager.json | 设备列表（S7/TCP）、addr_map |
| config/comm_rules.json | 解析规则、station_command、心跳 |

合并到 `app.yaml` 时键名：`comm_manager`, `comm_rules`。

### 11.2 S7 设备

**文件**：`plc/s7_client.py`, `plc/s7_codec.py`

- 库：python-snap7
- 连接：IP, rack, slot, port 102
- 支持类型：Bool, Int16, UInt16, Int32, UInt32, Float, String, HexBytes
- 大端编码

### 11.3 工位命令字

**文件**：`comm/station_command.py`, `comm/station_command_executor.py`

**PLC → 应用**：从 S7 地址读取整数 **command code**

| run_mode | 语义 |
|----------|------|
| exclusive | 一码一工位 |
| parallel_mask | 位掩码，每位对应 mapping |
| code_group | 同码多工位并行 |

| code | 动作 |
|------|------|
| ≤ 0 | 停止全部工位 |
| > 0 | 按 mapping 启动/切换对应工位 |

**Executor 动作**：switch, stop_all, sync, noop, throttled  
**防抖**：2s 内重复命令忽略；用户手动停止后需 code 变化才自动重启

### 11.4 结果回写（应用 → PLC）

**文件**：`comm/result_writer.py`

- 50ms 轮询 + result_code 变化立即写
- 多工位共享同一 PLC 地址 → 取 **max 严重度**（STOP > SLOW > OK）
- cmd=0 时写 idle 0；cmd>0 但 mapping 未满足写 3（未就绪）

**result_code 与 PLC 值一致**：0=OK, 1=SLOW, 2=STOP, 3=ALARM

### 11.5 结果同步追踪

**文件**：`comm/result_sync_tracker.py`

UI 显示：检测码 vs 写入值 vs 读回值  
判定：正常 / 检测 / 通讯 / 配置 / 待写入

### 11.6 通讯轮询

**文件**：`comm/host.py`

- 150ms 轮询 CommRuntimeEngine
- 解析规则 → comm_signal_store
- 预设切换：监听 zone/range preset 绑定信号
- 8s auto-start cooldown

---

## 12. 多工位运行时

**文件**：`pipeline/multi_runtime.py`

### 12.1 职责

- 为每个 enabled 工位创建 `SafetyRuntime`
- 共享 `AlarmTcpClient`, `AlarmDispatcher`, `GlobalLineSignals`
- 共享 `SharedCameraPool`（同设备 fingerprint 合并）
- 提供 `start_all()`, `stop_all()`, `reload_config()`, `reload_stations()`

### 12.2 共用相机别名

同一物理相机服务多个 logical station：
- 主 runtime 做 YOLO/depth 一次
- `_alias_station_ids`  fan-out 到各工位 ZoneManager/FSM
- 每帧 round-robin 处理部分 alias（性能优化）

### 12.3 启动流程（UI）

**文件**：`ui/run_controller.py`, `ui/engine_bootstrap_worker.py`

```
1. EngineBootstrapWorker 创建 MultiCameraManager
2. 预加载 YOLO 模型
3. DetectStartWorker 探测相机、解析绑定
4. start_all() 启动各工位线程
5. CommHost.start_background_services()
```

---

## 13. 用户界面

### 13.1 主窗口布局

**文件**：`ui/main_window.py`

```
┌──────────────────────────────────────────────────────────┐
│ 工具栏: 工位选择 | 用户 | 全部开始/停止 | 标定 | 保存划区  │
├──────────┬───────────────────────────────────────────────┤
│ 本机相机  │ Tab: [运行总览] [工位1: 监控|划区|视差] ...     │
│ 列表     │                                               │
├──────────┴───────────────────────────────────────────────┤
│ 运行日志面板                                              │
├──────────────────────────────────────────────────────────┤
│ 状态栏: 相机|通讯|PLC同步|模式|CPU/内存|报警               │
└──────────────────────────────────────────────────────────┘
```

### 13.2 菜单结构

| 菜单 | 项 | 权限 |
|------|-----|------|
| 系统 | 刷卡登录、退出登录、权限分配 | manage_auth |
| 工位 | 添加/编辑/删除、检测程序、模型配置 | manage_station |
| 相机 | 刷新列表、相机配置、保存绑定 | bind_camera / manage_station |
| PLC | 通讯配置 | comm_center |
| 文件 | 加载配置、运行设置、录像设置、圆桶模型、物体参数、YOLO Studio、训练模式、退出 | 各不同 |
| 查看 | 日志目录、审计目录、清空显示 | — |

### 13.3 工位 Tab 页

| Tab | 功能 | 源码 |
|-----|------|------|
| 运行总览 | 多工位缩略图+状态 | `running_overview.py` |
| 监控 | 主画面+结果+PLC同步；双目有左/右眼 | `station_view.py` |
| 视差/深度 | 仅双目/非轻量化 | `station_view.py` |
| 划区编辑 | 多边形+区域预设表+距离预设表 | `zone_editor.py`, `station_zone_panel.py` |

### 13.4 对话框清单

| 对话框 | 功能 |
|--------|------|
| StationEditDialog | 工位 CRUD、相机模式、设备选择 |
| CalibWizardDialog | 标定采集与执行 |
| S7ConfigDialog | PLC 设备/地址/命令/心跳 |
| PerformanceConfigDialog | 性能模式、自动启动 |
| RecordConfigDialog | 录像路径与保留 |
| ObjectDetectionConfigDialog | COCO 物体参数 |
| BarrelColorModelDialog | 圆桶 HSV 模型 |
| YoloStudioDialog | 标注+训练 |
| YoloTrainingModeDialog | 采集自动标注流程 |
| LoginDialog / AuthAdminDialog | 登录与权限管理 |
| CardConfirmDialog | 退出确认 |

### 13.5 主题

**文件**：`ui/industrial_theme.py`  
配置：`ui.theme` = light | dark  
工业茄紫统一色系。

---

## 14. 权限与审计

### 14.1 权限键

**文件**：`auth/permissions.py`

| 键 | 标签 | 典型门控 |
|----|------|----------|
| view | 查看监控 | 基线 |
| run_detect | 启停检测 | 开始+停止 |
| run_start | 启动检测 | 全部开始 |
| run_stop | 停止检测 | 全部停止 |
| load_config | 加载配置 | 文件菜单 |
| save_config | 保存配置 | 各配置对话框 |
| manage_station | 工位管理 | 工位 CRUD、检测程序 |
| calib | 标定 | 标定向导 |
| bind_camera | 绑定相机 | 相机面板 |
| edit_zone | 划区编辑 | 划区 Tab、保存划区 |
| signal_config | 信号配置 | 距离预设（与 edit_zone 或） |
| comm_center | 通讯管理 | PLC 菜单 |
| manage_auth | 权限分配 | 系统菜单 |

### 14.2 角色模板

| 角色 | 权限 |
|------|------|
| admin | 全部 |
| engineer | 查看、启停、划区、标定、信号、保存、绑相机、通讯 |
| operator | 查看、启停 |
| viewer | 仅查看 |
| guest | 查看、启动（默认未登录） |

### 14.3 认证配置

```yaml
auth:
  enabled: true
  idle_timeout_sec: 180    # 无操作退出登录，不关闭软件
  users_file: config/auth.yaml
  audit_dir: logs/audit
```

演示卡号：`10001` 操作员, `20001` 工程师, `90001` 管理员  
默认账户：登录框左上角双击 → `admin` / `admin`

### 14.4 审计事件

写入 `logs/audit/audit_YYYYMMDD.log`（action + detail + user + ts）

触发点：save/load config, zone, calib, bind camera, station CRUD, exit app 等。

> **注意**：当前 `auth/session.py`, `auth/store.py`, `auth/audit.py` 为桩实现，迁移时需完整实现或替换。

---

## 15. 配置体系

### 15.1 文件关系

```
config/app.yaml          ← 统一配置（优先）
config/default.yaml      ← 遗留主配置
config/auth.yaml         ← 遗留权限（合并为 auth_store）
config/comm_manager.json ← 遗留通讯设备
config/comm_rules.json   ← 遗留通讯规则
calibration_data/*.npz   ← 标定（独立文件）
models/*.pt|*.onnx       ← YOLO 权重
logs/                    ← 运行日志
records/                 ← 事件录像
datasets/                ← YOLO 训练数据
```

### 15.2 工位 schema（stations[]）

```yaml
stations:
  - id: cam03
    name: 工位3
    enabled: true
    cameras: { ... }           # 覆盖全局 cameras
    calibration:
      params_path: calibration_data/cam04_stereo.npz
    zone:
      type: image_polygon
      image_points: [[x,y], ...]
    zone_presets:
      - id: default
        label: 默认
        bind_signal: ""
        zone: { type, image_points }
    range_presets:
      - id: default
        label: 默认距离
        bind_signal: ""
        intrusion:
          distance_signals: { stop, slow, ... }
    default_range_preset_id: default
    zone_preset_signal: ""
    range_preset_signal: ""
    detection_programs:
      person_distance_enabled: true
      object_distance_enabled: true
      barrel_color_enabled: false
      default_mode: person_distance
    detection: { ... }         # 可选 per-station YOLO 覆盖
    intrusion: { ... }         # 可选 per-station 距离覆盖
    depth: { ... }             # 可选 per-station 深度覆盖
```

### 15.3 AppConfig.for_station() 合并规则

```
merged = deepcopy(global raw)
merged["_station_id"] = station.id
merged["_station_name"] = station.name
for key in [cameras, calibration, zone, intrusion, detection, depth, detection_programs]:
    if station has key: deep_merge(global[key], station[key])
attach _zone_presets, _range_presets, preset signals
run ensure_range_presets_from_legacy()
```

### 15.4 性能模式

**文件**：`performance/profiles.py`

| mode | 场景 | 典型 yolo_imgsz | depth.scale |
|------|------|-----------------|-------------|
| lightweight | i3/低配 | 320 | 0.75 |
| standard | i5/R5 | 640 | 1.0 |
| high_performance | i7/R7+ | 640 | 1.0 |

一键覆盖 detection/depth/cameras 多项参数。

### 15.5 启动项

```yaml
startup:
  auto_init_resources: true    # 启动时预加载引擎
  auto_run_detect: false       # 启动后自动开始检测
  windows_auto_launch: false   # Windows 开机自启
  local_run_current_station: false
```

---

## 16. 数据模型

### 16.1 PersonBox

```
x1, y1, x2, y2: float
score: float
track_id: int
zone_point: (cx, cy)
foot: (fx, fy)
```

### 16.2 FusedPerson

```
box: PersonBox
depth_mm: float | None
ground_xy_mm: (x, y) | None
in_zone: bool
valid_depth_ratio: float
signal_level: "" | "slow" | "stop"
is_threat: bool
```

### 16.3 IntrusionEvent

```
slow_entered, slow_exited, stop_entered, stop_exited: bool
slow_count, stop_count: int
slow_persons, stop_persons: List[FusedPerson]
is_slow_active, is_stop_active: bool
```

### 16.4 DetectedObject

```
x1, y1, x2, y2, score, class_id, class_name
```

### 16.5 Comm 信号存储

```
comm_signal_store: Dict[str, Any]   # var_name → 解析后的值
```

---

## 17. 协议与接口规范

### 17.1 对外 TCP JSON（报警）

- 编码：UTF-8
- 分帧：`\n`
- 必含：`event`, `ts`
- 工位相关：`station_id`, `station_name`
- 人员相关：`count`, `xy`, `depths_mm`

### 17.2 PLC 命令字

- 类型：整数（S7 Int16/Int32 可配）
- 0 或负：停止全部
- 正：查 mappings

### 17.3 PLC 结果码

| 值 | 含义 |
|----|------|
| 0 | OK |
| 1 | 减速 |
| 2 | 停止 |
| 3 | 未就绪/报警 |

### 17.4 内部 UI 信号（迁移为 WebSocket/EventBus 等价）

| 信号 | 数据 |
|------|------|
| frame_ready | station_id, payload |
| log_line | level, message, ts |
| station_command_state | code, targets, mode |
| engine_ready | bool, error |
| connectivity_changed | host, ok |

---

## 18. 状态机汇总

### 18.1 入侵档位 FSM（×2：slow/stop）

见 [9.3](#93-入侵-fsm)

### 18.2 全局产线信号

```
per-station: stop_active, slow_active
global_stop = OR(all stop_active) with edge detect
global_slow = OR(all slow_active) AND NOT global_stop
clear only when ALL stations clear (if resume_when_all_clear)
```

### 18.3 result_code 稳定器

```
进入 NG: 立即更新
离开 NG: 保持 result_clear_hold_ms 或 result_clear_hold_frames
```

### 18.4 工位命令 Executor

```
last_code, last_targets 去重
throttle 2s
user_stop_latch 阻止 auto-restart
```

### 18.5 相机 Runtime

```
Stopped → Running → [Parked] → Stopped
Camera fail → 30s cooldown 再重试
```

---

## 19. 文件与目录布局

```
safety_zone_detector/
├── main.py
├── config.py
├── unified_config.py
├── stations_config.py
├── detection_programs.py
├── config/
│   ├── app.yaml | default.yaml
│   ├── auth.yaml
│   ├── comm_manager.json
│   └── comm_rules.json
├── calibration_data/
├── models/
├── logs/
│   ├── safety_zone_YYYYMMDD.log
│   └── audit/
├── records/
│   └── <工位slug>/<timestamp>/
├── datasets/              # YOLO 训练
├── capture/
├── calibration/
├── depth/
├── detect/
├── zone/
├── alarm/
├── pipeline/
├── comm/
├── plc/
├── auth/
├── ui/
├── performance/
├── storage/
├── connectivity/
├── heartbeat/
└── tools/
```

**打包运行时**（PyInstaller）：exe 旁 `safety_zone_detector/` 可写目录，内置资源在 `_MEIPASS`。

---

## 20. 迁移优先级建议

> **与执行方案对照**：下表 Phase 1–3 对应 [执行方案 §1.2.3](安全区入侵检测系统_执行方案.md#123-迁移阶段与执行方案对照)。执行排期以执行方案 Sprint 为准。

### Phase 1 — 最小可运行（P0）

1. 配置加载 + 单工位 schema
2. 相机采集（mono + split）
3. YOLO 人体检测（ONNX 优先）
4. image_polygon 划区
5. 距离档位 + 入侵 FSM
6. 单线程 runtime loop
7. 基础 UI：预览 + 划区 + 启停
8. TCP 报警 JSON

### Phase 2 — 生产可用（P1）

1. 立体标定 + SGBM 深度
2. 多工位 + 共享相机
3. range_presets / zone_presets
4. 事件录像
5. S7 命令字 + 结果回写
6. 权限登录 + UI 门控
7. 配置热重载
8. 物体检测模式

### Phase 3 — 完整特性（P2）

1. 圆桶颜色
2. YOLO 训练 Studio
3. ROI 局部立体
4. 连通性 ping
5. 性能模式预设
6. 审计日志
7. Windows 自启 / 打包

---

## 21. 已知桩实现与差异

| 模块 | 文档/README 描述 | 代码现状 | 迁移建议 |
|------|------------------|----------|----------|
| auth/session.py | 完整 RBAC | 桩：始终 admin | 必须重写 |
| auth/store.py | 用户/角色存储 | 桩 | 必须重写 |
| auth/audit.py | 审计写入 | 桩 no-op | 必须重写 |
| tools/setup_yolo.py | 下载模型 | 桩 | 用 CI/脚本替代 |
| tools/generate_demo_calib.py | 演示标定 | 桩 | 测试夹具替代 |
| 信号距离菜单 | 编辑全局 YAML | 重定向到划区页距离预设 | UI 文案对齐 |
| 保存全部配置菜单 | 文件菜单可见 | 代码存在但菜单隐藏 | 按需暴露 |
| 配置主文件 | README 写 default.yaml | 优先 app.yaml | 迁移时统一 schema |

---

## 附录 A：迁移验收检查表

- [ ] 单目工位：划区 → 启动 → 人进入区 → TCP 收到 LINE_STOP
- [ ] 双目工位：标定 → 深度有效 → 距离档正确
- [ ] 进入/离开防抖：enter_frames / exit_frames 生效
- [ ] 多工位：全部开始，station_id 正确出现在 JSON
- [ ] 全局产线：任一工位 stop → LINE_STOP；全部 clear → LINE_STOP_CLEAR
- [ ] 录像：触发后 records/ 下有 avi + json
- [ ] PLC：写 cmd=1 → 对应工位启动；result 回写与 UI 一致
- [ ] 预设：PLC 切换 range_preset → 距离档变化
- [ ] 权限：operator 无法标定；engineer 可以
- [ ] 热重载：改 YAML 后检测参数更新（相机不重启）
- [ ] 性能：i3 类 CPU lightweight 模式 FPS 可接受

---

## 附录 B：推荐的目标架构（Web 化示例）

若迁移为 **Web 前端 + 后端服务**：

```
Browser (React/Vue)
  ←WebSocket→  API Gateway
                 ├─ Config Service      (YAML/DB)
                 ├─ Auth Service        (JWT + RBAC)
                 ├─ Station Orchestrator (N × Worker)
                 │    └─ Vision Worker Process (OpenCV+ONNX)
                 ├─ Alarm Service       (TCP out)
                 ├─ PLC Bridge          (S7/OPC UA)
                 └─ Record Service      (S3/本地存储)
```

每个 Vision Worker 对应一个 `SafetyRuntime` 等价物，通过 Redis/共享内存接收帧（若相机在后端）。

---

*文档结束。迁移过程中若目标栈模块划分不同，请以 [功能模块清单（§4）](#4-功能模块清单迁移主表) 的 ID（F01–F38）作为追踪单元，确保行为等价而非仅 API 同名。*
