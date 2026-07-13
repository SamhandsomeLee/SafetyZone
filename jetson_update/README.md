# `jetson_update` — Jetson 模型接收侧

Windows studio 只下发 **ONNX**；本包在 Jetson 上完成 receiver → build_engine → acceptance → hotswap（阶段三）。

## 目录约定

| 路径 | 用途 | Commit |
|------|------|--------|
| `jetson_update/testset/` | 场内冻结测试集 + MANIFEST | #46 |
| `jetson_update/inbox/` | studio 投放的待处理 `.onnx`（默认 inbox） | #47 |
| `jetson_update/inbox/processed/` | 已触发管线的 ONNX（避免重复扫描） | #47 |

`inbox/` 与 `*.onnx` 默认被 `.gitignore` 忽略；板上路径可用 `--inbox` 覆盖。

## Receiver（#47）

```bash
PYTHONPATH=. python -m jetson_update.receiver --once
PYTHONPATH=. python -m jetson_update.receiver --inbox /path/to/inbox --watch --interval 2
```

- **投放**：与 `windows_studio.export_send.send` 一致——将完整 `.onnx` 拷入 inbox 根目录。
- **可选完整标记**：若 inbox 中存在任意 `*.done`，则每个候选须有同名 sidecar（如 `model.onnx.done`）才触发。
- **触发后**：文件移入 `inbox/processed/`；回调默认为 stub `on_onnx_received`（#48 起接 build_engine）。

详见模块 docstring：`jetson_update/receiver.py`。
