# SafetyZone — 安全区入侵检测系统

工业产线安全区入侵检测：多路 USB 相机 / 录制视频 → YOLOv8 person 检测 → 判区 + 状态机 → PLC 联动 + 报警录像。

## 文档

- [设计方案](docs/安全区入侵检测系统_设计方案.md)
- [执行方案](docs/安全区入侵检测系统_执行方案.md)（**v1.3 Remote-Jetson**）
- [验证阶段](docs/validation_phases.md)
- [决策记录](docs/decisions.md)

## 开发方式（当前）

| 机器 | 用途 |
|------|------|
| **Win 本机** | `pytest tests/`、git、文档 |
| **Jetson（SSH / Cursor Remote）** | export、TRT、运行 UI、Bootstrap 验证 |

Jetson 快速开始见 [validation_phases.md §1.6](docs/validation_phases.md)。

## Win 本机：core 单测

```powershell
cd E:\SafetyZone
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest tests/ -v
```

## Jetson：Bootstrap Day 0

```bash
cd ~/SafetyZone && git pull
pip install -e ".[dev,jetson]"
mkdir -p models/stock data/sample_videos
yolo export model=yolov8s.pt format=onnx imgsz=640 opset=18 simplify=True dynamic=False
mv yolov8s.onnx models/stock/
trtexec --onnx=models/stock/yolov8s.onnx --saveEngine=models/stock/yolov8s.engine --fp16
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
jetson_update/  # 模型接收与验收（阶段三）
windows_studio/ # 调试人员 Win GPU 闭环工具（阶段三）
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
