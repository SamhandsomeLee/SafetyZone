# parallel

在我已确认 `/design-parallel` 编排结果的前提下，生成**启动清单**（仍不代 merge；各 lane 在 review 通过后自动 commit）。

请根据对话中**最近一次我已确认**的 `parallel-planner` 输出（若无确认记录，先提醒我跑 `/design-parallel` 并确认）：

1. **核对**：复述 Parallel Lanes 与 Serial Spine 的任务列表、各 lane 可改/禁改摘要。
2. **Worktree**：列出需创建的 worktree/分支清单（只列命令示例，**不执行** git 写操作，除非我明确授权）。
3. **启动 prompt**：为每个 Parallel lane 与 Spine 各生成可粘贴的 agent 启动说明，必须包含：目标 Sprint/F ID、可改/禁改、强制流程 `/design → 执行 → /review → 修复 → 提交`、禁止擅自 merge/push。
4. **建议启动顺序**。
5. **合入提醒**：commit ≠ merge，合入 master 由我审批。

本命令不替代 `/design-parallel`，也不替代各 lane 的 `/design` / `/review` / `/commit`。
