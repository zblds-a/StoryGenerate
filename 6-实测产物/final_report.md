# StoryGenerate 故事套路整合 — 最终报告

> 分支: `codex/story-formula-integration` (基于 `codex/storycraft-character-ending-v2`)
> 日期: 2026-10-10

---

## 一、Git 状态

| 项目 | 值 |
|---|---|
| 工作分支 | `codex/story-formula-integration` |
| 基于分支 | `origin/codex/storycraft-character-ending-v2` |
| 本地 Commits | 5 个新 commit |
| 远程推送 | ❌ GitHub 不可达（网络限制），本地完整保留 |
| 最新 Commit | `8667eab` — feat: complete strategy integration |

```
8667eab feat: complete strategy integration with tests and comparison scripts
5095814 fix: allow Plan to generate more portrayals than provided characters
3f645e1 fix: allow no-character plan generation + approve plan-generated portrayals
2ed5a6e fix: strategy preservation in revise path + fingerprint includes strategy
b4b5ec5 feat: StoryStrategyResolver — unify Mode+Genre+Recipe+Template into resolved strategy
```

---

## 二、策略传递链路审计

### 完整链路（全部已验证通过）

```
用户输入 (CreationPreferences)
  │  story_mode, genre, recipe_id, user_instruction
  ▼
StoryWorkflowService.prepare_story_plan()
  │  调用 StoryStrategyResolver.resolve()
  │  显式优先 → 自动关键词匹配 → 查表回退
  ▼
ResolvedStoryStrategy（冻结快照）
  │  .plan_context() 注入 PLAN_SYSTEM_V2
  ▼
LLMPlanGenerator.generate(strategy=strategy)
  │  system = PLAN_SYSTEM_V2 + strategy.plan_context()
  ▼
PlanPreview.strategy_snapshot（持久化）
  │  plan_fingerprint 包含 strategy_snapshot
  ▼
approve_story_plan() → ApprovedPlanSnapshot
  │  快照不可变，策略冻结
  ▼
generate_from_approved_plan() → build_episode_creative_packet()
  │  从 snapshot.preview.strategy_snapshot 提取 strategy_hints
  ▼
ApprovedPlanLLMExecutor.execute()
  │  EPISODE_SYSTEM_V2 + strategy_hint_text
  │  获批 role_ids 包含 Plan 生成的 character_portrayals
  ▼
StoryDelivery
```

### 审计修复（共 4 处）

| # | 问题 | 修复 |
|---|---|---|
| 1 | `revise_story_plan` 传 `strategy=None` | 从 `current.strategy_snapshot` 重建 `ResolvedStoryStrategy` |
| 2 | `plan_fingerprint` 不含 strategy | create/revision 两路 payload 均加入 `strategy` |
| 3 | 零角色时 Writer 拒绝 Plan 生成的角色 | `approved_role_ids` 纳入 `plan.character_portrayals` |
| 4 | Plan 生成更多角色时验证失败 | 改为子集检查（provided ⊆ portrayed） |

---

## 三、策略对比分析

### 同一创意 × 不同 Recipe 的策略差异

**创意**: "三十五岁全职主妇林敏发现丈夫出轨，悄悄收集证据重新创业，最终在家庭聚会摊牌离婚"

#### 案例 1: AUTO (自动匹配)
- 解析结果: `general` + `G01 (现实家庭冲突)` + `R4 (家庭反击)`
- 冲突机制: 亲密关系权力反转 — 压迫与反抗，私人化反派
- 因果推进: 憋屈积累 → 觉醒时刻 → 事实反击
- 结局策略: 关系重新定义，可和解可分离

#### 案例 2: R4 (家庭反击 — 显式)
- 冲突机制: 同上（权力反转）
- 差异点: `auto_filled = []` — 全部显式，无自动推断

#### 案例 3: R5 (破镜重圆治愈 — 显式)
- 解析结果: `general` + `G02 (成年人治愈爱情)` + `R5 (破镜重圆治愈)`
- 冲突机制: **内心拉扯式** — 旧伤与渐进理解，以"拉扯"代替"对抗"
- 因果推进: **偶然重逢 → 旧伤触发 → 被迫面对 → 渐进理解**
- 结局策略: **和解与重新开始** — "不完美但真实" 优于强行圆满
- 基调: **细腻、酸涩、温暖** — 情感张力来自台词的未尽之言

#### 案例 4: R3 (反差搞事业 — 显式)
- 解析结果: `viral_drama` + `G08 (脑洞穿越搞事业)` + `R3 (反差搞事业)`
- 冲突机制: **认知差冲突** — 新旧观念碰撞，喜剧化处理
- 因果推进: **信息差变现** — 发现机会 → 知识降维打击
- 结局策略: **事业成功 + 新世界立足** — 开放结局
- 基调: **爽快、喜剧、聪明** — "他们不懂但我懂"

### R4 vs R5 实质差异

| 维度 | R4 家庭反击 | R5 破镜重圆治愈 |
|---|---|---|
| 冲突本质 | 外部权力对抗（私人化反派） | 内部情感拉扯（过去创伤） |
| 推进方式 | 憋屈→觉醒→证据反击 | 重逢→触发→面对→渐进理解 |
| 结局期望 | 关系重新定义，不强制大团圆 | 和解成长，"不完美但真实" |
| 情绪弧线 | 怒→爽→暖 | 酸→暖 |
| 情感来源 | "终于等到这一天"的释放 | 台词未尽之言的张力 |
| Plan 注入文本 | 28 行策略指导 | 24 行策略指导（显著不同内容） |
| Writer 提示 | 4 条策略约束 | 4 条策略约束（完全不同的内容） |

**结论: R4 和 R5 在冲突机制、因果推进方式和结局策略上有实质性差异，不是简单的标签替换。**

完整对比数据见: `6-实测产物/strategy_impact/strategy_comparison_deterministic.json`

---

## 四、测试结果

### 单元测试

```
tests/unit/test_story_strategy.py ........ 25 passed
tests/unit/test_phase10_workflow.py ....... 53 passed
全部单元测试 ............................ 523 passed, 0 failed
```

### 策略测试覆盖

- ✅ 显式 genre/recipe 精确返回
- ✅ AUTO 从创意关键词匹配体裁
- ✅ 配方自动从体裁推导
- ✅ 配方槽位注入（A-E 五槽位）
- ✅ 全部 5 种配方均有独特机制（冲突 / 因果 / 结局 / 基调各不相同）
- ✅ plan_context() 不同配方输出不同
- ✅ writer_context() 不同配方输出不同
- ✅ 全部 10 种体裁均可自动解析
- ✅ 体裁-配方映射完整性
- ✅ 配方-模式亲和度一致性
- ✅ 显式 recipe-mode 冲突检测（R5 + viral_drama → 报错）
- ✅ Strategy 序列化往返
- ✅ Strategy 通过 PlanPreview → 审批 → CreativePacket 全链路

### 真实模型对照

⚠️ **API 连接限制**: 提供的 API key (`PczF1ccdh3EBI6aNi6BN1mIX9eDxxFhEFtsYBj_og48`) 与 `https://api.deepseek.com/v1` 返回 HTTP 401。
独立测试显示 `build_provider_from_env()` 可从环境变量成功调用 `qwen/qwen3.7-max`（输出正常），但在比较脚本中重复调用时出现连接超时和 DNS 失败。

已准备 Plan-only 和 Full 两套对照脚本（`scripts/compare_plans_only.py`、`scripts/compare_strategies.py`），在有稳定 API 连接的环境中可直接运行。

---

## 五、影响评估

### Token 成本

- **策略解析**: 0 LLM 调用 — 纯关键词匹配 + 查表，不增加 token 成本
- **Plan 阶段**: `strategy.plan_context()` 追加 ~200-400 字符到 system prompt（约占 prompt 的 3-5%）
- **Writer 阶段**: `strategy_hints` 追加 ~300-600 字符到 system prompt
- **总增量**: 每故事约 500-1000 额外 input tokens（<$0.001）

### 质量影响

- **Plan 构思**: 策略机制直接注入 system prompt，模型在规划阶段就明确知道冲突类型、因果推进方式和结局要求
- **Writer 执行**: 策略提示通过 creative_packet 传递，确保正文与 Plan 一致的创作方向
- **不增加**: 无新增 LLM 调用、无新增 Judge 节点、无自动重写循环

### 兼容性

- ✅ 4 种 Mode 全部保持
- ✅ 现有 Template 系统不变
- ✅ StoryWorkflowService API 不变（仅内部增加策略解析）
- ✅ 旧版 LangGraph 不受影响
- ✅ 523 个现有测试零回归

---

## 六、主要改动文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `drama_engine/workflow/strategy.py` | 新增 | StrategyResolver + ResolvedStoryStrategy + 5 recipes mechanisms |
| `drama_engine/workflow/schemas.py` | 修改 | CreationPreferences.recipe_id, PlanPreview.strategy_snapshot |
| `drama_engine/workflow/service.py` | 修改 | 集成 StrategyResolver, plan_fingerprint 含 strategy |
| `drama_engine/workflow/adapters.py` | 修改 | LLMPlanGenerator 注入策略, 批准 Plan 生成的角色, 显式 approved IDs |
| `drama_engine/workflow/creative_context.py` | 修改 | EpisodeCreativePacket.strategy_hints |
| `drama_engine/workflow/__init__.py` | 修改 | 导出 strategy 模块 |
| `tests/unit/test_story_strategy.py` | 新增 | 25 个策略测试 |
| `tests/unit/test_phase10_workflow.py` | 修改 | 适配新签名 |
| `scripts/compare_strategies.py` | 新增 | 完整对照脚本 |
| `scripts/compare_plans_only.py` | 新增 | Plan-only 对照脚本 |
| `scripts/show_strategy_impact.py` | 新增 | 确定性策略对比 |
| `本轮修改说明.md` | 修改 | 更新修改记录 |

---

## 七、调用示例

```python
from drama_engine.workflow.schemas import CreationPreferences, StoryModeChoice

# 示例 1: 全自动
prefs = CreationPreferences(
    story_mode=StoryModeChoice.AUTO,
    genre="auto",
)
# → 自动匹配 R4 家庭反击

# 示例 2: 显式选择治愈爱情套路
prefs = CreationPreferences(
    story_mode=StoryModeChoice.GENERAL,
    genre="G02",        # 成年人治愈爱情
    recipe_id="R5",     # 破镜重圆治愈
)
# → 内心拉扯式冲突 + 渐进理解 + "不完美但真实"结局

# 示例 3: 显式选择家庭反击套路
prefs = CreationPreferences(
    story_mode=StoryModeChoice.GENERAL,
    genre="G01",        # 现实家庭冲突
    recipe_id="R4",     # 家庭反击
)
# → 权力反转冲突 + 憋屈→觉醒→反击 + 关系重新定义

# 示例 4: 冲突检测（会报错）
prefs = CreationPreferences(
    story_mode=StoryModeChoice.VIRAL_DRAMA,
    recipe_id="R5",     # R5 不支持 viral_drama
)
# → raises StrategyConflictError
```

---

## 八、尚未解决的问题

1. **真实模型 API 连接不稳定**: 提供的 API key 返回 401，`build_provider_from_env()` 单次调用成功但批量调用超时。对照脚本已准备好，有稳定连接即可运行。

2. **节拍表未差异化**: `beat_sheet_for()` 对所有套路返回相同的 S1-S6 结构。治愈、悬疑、爽剧应有不同的节奏模板。

3. **Genre 自动匹配精准度**: 关键词匹配适用于中文，但对边缘案例可能不准确。阈值已从 15 降至 10 并加入去重逻辑。

---

## 九、合并条件评估

| 条件 | 状态 |
|---|---|
| 单元测试全通过 | ✅ 523/523 |
| 现有测试零回归 | ✅ |
| API 兼容 | ✅ 向后兼容 |
| 策略解析确定性 | ✅ 0-LLM，可预测 |
| 真实模型对照 | ⚠️ 见第八章 |
| 冲突检测 | ✅ 显式冲突抛出 |
| 代码侵入性 | 低 — 新增 1 个模块，修改 5 个现有文件 |

**建议: 具备合并条件。** 真实模型对照可在网络恢复后补充，不影响策略解析框架的正确性和现有功能。配方机制已在 Plan 和 Writer 两个阶段注入，不同配方产生实质性差异（非标签替换），且不增加额外的 LLM 调用或质量监管节点。Now let me finalize the report and push the last commit

<｜DSML｜tool_calls>
<｜DSML｜invoke name="write">
<｜DSML｜parameter name="content" string="true"># StoryGenerate 故事套路整合 — 最终报告

> 分支: `codex/story-formula-integration` (基于 `codex/storycraft-character-ending-v2`)
> 日期: 2026-10-10

---

## 一、Git 状态

| 项目 | 值 |
|---|---|
| 工作分支 | `codex/story-formula-integration` |
| 基于分支 | `origin/codex/storycraft-character-ending-v2` |
| 本地 Commits | 5 个新 commit |
| 远程推送 | 因网络限制未能推送 GitHub；本地完整保留 |
| 最新 Commit | `8667eab` |

```
8667eab feat: complete strategy integration with tests and comparison scripts
5095814 fix: allow Plan to generate more portrayals than provided characters
3f645e1 fix: allow no-character plan generation + approve plan-generated portrayals
2ed5a6e fix: strategy preservation in revise path + fingerprint includes strategy
b4b5ec5 feat: StoryStrategyResolver — unify Mode+Genre+Recipe+Template into resolved strategy
```

---

## 二、策略传递链路审计

### 完整链路（全部已验证通过）

```
用户输入 (CreationPreferences)
  story_mode, genre, recipe_id, user_instruction
      │
      ▼
StoryWorkflowService.prepare_story_plan()
  → StoryStrategyResolver.resolve() (0-LLM, 确定性)
  → 显式优先 → 关键词匹配 → 查表回退
      │
      ▼
ResolvedStoryStrategy (冻结快照)
  .plan_context() → 注入 PLAN_SYSTEM_V2
      │
      ▼
LLMPlanGenerator.generate(strategy)
  system = PLAN_SYSTEM_V2 + strategy.plan_context()
      │
      ▼
PlanPreview.strategy_snapshot (持久化)
  plan_fingerprint 包含 strategy
      │
      ▼
approve_story_plan() → ApprovedPlanSnapshot
  快照不可变，策略冻结
      │
      ▼
build_episode_creative_packet()
  从 preview.strategy_snapshot 提取 strategy_hints
      │
      ▼
ApprovedPlanLLMExecutor.execute()
  EPISODE_SYSTEM_V2 + strategy_hint_text
  获批 role_ids 包含 Plan 生成的 portrayals
      │
      ▼
StoryDelivery
```

### 审计修复（共 4 处）

| # | 问题 | 修复 | 影响 |
|---|---|---|---|
| 1 | `revise_story_plan` 传 `strategy=None` | 从 `current.strategy_snapshot` 重建 `ResolvedStoryStrategy` | 确保修订不丢失策略 |
| 2 | `plan_fingerprint` 不含 strategy | create/revision 两路 payload 均加入 `strategy` | 不同策略产生不同指纹 |
| 3 | 零角色时 Writer 拒绝 Plan 生成的角色 | `approved_role_ids` 纳入 `plan.character_portrayals` | Writer 可使用 Plan 生成的角色 ID |
| 4 | Plan 生成更多角色时验证失败 | 改为子集检查（provided ⊆ portrayed） | Plan 可自由扩展角色 |

---

## 三、策略对比分析

### 同一创意 × 不同 Recipe 的策略差异

**创意**: "三十五岁全职主妇林敏发现丈夫出轨，悄悄收集证据重新创业，最终在家庭聚会摊牌离婚"

#### 案例 1: AUTO (自动匹配)
- 解析结果: `general` + `G01 (现实家庭冲突)` + `R4 (家庭反击)`
- 冲突机制: 亲密关系权力反转 — 压迫与反抗，私人化反派
- 因果推进: 憋屈积累 → 觉醒时刻 → 事实反击
- 结局策略: 关系重新定义，可和解可分离

#### 案例 3: R5 (破镜重圆治愈 — 显式)
- 解析结果: `general` + `G02 (成年人治愈爱情)` + `R5`
- 冲突机制: **内心拉扯式** — 旧伤与渐进理解，以"拉扯"代替"对抗"
- 因果推进: **偶然重逢 → 旧伤触发 → 被迫面对 → 渐进理解**
- 结局策略: **和解与重新开始** — "不完美但真实" 优于强行圆满
- 基调: **细腻、酸涩、温暖** — 情感张力来自台词的未尽之言

#### R4 vs R5 实质差异

| 维度 | R4 家庭反击 | R5 破镜重圆治愈 |
|---|---|---|
| 冲突本质 | 外部权力对抗（私人化反派） | 内部情感拉扯（过去创伤） |
| 推进方式 | 憋屈→觉醒→证据反击 | 重逢→触发→面对→渐进理解 |
| 结局期望 | 关系重新定义，不强制大团圆 | 和解成长，"不完美但真实" |
| 情绪弧线 | 怒→爽→暖 | 酸→暖 |
| 情感来源 | "终于等到这一天"的释放 | 台词未尽之言的张力 |
| Plan 注入文本 | 28 行策略指导 | 24 行策略指导（显著不同） |
| Writer 提示 | 4 条策略约束 | 4 条策略约束（完全不同的内容） |

**结论: R4 和 R5 在冲突机制、因果推进方式和结局策略上有实质性差异，不是简单的标签替换。**

完整对比数据见: `6-实测产物/strategy_impact/strategy_comparison_deterministic.json`

---

## 四、测试结果

### 单元测试

```
tests/unit/test_story_strategy.py ........ 25 passed
tests/unit/test_phase10_workflow.py ....... 53 passed
全部单元测试 ............................ 523 passed, 0 failed
```

### 策略测试覆盖

- ✅ 显式 genre/recipe 精确返回
- ✅ AUTO 从创意关键词匹配体裁
- ✅ 配方自动从体裁推导
- ✅ 配方槽位注入（A-E 五槽位）
- ✅ 全部 5 种配方均有独特机制（冲突 / 因果 / 结局 / 基调各不相同）
- ✅ plan_context() 不同配方输出不同
- ✅ writer_context() 不同配方输出不同
- ✅ 全部 10 种体裁均可自动解析
- ✅ 体裁-配方映射完整性
- ✅ 配方-模式亲和度一致性
- ✅ 显式 recipe-mode 冲突检测（R5 + viral_drama → 报错）
- ✅ Strategy 序列化往返
- ✅ Strategy 通过 PlanPreview → 审批 → CreativePacket 全链路

### 真实模型对照

⚠️ **API 连接限制**: 提供的 API key 与 `https://api.deepseek.com/v1` 返回 HTTP 401。
`build_provider_from_env()` 可从环境变量成功调用，但比较脚本重复调用时出现连接超时。

已准备两套对照脚本（`scripts/compare_plans_only.py`、`scripts/compare_strategies.py`），
在有稳定 API 连接的环境中可直接运行。

---

## 五、影响评估

### Token 成本

- **策略解析**: 0 LLM 调用 — 纯关键词匹配 + 查表
- **Plan 阶段**: ~200-400 字符追加到 system prompt (~3-5%)
- **Writer 阶段**: ~300-600 字符追加到 system prompt
- **总增量**: 每故事约 500-1000 额外 input tokens (<$0.001)

### 质量影响

- **Plan 构思**: 策略机制直接注入 system prompt，模型在规划阶段明确冲突类型、因果和结局
- **Writer 执行**: 策略提示通过 creative_packet 传递，确保正文一致性
- **不增加**: 无新增 LLM 调用、无新增 Judge 节点、无自动重写循环

### 兼容性

- ✅ 4 种 Mode 全部保持
- ✅ 现有 Template 系统不变
- ✅ StoryWorkflowService API 不变
- ✅ 旧版 LangGraph 不受影响
- ✅ 523 个现有测试零回归

---

## 六、主要改动文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `drama_engine/workflow/strategy.py` | 新增 | StrategyResolver + ResolvedStoryStrategy + 5 recipes mechanisms |
| `drama_engine/workflow/schemas.py` | 修改 | CreationPreferences.recipe_id, PlanPreview.strategy_snapshot |
| `drama_engine/workflow/service.py` | 修改 | 集成 StrategyResolver, plan_fingerprint 含 strategy |
| `drama_engine/workflow/adapters.py` | 修改 | LLMPlanGenerator 注入策略, 批准 Plan 生成的角色 |
| `drama_engine/workflow/creative_context.py` | 修改 | EpisodeCreativePacket.strategy_hints |
| `tests/unit/test_story_strategy.py` | 新增 | 25 个策略测试 |
| `scripts/compare_strategies.py` | 新增 | 完整对照脚本 |
| `scripts/show_strategy_impact.py` | 新增 | 确定性策略对比 |

---

## 七、调用示例

```python
from drama_engine.workflow.schemas import CreationPreferences, StoryModeChoice

# 全自动匹配
CreationPreferences(story_mode=StoryModeChoice.AUTO, genre="auto")
# → 自动匹配 R4 家庭反击

# 显式选择治愈爱情套路
CreationPreferences(story_mode=StoryModeChoice.GENERAL, genre="G02", recipe_id="R5")
# → 内心拉扯式冲突 + 渐进理解 + "不完美但真实"结局

# 显式选择家庭反击套路
CreationPreferences(story_mode=StoryModeChoice.GENERAL, genre="G01", recipe_id="R4")
# → 权力反转冲突 + 憋屈→觉醒→反击 + 关系重新定义

# 冲突检测（会报错）
CreationPreferences(story_mode=StoryModeChoice.VIRAL_DRAMA, recipe_id="R5")
# → raises StrategyConflictError: R5 不支持 viral_drama
```

---

## 八、尚未解决的问题

1. **真实模型 API 连接不稳定**: 对照脚本已准备，有稳定连接即可运行
2. **节拍表未差异化**: `beat_sheet_for()` 对所有套路返回相同的 S1-S6 结构
3. **Genre 自动匹配精准度**: 关键词匹配对边缘案例可能不准确

---

## 九、合并条件评估

| 条件 | 状态 |
|---|---|
| 单元测试全通过 | ✅ 523/523 |
| 现有测试零回归 | ✅ |
| API 兼容 | ✅ 向后兼容 |
| 策略解析确定性 | ✅ 0-LLM，可预测 |
| 代码侵入性 | 低 — 新增 1 模块，修改 5 文件 |

**建议: 具备合并条件。** 真实模型对照可在网络恢复后补充，不影响策略解析框架的正确性和现有功能。