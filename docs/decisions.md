# 项目决策记录

> 阶段启动前确认项。变更需更新本文并注明日期。

| 字段 | 值 |
|------|-----|
| 确认日期 | 2026-07-01（D1–D4）；**2026-07-02**（D8–D11）；**2026-07-03**（D12） |
| 确认人 | 研发 + 待现场签字 |

---

## D1 — 检测模式

**决策：先仅 `person`**

- 阶段一 `core/` 与推理后处理只处理 person 类（COCO class 0）。
- `object` / `anomaly` 模式暂不实现，后续按需扩展。
- Jetson 运行 UI 的 Bootstrap 阶段不做 anomaly 示教。

---

## D2 — 相机与视频源

**决策：USB 相机 + 支持导入录制视频进行检测**

| 来源 | 阶段 | 说明 |
|------|------|------|
| **录制视频文件** | **Bootstrap 首选** | Jetson 运行 UI 首验输入；`camera/video_file.py` |
| USB (V4L2/GStreamer) | Bootstrap 第二步 / 阶段二 | 现场主链路，`camera/v4l2_usb.py` |

- 统一抽象 `CameraStream`，USB 与视频文件共用同一检测流水线与 **Jetson 运行 UI**。
- 视频文件：无 USB 时也可在 Jetson 上完成 **完整 UI 端到端验证**。
- Orbbec 深度相机：本期不做。

---

## D3 — PLC

**决策：西门子 S7-1200 / S7-1500**

- 通信库：`python-snap7` ≥ 3.0。
- 协议模式（block / command）待与 PLC 程序对接时二选一或并存。
- **待现场确认**：IP、rack、slot、DB 号、PUT/GET 是否开启（关闭时需 S7CommPlus 路径）。

---

## D4 — 录像

**决策：快照 + 短片段（默认）**

- 报警边沿（SLOW/STOP）触发快照 + 预录缓冲内短片段。
- 不做长时间连续录像（Orin Nano 无 NVENC）。
- Bootstrap 阶段录像为 **建议项**，不阻塞 UI 首验。

---

## D8 — 训练算力（2026-07-02 修订）

**决策：暂不使用 A100；仅调试人员 Windows GPU 承担训练**

| 角色 | 机器 | 用途 |
|------|------|------|
| 研发 | 本机（无 GPU 可）+ **Jetson** | core/编排；**Jetson 运行 UI + Bootstrap 验证** |
| 调试人员 | Windows 笔记本 GPU | 阶段三 `windows_studio` 微调 + 导出 ONNX |
| 现场 | Jetson | 运行检测；编 engine；场内冻结集验收 |

- **不部署** RemoteSshBackend / A100 / `train_remote` 路径。
- ONNX 导出：在 **Jetson 本机**（Ultralytics）或调试 Win 本机，二选一。
- 研发阶段一/二 **不依赖** A100 或本地 Win GPU。

---

## D9 — 验证分两阶段（Bootstrap / Production）

| 阶段 | 数据集 / 模型 | 验证形态 | 通过标准 |
|------|---------------|----------|----------|
| **Bootstrap** | COCO 预训练 YOLOv8s（**stock**，未场内微调） | **Jetson 完整运行 UI**（非 CLI 单测 YOLO） | 见 [validation_phases.md](validation_phases.md) |
| **Production** | 场内采集 + `windows_studio` 微调模型 | 冻结测试集 + `jetson_update` acceptance | 召回 ≥ D5 → 热切换 |

**原则（团队对齐）：**

- **COCO / stock 模型验证 = 工程集成验证**（链路通、UI 可用、信号语义对）。
- **场内冻结测试集 = 安全验收**（微调模型能否上线）。
- Bootstrap **不要求** ≥50 张现场图、不要求 `baseline_recall.py` 现场报告。
- stock 模型可用于 Bootstrap 联调（含 PLC 仿真），但 UI/文档须标明 **「集成测试 · 未过场内验收」**。

---

## D10 — COCO 在 Bootstrap 中的边界

| 用途 | 是否 |
|------|------|
| 提供 stock `yolov8s` → ONNX → Jetson FP16 engine | ✅ |
| 可选抽测（COCO val person 或含人视频） | ✅ |
| 替代场内冻结测试集做安全 sign-off | ❌ |
| 作为 D5 召回阈值依据 | ❌ |

---

## D11 — Bootstrap 期 PLC 策略（2026-07-02）

**决策：允许 PLC 仿真模式；真机联调分步进行**

| 模式 | 何时 | 说明 |
|------|------|------|
| **PLC 仿真** | Bootstrap UI 首验 | UI 显示将写入的 INT16 信号（0/1/2/-1），不连 snap7；可过 UI 验收 |
| **PLC 真机** | Bootstrap 后期 / 阶段二 | S7-1200/1500 + snap7；与产线程序对齐 |

- Bootstrap UI 验收 **不阻塞** 于 PLC 真机到货。
- 仿真模式下状态栏/仪表盘仍须展示与 §6.3 一致的信号语义。
- **配置契约（2026-07-13 / Wave0）**：`plc.enabled` + 待增 `plc.simulate`（默认 `true`）；`simulate=true` 或 `enabled=false` 时不连 snap7。拟写入 INT16 映射见 harness `D-008` / 执行计划 #20 SignalAdapter。Gateway 实现属 Wave 2，不阻塞 M-Bootstrap。

---

## D12 — Jetson 远程开发（2026-07-03）

**决策：研发已通过 SSH / Cursor Remote 连接 Jetson，Bootstrap 与 Sprint 1.2 起在板上主验证**

| 项 | 约定 |
|----|------|
| 连接 | SSH Host 别名（如 `jetson-137`）；Cursor **Remote-SSH** 在 Jetson 工作区开发 |
| 代码同步 | `git push`（Win）→ `git pull`（Jetson）；或大文件 `scp`（`*.engine`、`demo.mp4` 不进 git） |
| 验证主战场 | **Jetson**：export → trtexec → `trt_backend` → UI → M-Bootstrap |
| Win 本机 | `core/` 单测、可选 `onnx_backend` 对照；**不阻塞**上板 |
| 运行 UI 显示 | PySide6 需 Jetson **本地 HDMI 显示器** 或 **VNC/桌面**；纯 SSH 无 DISPLAY 时先做 TRT/CLI，UI 接屏后再验 M-Bootstrap |
| Jetson 工作目录 | 建议 `~/SafetyZone`（与仓库 clone 路径一致，写入团队备忘） |

---

## 两套 UI 分工（勿混淆）

| 程序 | 部署 | 用途 |
|------|------|------|
| **运行 UI**（`ui/` + `app/main.py`） | **Jetson** | 监视、划区、运行、报警、PLC 配置 — **Bootstrap 即要** |
| **windows_studio** | 调试人员 **Windows** | 难 case 复核、训练、下发 ONNX — **阶段三** |

---

## 待后续确认（非阻塞 Bootstrap）

| 项 | 状态 |
|----|------|
| D5 召回率验收阈值 | 阶段三前与现场共定 |
| D7 Jetson ↔ Win 静态 IP / rsync 路径 | 阶段三前 |
| PLC block vs command 模式 | 真机联调时 |
| S7 PUT/GET 是否开启 | 真机联调时 |
| stock 模型是否允许接 PLC 真机做联调信号测试 | **允许**（须标集成测试，非正式上岗） |
| Jetson SSH Host / 工作目录 | 团队备忘（D12） |
