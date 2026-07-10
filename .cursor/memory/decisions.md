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
