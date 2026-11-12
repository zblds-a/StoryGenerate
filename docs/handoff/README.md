# 完整故事前后端交付

2026-11-12 当前交付只生成、确认和导出剧本，不启动声音、舞台或动画。

推荐获取完整远程代码：

```powershell
git fetch https://github.com/zblds-a/StoryGenerate.git codex/my-legend-story-generation
git switch -c codex/story-generation-review FETCH_HEAD
```

该分支根目录是 my-legend 工程，保留上游历史，不要将其合并到通用引擎主分支。当前完整集成提交 `4a36e382cc019fd9de44e7fdfb428c479d534194`，基于同事最新 `codex/theme-scenes-v0.6` 的 `2f8439970c92d12412fc3cb476fb1842210a66e3`；包含其启动和错误归因修复。对同事原仓库仍无写权限，远程代码位于我方仓库的独立交付分支。

备用补丁各为一个汇总提交：

| 文件 | 使用起点 | SHA256 |
|---|---|---|
| my-legend-interactive-story-sessions.patch | 最新上游 2f84399，首次接入 | e34e78882bca02c60a97c9c44cc6a79e85ea41c35655e9701d663378055ee5d2 |
| my-legend-story-only-update.patch | 已应用旧交付并停在 dd9edba | 66f14f3a953589178cdcf893dd0a35233d604f1ff8d9ea2688846ec57ec0756f |

在 my-legend 克隆的独立评审分支执行 `git am --3way "所选补丁的绝对路径"`。已经应用旧补丁时只用增量补丁；增量同时继承最新上游修复。不要在 StoryGenerate 通用引擎根目录应用。

两份补丁均已在各自起点创建独立 worktree，实际 git am 成功，最终 Git tree 均为 `2db07e5bd6ea7e7fe0075590deea16e0d51b959a`，与完整远程交付相同。汇总补丁提交 SHA 与远程保留历史的提交 SHA 不同，文件内容相同。机器证据见 manifest-20261112.json 和 patch-verification-20261112.json。

详细功能、启动、前后端契约及下游边界见 [当前交接说明](../故事生成独立交付与接入契约_20261112.md)，验证与未验事项见 [测试记录](../故事生成独立交付测试记录_20261112.md)。新入口默认关闭，不因合并补丁自动启用。
