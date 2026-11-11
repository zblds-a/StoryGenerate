# My Legend 集成补丁交付

`my-legend-interactive-story-sessions.patch` 是完整 Git mailbox 补丁，包含前后端示范、生产适配、嵌入引擎、测试、契约和说明，共两个提交。

- 原仓库：`frostdogstarscream/my-legend`。
- 基线：`b7c24db2cc4a6c52b270c07ff2aa0e14c1850a77`，分支 `codex/theme-scenes-v0.6`。
- 本地集成最终提交：`dd9edba153dbc98571021900d98a9ff68b21859a`。
- 当前账号 zblds-a 对原仓库推送返回 403，因此由你方 StoryGenerate 仓库发布补丁，不冒称已推送同事仓库。

在同事的 my-legend 克隆中执行：

```powershell
git fetch origin
git switch -c integration/interactive-story-review origin/codex/theme-scenes-v0.6
git am --3way "补丁文件的本机完整路径"
```

已在独立 worktree 从上述基线实际执行 git am，两次提交均成功，最终 Git tree 与本地评审集成提交完全相同。目标分支若已前进，仍需评审冲突和运行项目测试；不代表任何后续基线均可无冲突应用。

同事在有写权限的账号下推送其评审分支，按功能与联调说明准备 PostgreSQL、独立 Worker、角色目录和媒体资产。不要在 StoryGenerate 引擎仓库根执行这个补丁。

默认功能关闭；真实样本与全量回归有明确未通过项，详见测试验收报告，不能把补丁交付视为发布通过。
