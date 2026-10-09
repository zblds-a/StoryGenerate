# 模型节点提示词维护位置

先确认调用的是哪条执行链。正式的“待审批 Plan → 获批 Job → StoryDelivery”
使用 `drama_engine.workflow`；旧 `run_pipeline()` 是兼容 Graph，两个入口的
提示词目前**不在同一个文件**。

| 需要修改的节点 | 主要位置 | 修改内容 |
| --- | --- | --- |
| 正式工作流：结构化大纲 | `4-引擎代码/drama_engine/workflow/adapters.py` 的 `LLMPlanGenerator.generate` | system、user payload、模板快照及修订反馈 |
| 正式工作流：正文与播放前简介 | 同文件 `ApprovedPlanLLMExecutor.execute` | 剧本文案、节拍与时长、`preview_blurb` 要求 |
| 正式工作流：逐句情绪／语气／重音 | 同文件 `LLMPerformanceAnnotator.annotate` | 演绎注释与定向修复提示 |
| 正式工作流：发布质量判断 | 同文件 `QualityDecision` 调用附近 | 大纲一致性、连续性和分级判断提示 |
| 旧 Graph：题材、角色、结构、分集、台词等 | `4-引擎代码/drama_engine/prompts.py` | 各节点的 `system`／`user` 组装函数 |
| 旧 Graph：音频适配特殊提示 | `4-引擎代码/drama_engine/nodes/episode.py` | 音频编辑、修复等节点内提示 |
| 旧 Graph：长篇规划 | `4-引擎代码/drama_engine/longform_planner.py` | 长篇规划提示 |
| LLM 结构化输出通用要求 | `4-引擎代码/drama_engine/llm/base.py` 的 `SCHEMA_INSTRUCTION` | 所有 `complete_structured` 调用都会附加的 JSON Schema 指令 |

修改**模型选择、温度或 token 上限**，去
`4-引擎代码/drama_engine/llm/router.py` 的 `MODEL_ROUTING`；具体模型名和超时
在 `4-引擎代码/drama_engine/core/settings.py`，也可由 `STORY_LLM_*_MODEL`
等环境变量覆盖。这些不是提示词。修改叙事硬规则，应改
`3-规则库/*.json`；新增可复用剧情结构，应按 `docs/TEMPLATE_AUTHORING.md`
创建版本化模板，不复制节点 Prompt。

每次修改会影响生成结果的提示词时：

1. 在 `4-引擎代码/drama_engine/config.py` 增加 `PROMPT_VERSION`，使缓存和
   Plan 规则指纹失效。已审批快照不能在新提示词下悄悄漂移。
2. 调整对应结构化 Schema 与单元测试；不要靠放宽质量门来适配模型输出。
3. 跑全量单元测试、PostgreSQL 集成测试；发布／质量验收须用真实模型，
   记录 Git SHA、Prompt 版本和实际路由模型，不得用 Mock 补齐失败样本。

`tests/acceptance/real_create_matrix.py` 是真实模型验收入口，不是正式提示词
来源；`scripts/generate_spy_demo_draft.py` 只生成编辑草稿，不产生获批
`StoryDelivery`。改它们不会改变正式工作流的节点提示词。
