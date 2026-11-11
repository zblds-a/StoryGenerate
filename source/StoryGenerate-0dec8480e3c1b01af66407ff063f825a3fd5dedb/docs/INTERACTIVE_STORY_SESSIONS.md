# 交互创作会话 v1：实施与联调

后续真实 API、PostgreSQL 和全量回归结果以 [2026-11-11 测试验收报告](故事生成交互升级_测试验收报告_20261111.md) 为准；下文保留首次离线实现时的记录。给前后端同事的完整说明见 [功能与接入联调方案](故事生成交互升级_功能说明与前后端接入联调方案_20261111.md)。

本功能为独立、默认关闭的新入口。旧 StoryWorkflow 和旧创作页保留。实现分布在两个仓库：

- 本地 `4-引擎代码/drama_engine/interactive/`：契约、SQLAlchemy 持久会话、命令/事件、逐幕生成、模型流、背景任务。
- 集成副本 `H:/Projects/my-legend-handoff-20261111`，分支 `codex/interactive-story-sessions`：同步引擎模块，以及生产 API、确认后媒体桥接、Worker 和 uni-app 页面。

## 已实现流程

`directions → directions_ready → outlining → outline_ready → writing → script_ready → media_pending → media_ready`

从一句灵感开始时跳过方向选择。仅剧本输出确认后进入 `confirmed`。`media_ready` 表示已建立原生产 flow，并不表示音频制作已经完成；最终进展进入原作品页查看。

大纲确认及剧本确认均校验版本和指纹。长剧默认六集，只展开和生成当前集；确认后可创建下一集会话，继承角色快照、系列主线、历史事实及前集正文。

题材映射固定为：国风奇幻 general/G10/R11，冒险成长 general/G12/R10，悬疑推理 mystery/G11/R6，生活治愈 general/G05/R5；实际规则由现有 StoryStrategyResolver 装载，注入 Plan 和 Writer。

生成中命令先入库，当前幕完成后进入 `change_ready`。服务返回实际影响起点和 `pending_change_fingerprint`，用户确认后提升执行轮次、保留前文、重规划受影响范围，再确认新大纲。只改一幕会保留其余正文，新的连续性仍需用户阅读确认；不冒称已有全面语义审查。

已确认剧本修改会保留原交付与媒体引用，并创建新版本；不修改已发出的媒体请求。确认后的新 flow 消费冻结的 StoryDelivery/RenderManifest，继续走原音频和基础舞台链路。背景图只下载备用，不接入舞台素材目录。

## API 与前端约定

所有接口位于业务 `/api/v1`，沿用原认证。JSON 包装为 `{code:0,message:'ok',data:...}`。新接口的 404/409 错误使用 FastAPI `detail`，前端专用客户端已兼容。

| 方法/路径 | 输入或输出 |
|---|---|
| GET `/story-options` | 能力开关、选项、默认值；关闭时只返回 enabled=false |
| POST `/story-sessions` | Creation，返回会话完整快照；不执行模型调用 |
| GET `/story-sessions` | 当前用户最近 100 个会话摘要及可续写标记 |
| GET `/story-sessions/{id}` | 会话快照、available_actions、当前大纲/剧本指纹、背景状态 |
| POST `/story-sessions/{id}/commands` | Command，返回 receipt 和最新快照 |
| GET `/story-sessions/{id}/events?after=N` | SSE，支持 Last-Event-ID；连接约 50 秒后重连 |
| GET `/story-sessions/{id}/events?after=N&poll=true` | 非流式端增量读取；每批最多 200 事件，按返回 last_seq 继续 |
| GET `/story-sessions/{id}/backgrounds/{scene_key}/image` | 仅当前用户、当前 ready 图片，认证下载 |
| GET `/story-sessions/{id}/export` | StoryDelivery 与背景规格/制品引用 |

JSON Schema 见 `docs/contracts/interactive/`。所有命令携带 command_id、expected_revision。相同 command_id 与输入返回原 receipt，换输入报冲突；会话读取、事件订阅和重连不会提交制作。

关键命令绑定：

- `select_direction`：target_id=返回的方向 ID。
- `confirm_outline`：target_id=plan_id，fingerprint=outline_fingerprint。
- `change/revise_outline`：option_id 或 text；可带 target_id=scene_key；scope=scene/following。未指定目标时优先调整未开始内容。
- `confirm_change`：fingerprint=pending_change_fingerprint。
- `confirm_script`：target_id=delivery.story_version_id，fingerprint=script_fingerprint。
- `next_episode`：返回 next_creation，使用其幂等键创建子会话。
- `retry_background`：target_id=scene_key。
- `retry`：仅重试已知结果的失败阶段；未知调用拒绝自动重放。

事件信封固定 event_id/seq/session_id/revision/generation_epoch/type/occurred_at/payload。预览事件带 attempt_id、chunk_index，替换时按执行轮次/尝试分组。正式结果以 ready 事件和快照为准。首期事件不清理，不存在静默丢失的保留窗口；将来启用清理前必须补充 cursor-expired 协议。

用户离开页面只断开订阅，不取消任务；重新进入从服务器快照恢复。新入口记住当前用户上次会话，并可选择已确认系列续写。前端在版本冲突时更新快照，要求用户再次核对选择。

## 部署与能力开关

需要 Python 3.12、生产环境 PostgreSQL；SQLite 仅供测试。安装集成的 StoryGenerate editable 包和生产包 `[production]`。生产包新增 SQLAlchemy/Pillow 依赖。不要用本地旧 engine 替代集成 engine。

在与原服务一致的配置环境中运行：

```powershell
# 仅增量建表；不请求模型或图片服务
python ops/my-legend/run_interactive_story_worker.py --migrate

$env:MY_LEGEND_INTERACTIVE_STORIES = '1'
# 只有网关实际支持 SSE chat/completions 时启用；默认按幕完整返回
$env:STORY_INTERACTIVE_STREAMING = '1'
python ops/my-legend/run_interactive_story_worker.py
```

业务 API 进程也需要 `MY_LEGEND_INTERACTIVE_STORIES=1` 并重启，前端创作页才显示“一起创作”入口。独立 Worker 不由旧启动器自动启动，运维需单独托管；不要对已有运行服务盲目重启。正常模型变量沿用 `DRAMA_LLM_*` 与既有 `STORY_LLM_*` 配置。

数据库新增 `interactive_story_sessions`，存储会话、事件、命令、工作租约和调用证据；新增 `interactive_story_sources` 登记用户确认过的媒体来源。前者由 session Store 显式 migrate 建表，后者为生产迁移 007。历史任务与 StoryVersion 不回写。关闭功能只移除新入口/路由；不要删除新表或仍在使用的制品。

### 背景图片

同时配置 `STORY_IMAGE_BASE_URL`、`STORY_IMAGE_API_KEY`、`STORY_IMAGE_MODEL` 才启用。首个适配器使用 `/images/generations`，要求支持 `b64_json` 和 `1536x1024` 请求；不自动下载供应商任意 URL。其他接口实现 `generate(spec) -> (image_bytes, model_id)` 即可接入 BackgroundWorker。

图片在确认分幕后开始，最多两个后台线程并行；按规格哈希复用同用户已成功制品。适配器返回的图片居中裁切为 1536×864 PNG，记录原尺寸、交付尺寸、哈希、模型和供应商。更改构图或场景使旧图失效；未启用时标记 disabled，仍提供提示词。

## 失败与成本边界

- 正文每幕顺序创作并完成演绎标注；首期演绎标注尚未与下一幕写作并行。不宣称总耗时已经缩短，先通过 metrics 比较首次可见/首幕/整集耗时。
- 原生 SSE 只发布已完整解析的白名单字段，不暴露 raw JSON、思考内容或密钥。断流不自动再次付费请求；结构不合法仍沿用一次结构修复，带独立尝试 ID。
- 会话模型调用上限 64；记录成功/失败调用、未知用量。供应商 Usage 仍区分 reported/estimated/unavailable，用户销售计费与真实金额对账未实现。
- Worker 的外部工作租约为 15 分钟；过期标记 WORKER_RESULT_UNKNOWN，禁止静默重放，需运维先核对供应商与生产任务。不是无限自动恢复。
- 图片失败可由用户显式重试；图片调用与未知结果保留记录。进程丢失时不能假定供应商未计费。
- 取消阻止未来调用/当前轮次发布，已经发出的请求可能完成。媒体创建与确认版本使用固定幂等键；进程崩溃后的外部结果未知不自动再次提交。
- 技术 READY 与用户确认均不代表语义质量、低龄儿童适用性或听感审核通过。仍沿用现有受众策略，不新增低龄儿童承诺。

## 验证及发布门

新增测试覆盖合同/状态、并发确认、修改与定稿竞态、事件重放、权限隔离、迟到结果、SSE、真实生成适配器的结构和演绎检查、图片 16:9 与缓存。前端补充 SSE 分块测试。

本轮没有使用真实供应商、生产数据库或硬件，因此发布前必须使用真实角色与模型完成短剧/系列小样本，核验新增会话到原媒体 flow 的版本、来源归属、配音与舞台结果，并对内容/听感及耗时做独立对照。未配置图片服务时不得展示虚构成功图片。

### 2026-11-11 本次检查结果

- 本地全量单元：631 passed / 1 skipped（本地 Python 3.10 缺 Pillow，图片测试跳过；在集成隔离环境已执行）。
- 集成引擎全量单元：687 passed，使用独立 Python 3.12 环境。
- 最新新增会话、流式/图片及真实媒体桥接合同测试：19 passed，不调用真实供应商。
- 前端：类型检查通过，130 项测试通过，H5 构建通过。保留原有外置字体/背景文件的构建提示。
- 生产全量：814 passed / 167 skipped / 49 failed。剩余失败日志包含未配置的 `runtime/my-legend-production/workflows.json`、缺少 scipy、websocket 与 langgraph.checkpoint.sqlite 等运行依赖。该结果不是全量发布通过；未提供 PostgreSQL 故障矩阵或真实媒体结果。

生产全量输出保存在集成副本 `runtime/my-legend-production/tests-interactive-production.txt`。本轮未启动后台服务、迁移实际数据库或触发供应商费用；新入口仍需按上文显式启用并托管 Worker。
