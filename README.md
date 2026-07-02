# SafetyZone — 安全区入侵检测系统

工业产线安全区入侵检测：多路 USB 相机 / 录制视频 → YOLOv8 person 检测 → 判区 + 状态机 → PLC 联动 + 报警录像。

## 文档

- [设计方案](docs/安全区入侵检测系统_设计方案.md)
- [执行方案](docs/安全区入侵检测系统_执行方案.md)
- [决策记录](docs/decisions.md)

## 阶段一：离线 core（当前）

```powershell
cd E:\SafetyZone
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest tests/ -v
```

## 仓库结构

```
core/           # 平台无关：判区、状态机、配置（单测覆盖）
detect/         # 推理后端接口
camera/         # USB 采集 + 录制视频文件源
plc/            # S7-1200/1500 (snap7)
record/         # 快照 + 短片段
app/            # 编排
jetson_update/  # 模型接收与验收
windows_studio/ # 调试人员 Win GPU 闭环工具
configs/        # 配置模板
tests/
```

## 决策摘要（2026-07-01）

| 项 | 选择 |
|----|------|
| D1 | 仅 person |
| D2 | USB + 录制视频导入 |
| D3 | S7-1200/1500 |
| D4 | 快照 + 短片段 |
| D8 | 厂外 A100 研发；现场 Win GPU 训练 |
