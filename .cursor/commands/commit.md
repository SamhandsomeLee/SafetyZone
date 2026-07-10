# commit

在 `/review`（及必要修复/复查）通过后，按 `git-ruiles.mdc` 完成本 worktree 的 **git 提交工作流**。

**门禁通过后应自动执行提交**，不必再等用户说「提交 / commit」。若 review 未通过或仍有未清 BLOCKER/MAJOR，则只报告状态，不提交。

请按下列步骤执行：

1. **门禁核对**：确认对应任务的 `/review` 已无未清 BLOCKER/MAJOR，或我明示接受残留 MINOR。
2. **范围核对**（并行时）：只暂存「可改」路径；排除 `__pycache__/`、`*.egg-info/`、`*.engine`、`*.onnx`、大视频等。
3. **按 git-ruiles 提交**：并行跑 `git status` / `git diff` / `git log`；`git add` → `git commit`（`type(scope): 中文祈使句`；可附 `Milestone:` / `Sprint:` footer）；提交后汇报分支名与 hash。
4. **权限边界**：本命令只做当前分支 commit；**不** merge / rebase / push，除非我另行明确授权。

若我只说「准备提交」：只输出建议 commit message 与文件列表，等待确认后再提交。
