# 决策日志（Decision Log）

> harness / 落地取舍。产品决策 D1–D12 见 `docs/decisions.md`，此处不重复全文。
> 格式与控量见 `.cursor/rules/memory.mdc`。

## 条目格式

```
### D-NNN | <一句话结论> | <日期> | Sprint 或 "harness"
- 背景：
- 结论：
- 备选：
- 关联：
```

---

### D-001 | harness 从 substrate-panel 适配为 SafetyZone | 2026-07-10 | harness
- 背景：`.cursor/` 原为 Vue↔FastAPI↔ParameterKernel 项目拷贝，规则会误导 agent。
- 结论：重写 project-overview / core-boundary / layer-*；删除 host/ui/kernel 专属规则；任务单元用 Sprint/F ID；memory 与 `docs/decisions.md` 分工。
- 备选：只改 overview 保留旧 layer——否（globs 指向不存在路径）。
- 关联：`.cursor/rules/*`、agents、commands

### D-002 | 执行单元用 Sprint/F ID，不用 #NN | 2026-07-10 | harness
- 背景：substrate 执行计划按 commit #NN；SafetyZone 按阶段 Sprint 与 MIGRATION F ID。
- 结论：`/design` `/review` `/parallel` 均以 Sprint（如 UI-2、B4）或 F ID 为锚；review-log 用 `R-UI-2` 等形式。
- 关联：plan-designer、code-reviewer、parallel-planner

### D-003 | review 通过后自动 commit；合入 master 须用户审批 | 2026-07-10 | harness
- 背景：沿用原 harness 权限分层，适配本仓库。
- 结论：门禁通过后 agent 自动 `/commit`；merge/push 到 master 仍须用户明示。
- 关联：`git-ruiles.mdc`、`parallel-lanes.mdc`

### D-004 | 当前进度锚点：UI-1 已完成，下一刀 UI-2 → M-Bootstrap | 2026-07-10 | harness
- 背景：执行方案 §1.2 仍标 UI/frame_bridge ❌，但仓库已有 `fd8d7de` Sprint UI-1。
- 结论：编排与设计以仓库实况为准；划区编辑+config 保存为下一交付切片。
- 关联：执行方案 §4.0、validation_phases §1.3

### D-005 | 执行方案 v2.0：逐 commit 表 + Wave 并行 | 2026-07-10 | harness
- 背景：用户要求按 substrate-panel《执行计划》风格重写，并采纳并行方案五点决策。
- 结论：①Wave1 脊梁+旁路；②studio Wave2 立刻开壳；③策略 B（≤3 业务+1 studio）；④PLC 开发仿真、真机接口预留、现场 checklist；⑤一 commit 一调整点编号 #15 起为下一刀。
- 关联：`docs/安全区入侵检测系统_执行方案.md` v2.0

### D-006 | PLC：开发仿真、真机接口先留好 | 2026-07-10 | harness
- 背景：真机只在现场调试；开发期不能阻塞。
- 结论：默认 `simulate=true`；Gateway 抽象 + snap7 适配器可加载；现场只改 config/清单。
- 关联：执行计划 #25–#26、#32–#33

### D-007 | Wave 0 四契约冻结（并行前 SSOT） | 2026-07-13 | Wave0/#15
- 背景：Wave 1 多 lane 前必须钉死共享契约，禁止旁路各定一版。
- 结论（四条）：
  1. **FramePayload（Bootstrap）**：保持现字段 `station_id, frame_index, signal, zone_hit, detections, infer_ms, process_fps, fault, overlay_bgr`。**暂不**扩展 `plc_int16`；UI 拟写入由 `SignalAdapter.to_plc_int16(signal, fault=…)`（或等价）计算，状态栏调用（与 UI-1 `plc_sim_value` 同语义，#23 改委托 Adapter）。
  2. **划区写回**：编辑结果写入当前工位绑定的 `ParamGroup.slow_polygon` / `stop_polygon`；`ref_width`/`ref_height` 为坐标参考分辨率；经 `core.config.save_config` 原子写+备份；坐标相对 ref，判区时再 `scale_polygon` 到帧。
  3. **CameraStream**：USB（#24）与 `video_file` 均实现 `camera/base.py`：`start`/`stop`/`get_frame`；`get_frame()` **必须返回副本（`.copy()`）**；可选 `on_connection_changed` 供 USB 看门狗。
  4. **PLC 仿真/真机边界**：开发默认仿真。契约字段：`plc.enabled`（已有）+ **`plc.simulate`（待 Wave2 写入 `PlcConfig`，默认 true）**。`simulate=true` 或 `enabled=false` → 不连 snap7，仅展示拟写入 INT16。Gateway 抽象 + snap7 适配器 + 独立进程属 Wave2 #25–#26；Bootstrap 不实现 Gateway。
- 备选：Payload 内嵌 `plc_int16`——否（Bootstrap 避免改 `frame_bridge` 敏感面；Adapter 为 SSOT）。
- 关联：执行计划 #15；`app/frame_bridge.py`；`core/config.py`；`camera/base.py`；D-006；validation §1.3

### D-008 | SignalAdapter 映射表（signal → PLC INT16） | 2026-07-13 | Wave0/#15
- 背景：旧 `result_code` 与新 `signal` 禁止混写 PLC；设计 §6.3/§6.4。
- 结论：`SignalAdapter`（#20）为拟写入唯一映射 SSOT；与现 `plc_sim_value` 对齐：

  | 条件 | PLC INT16 | 说明 |
  |------|-----------|------|
  | `fault=True` | -1 | 故障优先；UI 标 FAULT，勿当 SAFE |
  | `signal==2` | 2 | STOP 确认 |
  | `signal==1` | 1 | SLOW 确认 |
  | `signal==0` 或 `-1` 或其他 | 0 | 安全侧（WARN 过渡与 SAFE 对 PLC 皆写 0） |

  命令字无匹配工位等扩展值 `3` 属真机 Gateway 后期，Bootstrap Adapter 可不实现。
- 备选：WARN(`0`) 单独映射非 0——否（§6.4 安全=0；与 UI-1 一致）。
- 关联：#20、#23；`app/signal_display.py`；设计 §6.3/§6.4

### D-009 | 进度锚点：Wave0 完成后下一刀 #17（UI-2 划区） | 2026-07-13 | Wave0/#15
- 背景：D-004/D-005 锚定 #15；契约落地后旁路可开。
- 结论：#15/#16 合入 master 后下一交付为脊梁 **#17 划区编辑**；旁路 #20/#21 可并行；#23 依赖 #20 合入。
- 关联：执行计划进度表；`/parallel` 启动清单
