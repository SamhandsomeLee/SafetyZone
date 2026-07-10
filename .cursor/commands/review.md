# review

把当前改动转交给 `code-reviewer` 子代理做代码审查。

请调用 `code-reviewer` 子代理，对当前未提交的改动（若我在下方指定了文件/模块，则聚焦该范围）执行完整代码审查：先读《执行方案》对应任务验收与《设计方案》相关章节建立基线，再对照核心不变量、core 边界、app/ui/detect/plc 分层、信号语义、线程模型、测试门禁逐项检查，按 BLOCKER/MAJOR/MINOR 分级输出审查报告。

审查结束时提醒主代理：存在 BLOCKER/MAJOR 则修复后须重跑针对性复查；通过后**自动**走 `/commit`（无需再等我批「提交」）。并行场景下 commit ≠ merge——合入 master 仍须我审批。
