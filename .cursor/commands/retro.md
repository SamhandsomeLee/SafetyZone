# retro

把 harness 自身交给 `harness-reviewer` 子代理做复盘与受限自改进。

请调用 `harness-reviewer` 子代理：读取 `.cursor/memory/` 下的 review-log / pitfalls / decisions，聚类反复出现的失败模式（≥2 次），对照现有 `.cursor/rules` 找出空白，提出**有界**的规则/子代理/命令改进建议（每条为窄改动、附依据、经边界自检），并明确列出「不该用规则解决」的项。核心不变量、`core-boundary`、git 授权为不可编辑宪法，不在建议范围。所有建议仅输出到对话，需我确认后才落地，子代理不改任何文件。
