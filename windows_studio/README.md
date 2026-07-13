# windows_studio

调试人员在 **Windows 11 + NVIDIA GPU** 上使用的训练闭环工具（阶段三）。与 Jetson 运行 UI（`ui/`）分离：现场监视与划区在边缘机，难 case 复核、微调、导出 ONNX 在本机完成。

## 用途

| 环节 | 说明 |
|------|------|
| 数据来源 | Jetson 现场 `outbox/` 难 case（报警快照等） |
| 训练 | 本机 GPU 运行 Ultralytics YOLO 微调（非云端 A100） |
| 产物 | **仅 ONNX** 下发至 Jetson `jetson_update` inbox；`.engine` 只在 Jetson 本机编译 |

Jetson 侧接收扫描见 `jetson_update/README.md` / `python -m jetson_update.receiver`（#47）。

依赖可选组：`pip install -e ".[windows]"`（PySide6、ultralytics、onnxruntime-gpu 等）。

## 包结构（#28 空壳）

```
windows_studio/
├── app.py              # 单一入口（CLI / 可选 GUI）
├── ingest/             # #40 拉取 outbox
├── review_ui/          # #41 复核与改框
├── dataset/            # #42 训练/测试集隔离
├── train/              # #43 LocalCuda 微调
└── export_send/        # #44 导出 ONNX + 发送 inbox
```

## 启动

默认 **CLI** 打印四步向导说明；加 `--run` 可走通整条链路（默认 dry-run，无 GPU 可冒烟）：

```bash
python -m windows_studio.app              # 说明
python -m windows_studio.app --run        # 干跑 ingest→review→train→export→inbox
python -m windows_studio.app --run --outbox /path/to/outbox --inbox /path/to/inbox
python -m windows_studio.app --run --real # 需 Windows GPU + ultralytics（真训/真导出）
```

可选 GUI（需 PySide6）：

```bash
python -m windows_studio.app --gui
```

各子模块亦可单独调用：

```bash
python -m windows_studio.ingest.cli pull --source /path/outbox
python -m windows_studio.review_ui.cli --auto-confirm
python -m windows_studio.dataset.cli build
python -m windows_studio.train.cli --dry-run
python -m windows_studio.export_send.cli export --weights runs/.../best.pt --dry-run
python -m windows_studio.export_send.cli send --onnx export/model.onnx --inbox /path/inbox
```

## 四步向导（#45 已串联）

1. **拉取难 case** — `ingest`：配置 outbox 路径或 rsync，列出待复核样本。
2. **复核标注** — `review_ui`：确认 / 改框 / 删 / 补预标注。
3. **微调训练** — `train`：本机 GPU `yolo train`；`dataset` 负责 train/test 物理隔离。
4. **导出并下发** — `export_send`：导出 ONNX，送入 Jetson inbox（不传 `.engine`）。

当前 **#40–#45** 已落地各子包与向导串联；不依赖 Jetson `ui/` / `app/`。
