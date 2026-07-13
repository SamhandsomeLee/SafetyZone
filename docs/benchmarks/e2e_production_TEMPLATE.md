# Production E2E 演练清单（M11 候选）

> 对照 [validation_phases.md §2](../validation_phases.md) 与执行方案 **#51**。  
> 复制本模板为 `e2e_production_YYYYMMDD.md` 填写板上证据。  
> **代码侧**：#46–#50 已合入本分支即可开本清单；**M11 正式通过**须现场冻结集人标 + D5 填数 + 本表全链证据齐全。

| 字段 | 值 |
|------|-----|
| 日期 | |
| Jetson / JetPack | |
| Win GPU 主机 | |
| 分支 / commit | `wt/spine-wave3` / |
| 当前运行 engine | `models/…`（切换前） |
| 候选 ONNX / engine | |
| D5 阈值 | `docs/decisions.md` 共定值，或占位 `0.95` |
| 测试人 | |

---

## 0. 前置条件（开演前核对）

| # | 前置 | 状态 (✅/❌/⏳) | 证据 / 备注 |
|---|------|----------------|-------------|
| P1 | **#46–#50 代码已合**：testset / receiver / build_engine / acceptance / hotswap | | `git log --oneline` 含 #46–#50 |
| P2 | **冻结集人标**：`jetson_update/testset/` 已填帧；`MANIFEST.json` `locked=true`、`never_train=true` | | 空集只能 dry-run，**不能**标 M8/M9/M11 正式通过 |
| P3 | **D5** 召回阈值已与现场共定并写入 `docs/decisions.md` | | 未填则 CLI 默认 `0.95` **占位**；acceptance 可跑，M9/M11 仍为候选 |
| P4 | **D7** Jetson ↔ Win 网络：静态 IP / SSH / `rsync` 路径可达 | | outbox 拉、inbox 送 |
| P5 | Jetson 本机有 `trtexec`（真编 engine）；Win 有 CUDA + `ultralytics`（真训） | | dry-run 可不齐 |
| P6 | 训练集与冻结集 overlap 已通过 | | 见步骤 0b |

### 0b. 冻结集格式 / overlap（建议先跑）

```bash
# Jetson 仓库根
PYTHONPATH=. python tools/check_testset_overlap.py \
  --testset jetson_update/testset --manifest-only
# 现场填满后加 --require-files；有训练集时：
# PYTHONPATH=. python tools/check_testset_overlap.py \
#   --testset jetson_update/testset --train /path/to/train/images
```

| 预期 | 证据栏 |
|------|--------|
| 退出码 `0`；`[OK] MANIFEST …` | 粘贴输出或日志路径： |

---

## 失败路径（全程硬闸，勿跳过）

| 场景 | 必须行为 | 证据栏 |
|------|----------|--------|
| **acceptance 拒绝**（召回 < D5 / 空冻结集 / dry-run） | **不得** hotswap / promote；运行中仍用旧 engine | |
| **build_engine 失败** | 不进入 acceptance；inbox 产物可留在 `processed/` 排查 | |
| **promote 异常 / warmup 失败** | 保留旧版；`switched=False` | |
| **回滚演练** | `rollback` 恢复上一版 engine；预览/信号恢复正常 | |

---

## 链路总览

```text
Jetson outbox（难 case）
    │  rsync / 本地路径（D7）
    ▼
windows_studio：拉取 → 复核 → 训练 → 导出 ONNX → 送 inbox
    │
    ▼
jetson_update：receiver → build_engine → acceptance（召回闸）
    │                    │
    │                    └─ 拒绝 → 停止（不切换）
    ▼ 仅通过
hotswap promote → 运行中切换
    ▼
rollback 演练 → 恢复旧 engine
```

---

## 1. Jetson：难 case 进入 outbox

难 case = 报警快照 / 低置信 / 近区 / 疑似漏检等现场帧（原图 ± 预标注），落到约定 **`outbox/`**（仓库默认 gitignore；板上路径按 D7）。

| 项 | 内容 |
|----|------|
| **命令 / 操作** | 运行 UI 或采集流程产生报警/难 case，确认文件出现在 outbox（例：`/data/safetyzone/outbox` 或仓库旁 `outbox/`） |
| **预期** | 至少若干可读图像（jpg/png）；可选同 stem 的 YOLO txt / meta |
| **证据栏** | outbox 路径 + `ls` 摘要： |

---

## 2. Windows studio：拉取 → 复核 → 训练 → 导出 → inbox

在调试人员 **Windows GPU** 机（或同源路径挂载）执行。工作区默认 `windows_studio_data/`。

### 2.1 拉取（ingest）

```bash
# 列表（不拷贝）
python -m windows_studio.ingest.cli --source /path/to/outbox list
# 或 rsync://user@jetson:/path/outbox

# 拉取到 staging
python -m windows_studio.ingest.cli --source /path/to/outbox pull \
  --staging-dir windows_studio_data/ingest
```

| 预期 | 证据栏 |
|------|--------|
| 列表可见难 case；pull 后 staging 有图 | |

### 2.2 复核（review）

```bash
python -m windows_studio.review_ui.cli --auto-confirm
# 正式演练宜 GUI 改框：python -m windows_studio.app --gui
```

| 预期 | 证据栏 |
|------|--------|
| 样本已确认/改框；未把冻结集帧混入训练 | |

### 2.3 训练集隔离 + 微调

```bash
python -m windows_studio.dataset.cli build
python -m windows_studio.train.cli --epochs 50   # 现场回合；冒烟可用更小
# 无 GPU 勿宣称真训：加 --dry-run
```

| 预期 | 证据栏 |
|------|--------|
| `runs/.../weights/best.pt`；训练日志无「进冻结集」 | |

### 2.4 导出 ONNX + 发送 Jetson inbox

```bash
python -m windows_studio.export_send.cli export \
  --weights runs/.../weights/best.pt
python -m windows_studio.export_send.cli send \
  --onnx export/model.onnx \
  --inbox rsync://user@jetson:/path/to/SafetyZone/jetson_update/inbox
# 或本地可达路径：--inbox /mnt/jetson/.../jetson_update/inbox
```

| 预期 | 证据栏 |
|------|--------|
| **仅** `.onnx` 到达 Jetson `jetson_update/inbox/`（**不**传 `.engine`） | ONNX 路径 / rsync 日志： |

### 2.5 一键向导（可选）

```bash
python -m windows_studio.app --run \
  --outbox /path/to/outbox \
  --inbox rsync://user@jetson:/path/jetson_update/inbox \
  --real
# 无 GPU 联调：去掉 --real（默认 dry-run，占位产物，不可上线）
```

| 预期 | 证据栏 |
|------|--------|
| `wizard_result.json` 四步均为成功语义；`--real` 时产物可部署 | |

---

## 3. Jetson：receiver → build_engine → acceptance

仓库根，建议 `PYTHONPATH=.`。

### 3.1 receiver（扫描 inbox）

```bash
PYTHONPATH=. python -m jetson_update.receiver --once -v
# 持续监听：--watch --interval 2
```

| 预期 | 证据栏 |
|------|--------|
| 发现 `.onnx`；移入 `jetson_update/inbox/processed/`（除非 `--no-mark`） | |

### 3.2 build_engine（本机 FP16）

```bash
PYTHONPATH=. python -m jetson_update.build_engine \
  --onnx jetson_update/inbox/processed/<model>.onnx \
  --out jetson_update/candidates
```

| 预期 | 证据栏 |
|------|--------|
| 产出 `jetson_update/candidates/<stem>.engine`；`trtexec` 成功 | engine 路径 / 日志： |

### 3.3 acceptance（冻结集召回闸 · M9）

```bash
PYTHONPATH=. python -m jetson_update.acceptance \
  --engine jetson_update/candidates/<stem>.engine \
  --testset jetson_update/testset \
  --threshold <D5或0.95>
```

| 预期（通过） | 证据栏 |
|--------------|--------|
| 打印 `PASS`（或等价）；`hotswap: allowed`；召回 ≥ 阈值 | 完整一行指标： |
| **失败路径** | `REJECT` / `hotswap: forbidden` → **停止**，跳到 §5 记录原因，**不**做 §4 promote |

空冻结集必然拒绝（设计如此）。`--dry-run` **永不**宣称生产通过。

---

## 4. 热切换（仅 acceptance 通过）

运行中 backend 持有 `EngineHotSwap`（`InferenceWorker` / `RunController`）。CLI 无独立 `python -m jetson_update.hotswap`；用运行路径或 Python API。

### 4.A 运行中（推荐正式演练）

1. 启动 UI / pipeline，确认当前 active engine。  
2. 在已挂载 `RunController` / worker 的上下文调用：

```python
# 示意：acceptance 已通过后
from pathlib import Path
from jetson_update.acceptance import run_acceptance, AcceptanceConfig
from jetson_update.hotswap import RuntimeHotswap

acc = run_acceptance(AcceptanceConfig(
    engine_path=Path("jetson_update/candidates/<stem>.engine"),
    testset_dir=Path("jetson_update/testset"),
    recall_threshold=0.95,  # 换成 D5
))
assert acc.allows_hotswap, acc.reason

# controller / worker 已在跑：
result = controller.promote_engine(
    "jetson_update/candidates/<stem>.engine",
    acceptance=acc,
)
assert result.switched, result.reason
```

| 预期 | 证据栏 |
|------|--------|
| `switched=True`；预览仍流畅；UI 不再仅 STOCK（若已切微调） | active_path 前后： |

### 4.B 拒绝路径抽检（建议同次演练）

对**故意不合格**候选（或空集 dry-run 结果）调用 `promote_engine(..., acceptance=fail_result)`：

| 预期 | 证据栏 |
|------|--------|
| `switched=False`；`active_path` 仍为旧 engine | |

---

## 5. 回滚演练

在 §4 成功 promote **之后**：

```python
rb = controller.rollback_engine()
assert rb.switched, rb.reason
# 期望 active_path 回到 promote 前的 engine
```

| 预期 | 证据栏 |
|------|--------|
| 旧 engine 恢复；推理/信号正常；无残留候选误用 | previous → active： |

若 `rollback unavailable (no previous engine retained)` → 记录为演练失败（未先成功 promote 或底层未保留 previous）。

---

## 6. 端到端勾选（M11）

| # | 步骤 | 结果 (✅/❌/⏭) | 证据摘要 |
|---|------|----------------|----------|
| 1 | 难 case → outbox | | |
| 2 | studio 拉取 / 复核 | | |
| 3 | 训练 + 导出 ONNX | | |
| 4 | 下发 inbox | | |
| 5 | receiver + build_engine | | |
| 6 | acceptance 通过 | | |
| 6f | （对照）acceptance 拒绝不切换 | | |
| 7 | hotswap promote | | |
| 8 | rollback 恢复旧版 | | |

### 结论

- [ ] **M11 候选文档完成**（本清单步骤可执行；代码 #46–#51 齐）
- [ ] **M11 正式通过**（上表 1–8 均有板上证据；P2 冻结集锁定；P3 D5 已写入 decisions）
- [ ] 未通过（阻塞项：）

---

## 附录 A · Dry-run 冒烟（无真 engine / 无冻结集 / 无 Win GPU）

用于验证 CLI 接线与文档命令可跑；**不得**据此宣称 M8/M9/M11 正式通过。

```bash
# 仓库根；或：bash tools/e2e_production_dry_run.sh
set -e
PYTHONPATH=.

# A1 冻结集 MANIFEST 格式
python tools/check_testset_overlap.py --testset jetson_update/testset --manifest-only

# A2 studio 向导干跑（占位 outbox/inbox，不需 CUDA）
python -m windows_studio.app --run

# A3 build_engine dry-run（需任意存在的 .onnx；可用占位）
mkdir -p /tmp/sz_e2e_smoke
printf 'not-a-real-onnx' > /tmp/sz_e2e_smoke/smoke.onnx   # 仅测「文件存在」路径前请换真实 onnx
# 若无真实 onnx：跳过 A3，或用 studio dry-run 写出的占位：
#   windows_studio_data/export/*.onnx
python -m jetson_update.build_engine \
  --onnx windows_studio_data/export/*.onnx \
  --out /tmp/sz_e2e_smoke/candidates --dry-run || true

# A4 acceptance dry-run（跳过推理；永不 PASS 生产）
python -m jetson_update.acceptance \
  --engine models/stock/yolov8s.engine \
  --testset jetson_update/testset --dry-run || true
# 空集非 dry-run 亦应 REJECT + hotswap forbidden：
python -m jetson_update.acceptance \
  --engine models/stock/yolov8s.engine \
  --testset jetson_update/testset || true

# A5 receiver 单次扫描（inbox 可空）
python -m jetson_update.receiver --once

# A6 单测门（无板上 GPU 也可）
python -m pytest tests/jetson_update/ tests/app/test_hotswap_wiring.py -q
```

| 冒烟项 | 结果 | 证据 |
|--------|------|------|
| A1 manifest | | |
| A2 studio --run | | |
| A3 build --dry-run | | |
| A4 acceptance dry-run / 空集拒绝 | | |
| A5 receiver --once | | |
| A6 pytest hotswap/acceptance | | |

---

## 附录 B · 路径速查

| 角色 | 路径 |
|------|------|
| 难 case | `outbox/`（板上约定，D7） |
| Studio 工作区 | `windows_studio_data/` |
| Jetson inbox | `jetson_update/inbox/` → `processed/` |
| 候选 engine | `jetson_update/candidates/*.engine` |
| 冻结集 | `jetson_update/testset/` + `MANIFEST.json` |
| 模块说明 | `jetson_update/README.md`、`windows_studio/README.md` |

---

## 附录 C · 相关决策与里程碑

| 项 | 说明 |
|----|------|
| D5 | 召回阈值；未共定前 CLI 默认 `0.95` 占位 |
| D7 | Jetson↔Win rsync / 静态 IP |
| D8 | 训练仅在 Win GPU 本机 |
| M8 | 冻结集锁定 + 基线 |
| M9 | acceptance 闸正式生效（须 D5） |
| M10 | studio 功能向导（#45） |
| **M11** | 本 E2E + 回滚（#51） |
| M12 | studio 可视化 UI（#52+，不挡本闸） |
