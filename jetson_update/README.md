# `jetson_update` — Jetson 模型接收侧

Windows studio 只下发 **ONNX**；本包在 Jetson 上完成 receiver → build_engine → acceptance → hotswap（阶段三）。

## 目录约定

| 路径 | 用途 | Commit |
|------|------|--------|
| `jetson_update/testset/` | 场内冻结测试集 + MANIFEST | #46 |
| `jetson_update/inbox/` | studio 投放的待处理 `.onnx`（默认 inbox） | #47 |
| `jetson_update/inbox/processed/` | 已触发管线的 ONNX（避免重复扫描） | #47 |
| `jetson_update/candidates/` | 候选 FP16 `.engine`（`build_engine` 默认输出） | #48 |

`inbox/` 与 `*.onnx` 默认被 `.gitignore` 忽略；板上路径可用 `--inbox` 覆盖。

## Receiver（#47）

```bash
PYTHONPATH=. python -m jetson_update.receiver --once
PYTHONPATH=. python -m jetson_update.receiver --inbox /path/to/inbox --watch --interval 2
```

- **投放**：与 `windows_studio.export_send.send` 一致——将完整 `.onnx` 拷入 inbox 根目录。
- **可选完整标记**：若 inbox 中存在任意 `*.done`，则每个候选须有同名 sidecar（如 `model.onnx.done`）才触发。
- **触发后**：文件移入 `inbox/processed/`；回调默认为 stub `on_onnx_received`。可选接线：`scan_once(..., callback=make_build_callback())`（#48）；完整管线串接见 #49。

详见模块 docstring：`jetson_update/receiver.py`。

## build_engine（#48）

本机 `trtexec` 将 inbox/任意 ONNX 编为候选 FP16 engine（参数风格对齐 `tools/build_engine.sh`）。

```bash
PYTHONPATH=. python -m jetson_update.build_engine --onnx path/to/model.onnx
PYTHONPATH=. python -m jetson_update.build_engine --onnx model.onnx --out jetson_update/candidates --dry-run
```

- **输出**：默认 `jetson_update/candidates/<stem>.engine`。
- **无 trtexec**：清晰报错；`--dry-run` 只打印命令并写占位标记（测试/CI）。
- **receiver 可选接线**：`from jetson_update.build_engine import make_build_callback`。
