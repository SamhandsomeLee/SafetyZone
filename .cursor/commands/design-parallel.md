# design-parallel

把《执行方案》接下来一段转交给 `parallel-planner` 子代理做**并行编排设计**（拆分可并行 / 必须串行，不写代码）。

请调用 `parallel-planner` 子代理，对我指定的任务列表（未指定则从真实下一未完成刀起扫一段，并与我确认范围）执行编排：

1. 先读 `docs/安全区入侵检测系统_执行方案.md` 候选行，并用 `.cursor/memory/review-log.md` 与**仓库实况**校正进度（勿盲信过期勾选）。
2. 对照 `.cursor/rules/parallel-lanes.mdc`，产出依赖与冲突矩阵。
3. 可并行部分拆成 Parallel Lane briefs；必须串行部分合并为 Serial Spine（方案 A：每步完整 `/design → 执行 → /review → 修复 → 提交`）。
4. 给出 worktree 命名与启动建议；区分 lane 内自动提交与合入 master（须我审批）。

编排只输出到对话，供我确认。确认后我再 `/parallel` 或 Multitask 启动。
