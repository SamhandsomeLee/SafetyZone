# SafetyZone — 安全区入侵检测系统

工业产线安全区入侵检测：多路 USB 相机 / 录制视频 → YOLOv8 person 检测 → 判区 + 状态机 → PLC 联动 + 报警录像。

## 文档

- [设计方案](docs/安全区入侵检测系统_设计方案.md)
- [执行方案](docs/安全区入侵检测系统_执行方案.md)
- [验证阶段](docs/validation_phases.md)
- [决策记录](docs/decisions.md)
- **[windows_studio 使用说明](windows_studio/README.md)**（Win GPU 复核 / 训练 / 下发 ONNX）
- [jetson_update 使用说明](jetson_update/README.md)（收 ONNX → 验收 → 热切换）

## 开发方式（当前）

| 机器 | 用途 |
|------|------|
| **Win 本机** | `pytest`、git、文档；**阶段三** `windows_studio` 训练闭环 |
| **Jetson（SSH / Cursor Remote）** | TRT、运行 UI、Bootstrap；**阶段三** `jetson_update` |

Jetson 快速开始见 [validation_phases.md §1.6](docs/validation_phases.md)。

## Win 本机：core 单测

```powershell
cd E:\SafetyZone
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest tests/ -v
```

## Jetson：Bootstrap Day 0（Win 导出 → scp → 板上编 engine）

**Win 本机（有网）** 导出 ONNX 并推到 Jetson：

```powershell
cd E:\SafetyZone
yolo export model=yolov8s.pt format=onnx imgsz=640 opset=18 simplify=True dynamic=False
scp yolov8s.onnx nvidia@<jetson-ip>:~/Desktop/SafetyZone/models/stock/
# 可选：含人测试视频
scp demo.mp4 nvidia@<jetson-ip>:~/Desktop/SafetyZone/data/sample_videos/
```

**Jetson（无需外网）** 编 FP16 engine + M2 冒烟：

```bash
cd ~/Desktop/SafetyZone
pip install -e ".[dev,jetson]"
bash tools/offline_check.sh
bash tools/build_engine.sh
python tools/jetson_infer_smoke.py --engine models/stock/yolov8s.engine
```

大文件（`*.onnx` / `*.engine` / `demo.mp4`）不进 git，统一 Win scp 同步。

## 阶段三：Windows Studio（简述）

完整步骤见 **[windows_studio/README.md](windows_studio/README.md)**。

```powershell
pip install -e ".[windows,dev]"
python -m windows_studio.app --gui
python -m windows_studio.app --run --real --outbox <outbox> --inbox <inbox>
```

## 仓库结构

```
core/           # 平台无关：判区、状态机、配置（单测覆盖）
detect/         # 推理后端（Jetson: trt_backend）
camera/         # USB 采集 + 录制视频文件源
plc/            # S7-1200/1500 (snap7)
record/         # 快照 + 短片段
ui/             # Jetson 运行 UI (PySide6)
app/            # 编排
windows_studio/ # 调试人员 Win GPU 闭环 — 详见 windows_studio/README.md
jetson_update/  # 模型接收与验收 — 详见 jetson_update/README.md
configs/
tests/
```

## 决策摘要

| 项 | 选择 |
|----|------|
| D1 | 仅 person |
| D2 | USB + 录制视频（Bootstrap 首选视频） |
| D8 | 无 A100；Win GPU 训练（阶段三） |
| D9 | Bootstrap = Jetson 全 UI；Production = 场内冻结集 |
| D12 | **Remote-SSH 在 Jetson 主开发/验证** |
