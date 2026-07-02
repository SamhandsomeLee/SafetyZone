# 验证阶段说明（Bootstrap / Production）

> 与 [decisions.md](decisions.md) D9–D11 配套。实施与验收以本文为准。

---

## 总览

```
Bootstrap（现在）                    Production（场内数据就绪后）
─────────────────                   ─────────────────────────────
COCO stock YOLOv8s                  windows_studio 微调模型
Jetson 完整运行 UI                  场内冻结测试集
视频文件 / USB / PLC 仿真→真机      jetson_update acceptance
集成验证 · 未过场内验收              安全验收 · 可热切换上线
```

**安全定位不变**（见设计方案 §2）：视觉为监督层；零漏检靠独立硬件安全回路。Bootstrap 通过 **不等于** 可正式承担产线安全职责。

---

## 一、Bootstrap 阶段

### 1.1 目标

在 Jetson 上通过 **完整运行程序（PySide6 运行 UI + 检测编排）** 验证：

- stock FP16 engine 可加载、可推理；
- 视频/相机 → 检测 → 判区 → 状态机 → 报警指示 **全链路**；
- 划区、配置保存、运行/停止等 **现场操作路径** 可走通。

**不是目标：** 仅 CLI 跑 YOLO；用 COCO 指标替代场内安全验收。

### 1.2 模型与数据

| 项 | 说明 |
|----|------|
| 模型 | Ultralytics **YOLOv8s COCO 预训练** → ONNX → Jetson `trtexec --fp16` → `models/stock/yolov8s.engine` |
| 数据 | 优先 **录制视频**（D2）；其次 USB 相机；可选 COCO val 人物图/短视频做 smoke |
| 不要求 | ≥50 张现场图、`baseline_recall.py` 现场 GT 报告 |

### 1.3 Jetson 运行 UI — Bootstrap 最小验收清单

| # | 能力 | 必须 | 备注 |
|---|------|------|------|
| 1 | 监视预览（≥1 路） | ✅ | ~15FPS；视频文件或 USB |
| 2 | slow/stop **划区编辑** | ✅ | 参考分辨率、保存到 config |
| 3 | 运行 / 停止 | ✅ | |
| 4 | 信号显示 `-1/0/1/2` | ✅ | 仪表盘或状态栏 |
| 5 | 报警指示（SLOW/STOP） | ✅ | 人进入停区应能触发 |
| 6 | 视频文件源（D2） | ✅ | Bootstrap 首选输入 |
| 7 | 界面标注「STOCK · 集成测试」 | ✅ | 未过场内验收 |
| 8 | USB 相机 | 建议 | 有设备再接 |
| 9 | PLC **仿真**模式 | ✅ | D11；UI 显示拟写入信号 |
| 10 | PLC 真机 | 分步 | Bootstrap 后期 |
| 11 | 报警录像（快照+短片段） | 建议 | D4 |
| 12 | anomaly 示教 | ❌ | D1 仅 person |
| 13 | jetson_update / 热切换 | ❌ | 阶段三 |

**线程纪律：** 检测 / IO 不在 UI 线程（设计方案 §6.7、§7）。

### 1.4 Bootstrap 操作步骤（验收用）

1. Jetson 安装：JetPack 6.x、PySide6、TensorRT、OpenCV（GStreamer）、项目依赖。
2. 准备 stock 模型：
   ```bash
   yolo export model=yolov8s.pt format=onnx imgsz=640 opset=18 simplify=True dynamic=False
   trtexec --onnx=yolov8s.onnx --saveEngine=models/stock/yolov8s.engine --fp16
   ```
3. 准备输入：含人员的 `demo.mp4` 或 USB 相机。
4. 启动运行程序（`app/main.py` 或打包入口）。
5. UI：选择 `video_file` 源 → 划 slow/stop 区 → 保存 config。
6. 运行：观察预览、检测框（可选）、信号从 `-1` → `0` → `2`（人进 STOP 区）。
7. PLC 仿真：确认 UI 显示拟写入值与信号一致。
8. （建议）STOP 边沿检查录像目录是否有快照。
9. 记录：`docs/benchmarks/jetson_bootstrap_YYYYMMDD.md`（FPS、延迟、问题列表）。

### 1.5 Bootstrap 里程碑

| 里程碑 | 完成定义 |
|--------|----------|
| **M2** | Jetson 上 stock FP16 engine 推理成功 |
| **M-Bootstrap** | **运行 UI 端到端**：视频 → 划区 → 运行 → 报警与信号正确；config 可保存 |
| **M3** | 离线编排骨架可复现信号（本机 pytest/demo，可与 Bootstrap 并行） |

---

## 二、Production 阶段

### 2.1 目标

场内数据采集 → `windows_studio` 复核微调 → 下发 ONNX → **冻结测试集召回验收** → 热切换。

### 2.2 硬前置

- **冻结测试集**建立并锁定（永不进训练）— 针对 **微调模型** 上线，非 Bootstrap stock 模型必需。
- D5 召回阈值与现场 / 安全负责人共定。
- 训练仅在 **调试人员 Windows GPU** 本机完成（D8）。

### 2.3 与 Bootstrap 的衔接

| 场景 | 行为 |
|------|------|
| 继续用 stock engine 做集成调试 | 允许；保持 UI「集成测试」标识 |
| 微调模型上线 | **必须**过 `jetson_update/acceptance` |
| 场内难 case | Jetson `outbox/` → Win `windows_studio` |

### 2.4 Production 里程碑（阶段三）

| 里程碑 | 完成定义 |
|--------|----------|
| **M8** | 场内冻结测试集锁定 + stock/当前 engine 基线指标 |
| **M9** | jetson_update 验收闸生效 |
| **M10** | windows_studio 四步向导可用 |
| **M11** | E2E：难 case → 训练 → 下发 → 验收 → 热切换 → 回滚演练 |

---

## 三、常见误区

| 误区 | 正确理解 |
|------|----------|
| Bootstrap = 只验 YOLO | Bootstrap = **Jetson 运行 UI + 全流水线** |
| COCO 过了就能正式上岗 | 仅集成验证；上岗看场内冻结集 + D5 |
| windows_studio 替代 Jetson UI | studio 只做训练闭环；监视/划区在 Jetson |
| 必须先有 A100 | 不需要；导出在 Jetson 或 Win 即可 |
| 必须先有 PLC 真机才能验 UI | PLC **仿真**可先过 UI 验收（D11） |
