# windows_studio — Windows GPU 训练闭环

调试人员在 **Windows 11 + NVIDIA GPU** 上使用的阶段三工具：从 Jetson 拉难 case → 复核标注 → 本机微调 → 导出 **ONNX** → 下发 Jetson inbox。

| 侧 | 职责 |
|----|------|
| **本工具（Win）** | 标注复核、YOLO 微调、导出 ONNX、发 inbox |
| **Jetson `ui/`** | 产线监视、划区、PLC（**不要**在本工具里做） |
| **Jetson `jetson_update/`** | 收 ONNX → 编 engine → 冻结集召回闸 → 热切换 |

设计对标工业视觉平台交互骨架（三栏 + 向导），场景固定为 **person 检测 + 召回优先**；不做通用标注器 / 算法画布。详见设计方案 §8.2。

---

## 1. 环境要求

| 项 | 建议 |
|----|------|
| OS | Windows 11 64-bit（开发冒烟也可在 Linux/Jetson 开 GUI，**真训练请用 Win GPU**） |
| Python | ≥ 3.10 |
| GPU | NVIDIA + 新驱动；CUDA 与 PyTorch/ultralytics 匹配 |
| 磁盘 | 难 case + runs 建议 ≥ 20GB 可用 |
| 网络 | 与 Jetson 同局域网（直连/静态 IP）；数据不出厂 |

---

## 2. 安装（Windows）

在仓库根目录：

```powershell
cd E:\SafetyZone
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[windows,dev]"
```

可选依赖组 `windows` 含：`PySide6`、`ultralytics`、`onnxruntime-gpu`、`opencv-python-headless`。

验证：

```powershell
python -c "import PySide6, ultralytics; print('ok')"
python -m windows_studio.app
pytest tests/windows_studio/ -q
```

---

## 3. 与 Jetson 的数据流

```text
Jetson outbox/（难 case 原图+预标注）
        │  本地路径 或  rsync://user@jetson:/path/outbox
        ▼
  windows_studio（ingest → review → train → export）
        │  仅 .onnx
        ▼
Jetson inbox/  →  receiver → build_engine → acceptance → hotswap
```

- **只传 ONNX**，不要传 `.engine`（engine 仅 Jetson 本机 `trtexec` 编译）。
- Jetson 侧说明：[jetson_update/README.md](../jetson_update/README.md)
- 端到端演练清单：[docs/benchmarks/e2e_production_TEMPLATE.md](../docs/benchmarks/e2e_production_TEMPLATE.md)

### outbox / inbox 路径示例

```powershell
# 已把 Jetson 目录映射到本机（SMB/scp 同步目录）
python -m windows_studio.app --gui `
  --outbox D:\jetson_share\outbox `
  --inbox  D:\jetson_share\inbox

# 或 CLI 向导（默认 dry-run）
python -m windows_studio.app --run `
  --outbox D:\jetson_share\outbox `
  --inbox  D:\jetson_share\inbox

# 真训练 + 真导出（需 GPU + ultralytics）
python -m windows_studio.app --run --real `
  --outbox D:\jetson_share\outbox `
  --inbox  D:\jetson_share\inbox `
  --epochs 50
```

`rsync://user@host:/path/outbox` 形式亦支持（见 `ingest` / `export_send`）。

---

## 4. 启动方式

### 4.1 GUI（推荐调试人员）

```powershell
cd E:\SafetyZone
.\.venv\Scripts\Activate.ps1
python -m windows_studio.app --gui
python -m windows_studio.app --gui --workspace D:\sz_studio_data
```

界面（#52–#54）：

| 区域 | 内容 |
|------|------|
| **顶** | 步进：拉取 → 复核 → 训练 → 下发 → 评估 |
| **左** | 样本列表；过滤：全部 / 未确认 / 已确认 / 疑似漏检 |
| **中** | 画布：原图 + 框；空格切换 原图 / 标注 / 标注+预测 |
| **右** | 当前步工具；「运行向导」；安全提示 **宁可多标、勿漏标** |

操作提示：

1. 配置好 `--outbox` / `--inbox`（或先点「运行向导」dry-run 灌演示数据）。
2. **复核**：确认 / 拖框 / 删误框 / 补漏框；优先处理「疑似漏检」「未确认」。
3. **训练**：看 epoch / ETA / loss 曲线，可中断。
4. **评估**：召回大字号；点漏检样本会跳回复核并过滤（**不替代** Jetson 冻结集验收闸）。

在 Linux/Jetson 上仅看界面时：

```bash
DISPLAY=:0 PYTHONPATH=. python3 -m windows_studio.app --gui
```

### 4.2 CLI 向导

```powershell
python -m windows_studio.app                    # 打印四步说明
python -m windows_studio.app --run              # dry-run 全链路（无 GPU 可冒烟）
python -m windows_studio.app --run --real       # 真训 + 真导出
python -m windows_studio.app --run --workspace .\windows_studio_data --epochs 30
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `--run` | off | 跑 ingest→review→train→export→send |
| `--gui` | off | 开三栏 GUI |
| `--workspace` | `windows_studio_data` | 本机工作区根目录 |
| `--outbox` | 空（dry-run 会造演示 outbox） | Jetson outbox 本地路径或 rsync URL |
| `--inbox` | 空（默认 workspace/inbox） | Jetson inbox 本地路径或 rsync URL |
| `--epochs` | 1 | 训练轮数 |
| `--real` | off | 关闭 dry-run，走真 CUDA / 真导出 |

### 4.3 子模块单独调用

```powershell
python -m windows_studio.ingest.cli pull --source D:\outbox
python -m windows_studio.review_ui.cli --auto-confirm
python -m windows_studio.dataset.cli build
python -m windows_studio.train.cli --dry-run
python -m windows_studio.train.cli --epochs 30
python -m windows_studio.export_send.cli export --weights runs\...\best.pt --dry-run
python -m windows_studio.export_send.cli send --onnx export\model.onnx --inbox D:\inbox
```

---

## 5. 工作区目录（`--workspace`）

默认 `windows_studio_data/`（可 gitignore，勿提交现场图）：

```text
windows_studio_data/
├── ingest/          # 拉取暂存
├── review/          # 复核队列 + review_manifest.json
├── dataset/
│   ├── train/
│   └── test/        # 与冻结集纪律配合；训练前 overlap 校验
├── runs/            # ultralytics 训练输出
├── export/          # ONNX 等
└── wizard_result.json
```

训练前勿把 **Jetson 冻结测试集**（`jetson_update/testset/`）混入 train；可用：

```bash
# 在 Jetson 或已同步目录上
python tools/check_testset_overlap.py --testset jetson_update/testset --train <train_images>
```

---

## 6. 包结构

```text
windows_studio/
├── app.py                 # 入口：CLI / GUI
├── wizard.py              # 四步编排（#45）
├── shell/                 # 三栏主壳 + 步进条（#52）
├── ingest/                # 拉 outbox（#40）
├── review_ui/             # 复核数据层 + 画布/过滤（#41/#53）
├── dataset/               # train/test 隔离 + overlap（#42）
├── train/                 # LocalCuda 微调 + 进度 GUI（#43/#54）
├── eval_ui/               # 召回优先评估 + 漏检回环（#54）
└── export_send/           # 导出 ONNX + 发 inbox（#44）
```

向导步骤：

1. **拉取** — `ingest`
2. **复核** — `review_ui`（GUI 重心）
3. **训练** — `dataset` + `train`
4. **下发** — `export_send`（仅 ONNX）
5. **评估** — `eval_ui`（辅助回环；上线闸仍在 Jetson `acceptance`）

---

## 7. 测试

```powershell
# Windows
pytest tests/windows_studio/ -q

# Linux / CI 无显示器
$env:QT_QPA_PLATFORM="offscreen"   # PowerShell
# bash: QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 -m pytest tests/windows_studio/ -q
```

---

## 8. 常见问题

| 问题 | 处理 |
|------|------|
| `No module named PySide6` | `pip install -e ".[windows]"` |
| GUI 打不开 / 无窗口 | 确认在 Win 桌面会话；远程桌面需 GPU/显示正常 |
| `--real` 训练失败 | 检查 NVIDIA 驱动、CUDA、`nvidia-smi`、ultralytics 版本 |
| 想传 `.engine` 到 Jetson | **不要**；只发 ONNX，板上 `trtexec` / `jetson_update.build_engine` |
| 评估页召回很高就上线？ | **否**；必须以 Jetson 冻结集 `acceptance`（D5）为准 |
| 与运行 UI 搞混 | Studio 只在 Win；监视/划区只用 Jetson `python -m app.main` |

---

## 9. 相关文档

| 文档 | 内容 |
|------|------|
| [设计方案 §8](../docs/安全区入侵检测系统_设计方案.md) | 闭环与 Studio UX |
| [执行方案 Wave 2/3.B](../docs/安全区入侵检测系统_执行方案.md) | #40–#45、#52–#55 |
| [jetson_update/README](../jetson_update/README.md) | 接收 / 验收 / 热切换 |
| [E2E 演练模板](../docs/benchmarks/e2e_production_TEMPLATE.md) | 全链手测清单 |

---

## 10. 明确不做（防过度设计）

- 不把 CVAT / Label Studio 嵌进来  
- 不做缺陷分割画笔 / 算法画布 / 八大工业模块照搬  
- 不把 Studio 迁回 Jetson 运行 UI  
- 不在 Studio 侧替代冻结集召回验收闸  
