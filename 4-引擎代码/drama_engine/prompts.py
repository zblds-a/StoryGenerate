"""提示词组装层。

核心决策：**提示词不是硬编码的文案，而是从规则库动态组装的。**

理由：规则库会迭代（K01–K18 已经从 15 条涨到 18 条，v1.0 → v1.2）。
如果把规则抄进提示词里，每次改规则都要人肉同步两处，迟早漂移。
这里所有约束文本都从 RuleLibrary 取值，规则库一变，提示词自动跟着变。

同时，提示词的 hash 会进入缓存指纹（见 config.cache_fingerprint），
保证"规则更新 → 旧缓存失效"，不会出现改了规则却拿到旧结果的隐蔽 bug。
"""
from __future__ import annotations

import json

from .config import RuleLibrary


def _bullets(items, fmt=lambda x: str(x)) -> str:
    return "\n".join(f"- {fmt(x)}" for x in items)


# ------------------------------------------------------------------ 立项：选题
def topic_select(lib: RuleLibrary, idea: str) -> tuple[str, str]:
    system = (
        "你是一名广播剧制片人，专长是把竖屏短剧的题材判断迁移到纯音频形态。\n"
        "你的判断标准只有一条：**该题材的戏剧张力是否天然存在于台词里**。\n"
        "任何依赖打斗画面、妖物特效、颜值特写的题材，音频化后都会断崖式下跌。"
    )
    genres = "\n".join(
        f"- {g['genre_id']} {g['name']}｜音频适配 {g['audio_fit_score']}/100｜机制：{g['mechanism']}"
        f"｜情绪：{g['emotion']}"
        for g in lib.genres
    )
    recipes = "\n".join(f"- {r['id']} {r['name']}｜适配：{r['audio_fit']}" for r in lib.recipes)
    allowed = ", ".join(g["genre_id"] for g in lib.audio_ready_genres)
    user = (
        f"创意：{idea}\n\n"
        f"【可选赛道】\n{genres}\n\n"
        f"【必须避开】音频适配低于 70 的赛道一律不选。允许的 genre_id：{allowed}\n\n"
        f"【可选配方】\n{recipes}\n\n"
        "请选出赛道与配方，并说明为什么这个赛道适配音频形态。"
    )
    return system, user


# ------------------------------------------------------------------ 立项：金手指
def gadget_design(lib: RuleLibrary, idea: str, genre_id: str, locked_assets: list[str],
                  prior_findings: list[dict] | None = None) -> tuple[str, str]:
    layers = "\n".join(
        f"- {v['id']} {v['name']}：赋予主角「{v['grants']}」，结构后果是「{v['structural_result']}」"
        for v in lib.value_layers.values()
    )
    curves = "\n".join(
        f"- {c['id']} {c['name']}：感知方式={c['realization']}，曲线={c['curve']}，"
        f"正确用法={c['correct_usage']}"
        for c in lib.tension_curves.values()
    )
    k_rules = _bullets(
        [f"{r['id']} {r['title']} —— {r['details']}"
         for r in lib.k_rules.values()
         if r["category"] in ("金手指", "冲突层级")],
        str,
    )
    division = lib.timetravel.get("layer_division_law", {})
    system = (
        "你是一名剧集结构设计师。你设计的不是『设定』，而是**能持续供给张力的结构**。\n"
        "你的核心判断：无限的东西本身没有张力，张力来自它被什么限制。"
    )
    user = (
        f"创意：{idea}\n赛道：{genre_id}\n"
        f"用户指定必须包含的金手指：{locked_assets or '（未指定，由你决定）'}\n\n"
        f"【价值层级】\n{layers}\n\n"
        f"【张力曲线】\n{curves}\n\n"
        f"【层级分工定律】{division.get('statement', '')}\n"
        f"{division.get('rationale', '')}\n\n"
        f"【必须遵守的规则】\n{k_rules}\n\n"
        + _feedback(prior_findings)
    )
    return system, user


# ------------------------------------------------------------------ 立项：角色
def cast_design(lib: RuleLibrary, idea: str, recipe_id: str,
                gadget: dict, prior_findings: list[dict] | None = None) -> tuple[str, str]:
    recipe = lib.recipe(recipe_id) or {}
    slots = lib.formula.get("character_slots", [])
    slot_text = "\n".join(
        f"- {s['id']} {s['name']}：{s['function']}。必备：{'、'.join(s['required_attributes'])}"
        f"｜音频注意：{s['audio_note']}"
        for s in slots
    )
    fields = lib.formula.get("character_card_fields", [])
    field_text = "\n".join(
        f"- {f['key']}（{f.get('type', 'string')}{'，必填' if f.get('required') else ''}）"
        f"：{f.get('description', '')}"
        for f in fields
    )
    system = (
        f"你是一名广播剧选角导演。你的硬约束：**有声角色不超过 {lib.max_voiced_characters} 个**。\n"
        "听众没有画面，认人只能靠声音。角色的数量必须让位于声音的辨识度。"
    )
    user = (
        f"创意：{idea}\n配方：{recipe_id} {recipe.get('name', '')}\n"
        f"配方槽位建议：A={recipe.get('A')}；B={recipe.get('B')}；C={recipe.get('C')}；"
        f"D={recipe.get('D')}；E={recipe.get('E')}\n"
        f"音频落地提醒：{recipe.get('landing_note', '')}\n\n"
        f"【五槽位模型】\n{slot_text}\n\n"
        f"【角色卡字段】\n{field_text}\n\n"
        f"【金手指设定】\n{json.dumps(gadget, ensure_ascii=False, indent=2)}\n\n"
        "要求：\n"
        f"1. 恰好 5 张卡，槽位 A–E 各一张。\n"
        f"2. 有声角色不超过 {lib.max_voiced_characters} 个；C 槽位的护短群体若超过 2 人，"
        "必须合并为同一音色家族或降级为背景声。\n"
        "3. D 槽位反派必须 private —— 是家人、亲戚、同僚、身边人，且与主角同阵营。\n"
        "4. 每个有声角色的 voice_anchor 必须是**听觉特征**（口癖、语速、气声、停顿），"
        "不能是外貌或表情。\n\n"
        + _feedback(prior_findings)
    )
    return system, user


# ------------------------------------------------------------------ 立项：人物行为卡
def behavior_design(lib: RuleLibrary, idea: str, gadget: dict, cast: list[dict],
                    prior_findings: list[dict] | None = None) -> tuple[str, str]:
    """行为卡提示词。

    组装原则与其它提示词一致：所有约束文本从规则库取，不抄进提示词。
    但这里多做了一件事：**把"性格"这个形容词从提示词里排除掉**。
    提示词只索要"压力 × 选择 + 代价"，因为那是可生成、可检查的形态；
    一句"温柔但坚韧"既生成不出东西，也无从校验。
    """
    pressures = "\n".join(
        f"- {p['id']} {p['name']}：{p['description']}（{p['default_choice_pressure']}）"
        for p in lib.pressure_types.values()
    )
    axes = "\n".join(
        f"- {a['id']} {a['name']}（{'慢变量' if a.get('slow_variable') else '快变量'}）："
        f"{a['description']}｜常见失败：{a['failure_mode']}"
        for a in lib.relationship_axes.values()
    )
    fields = _bullets([f"{f['key']}：{f['description']}"
                       for f in lib.choice_field_spec], str)
    choice_fields = _bullets([f"{f['key']}：{f['description']}"
                              for f in lib.choice_rule_field_spec], str)
    rules = _bullets([f"{r['id']} {r['title']} —— {r['details']}"
                      for r in list(lib.choice_rules.values()) + list(lib.relation_rules.values())],
                     str)
    blacklist = "、".join(lib.choice_cliche_blacklist)

    system = (
        "你是一名人物设计师。你不写人设形容词，你写**选择规律**。\n"
        "你的核心判断：性格 = 在特定压力下愿意放弃什么。\n"
        "一个角色的温柔不体现在台词里说他温柔，而体现在『面对 P2 利益压力时他让利』这个选择上。"
    )
    user = (
        f"创意：{idea}\n\n"
        f"【压力类型（选择的坐标系）】\n{pressures}\n\n"
        f"【关系轴（关系变化的坐标系）】\n{axes}\n\n"
        f"【角色卡（听觉辨识度已定，你要补的是行为）】\n"
        f"{json.dumps(cast, ensure_ascii=False, indent=2)}\n\n"
        f"【金手指】\n{json.dumps(gadget, ensure_ascii=False, indent=2)}\n\n"
        f"【行为卡字段】\n{fields}\n\n"
        f"【选择规律字段】\n{choice_fields}\n\n"
        f"【必须遵守的规则】\n{rules}\n\n"
        "要求：\n"
        "1. 为每一个有声角色产出一张行为卡（数量与角色卡的有声角色一致）。\n"
        "2. 每张卡至少 3 条选择规律，覆盖至少 2 种不同压力类型。\n"
        "3. 每条选择规律必须写明具体代价（他在这个选择里失去了什么），"
        f"严禁使用这些套话：{blacklist}。\n"
        "4. 全剧至少 2 条选择标注 against_self_interest=true，其中载体角色（A 槽位）至少 1 条。"
        "这条是人物魅力的硬判据：观众不会喜欢一个永远做最优解的人。\n"
        "5. 关系边必须覆盖载体角色与其余每一个有声角色；每条边至少 1 个转折点，"
        "且转折点必须绑定具体事件（不能写『相处久了就信任了』）。\n"
        "6. 慢变量关系轴（trust / kinship / debt）若发生方向反转，必须拆成至少 2 个转折点："
        "先动摇，再倒向。\n"
        "7. evidence_hint 要写清这个转折在正文里应该长什么样（台词或音效），供后续证据评审比对。\n\n"
        + _feedback(prior_findings)
    )
    return system, user


# ------------------------------------------------------------------ 立项：事实账本
def fact_ledger(lib: RuleLibrary, idea: str, gadget: dict, cast: list[dict],
                outline: list[dict], bible: dict | None = None,
                prior_findings: list[dict] | None = None) -> tuple[str, str]:
    """事实账本提示词。

    账本要解决的四个问题全在规则里：倒计时（数字不能前后矛盾）、
    资源（无限与快用完不能并存）、认知（谁说不出他不知道的事）、
    承接（每集至少接住一笔旧账）。
    """
    kinds = "\n".join(
        f"- {k}：{v}" for k, v in {
            "countdown": "倒计时。必须给出 due_at（到期集），且到期集要自己负责兑现",
            "resource": "资源余量。必须与金手指的 capacity 声明一致（无限则不得记载告罄）",
            "knowledge": "认知。写清 holders（谁知道）与 forbidden_holders（谁禁知），两者不得重叠",
            "promise": "承诺与欠负。说过的话、欠过的情，必须有还的时候",
            "possession": "物件归属。某样东西此刻在谁手上",
            "position": "身份与处境。官职、伤病、是否被囚",
        }.items()
    )
    rules = _bullets([f"{r['id']} {r['title']} —— {r['details']}"
                      for r in lib.fact_rules.values()], str)
    caps = "\n".join(
        f"- {a['name']}：capacity={a['capacity']}，curve={a['curve']}"
        + (f"，衰减安排：{a['decay_plan']}" if a.get("decay_plan") else "")
        for a in gadget.get("assets", [])
    )
    names = [c.get("name") for c in cast if c.get("is_voiced") and not c.get("merged_into")]
    act3 = [e.get("episode") for e in outline if e.get("act", 0) >= 3]

    system = (
        "你是一名场记（continuity supervisor）。你的职责只有一件事："
        "**让第 30 集不会和第 2 集打架。**\n"
        "你不写剧情，你写账目：什么数字、什么余量、谁知道、什么时候必须兑现。"
    )
    user = (
        f"创意：{idea}\n\n"
        f"【账目类型】\n{kinds}\n\n"
        f"【必须遵守的规则】\n{rules}\n\n"
        f"【金手指容量声明】\n{caps}\n\n"
        f"【有声角色名单（认知账目只能引用这些名字）】\n{names}\n\n"
        f"【行为卡（错误信念常对应认知盲区，可用于设计 forbidden_holders）】\n"
        f"{json.dumps(bible or {}, ensure_ascii=False, indent=2)[:2400]}\n\n"
        f"【分集大纲】\n{json.dumps(outline, ensure_ascii=False, indent=2)}\n\n"
        "要求：\n"
        f"1. 条目数不少于 max(3, 总集数/2)；第三幕（act>=3）的每一集 {act3} 都至少被一笔账覆盖。\n"
        "2. 倒计时条目必须给出 due_at，且 due_at 必须出现在该条目的 expected_mentions 里"
        "（到期这件事必须自己负责兑现）。\n"
        "3. 资源条目不得与 capacity 声明矛盾：无限容量的资产不得出现『用完/见底』；"
        "有限或会耗尽的资产必须有余量账目。\n"
        "4. 认知条目的 holders 与 forbidden_holders 不得有交集。\n"
        "5. expected_mentions 里的集号必须真实存在（1 到总集数之间）。\n"
        "6. statement 用一句可核对的话写，例如『第 3 集用掉两支，剩九支』，"
        "不要写『资源逐渐紧张』这类无法核对的话。\n\n"
        + _feedback(prior_findings)
    )
    return system, user


# ------------------------------------------------------------------ 立项：大纲
def outline(lib: RuleLibrary, idea: str, genre_id: str, gadget: dict, cast: list[dict],
            total_episodes: int, prior_findings: list[dict] | None = None,
            bible: dict | None = None) -> tuple[str, str]:
    acts = "\n".join(
        f"- 第 {a['act']} 幕 {a['name']}：占比 {a['ratio'][0]:.0%}–{a['ratio'][1]:.0%}，"
        f"职能：{a['function']}；硬要求：{a['hard_requirement']}"
        for a in lib.four_act_structure
    )
    loop = lib.timetravel.get("core_engine_loop", {})
    loop_text = "\n".join(f"  {s['step']}. {s['name']}" for s in loop.get("steps", []))
    side_effects = _bullets(
        [f"上一次成功：{e['prev_success']} → 正确的副作用：{e['correct_side_effect']}"
         for e in loop.get("step5_examples", [])],
        str,
    )
    arcs = _bullets([f"{a['id']} {a['range']}：{a['task']}（硬规则：{a['hard_rule']}）"
                     for a in lib.series_arc_rules], str)
    k_rules = _bullets(
        [f"{r['id']} {r['title']} —— {r['details']}"
         for r in lib.k_rules.values() if r["category"] == "结构"],
        str,
    )
    sensory = [a["name"] for a in gadget.get("assets", []) if a.get("curve") == "TC2"]

    # 人物层：大纲必须把行为卡里的选择安排到具体集数上，否则行为卡只是设定文档
    choice_menu = _choice_menu(bible)
    choice_block = (
        "【可供安排的角色选择（每位角色每集最多一条）】\n" + choice_menu
        if choice_menu else ""
    )
    turn_block = _turning_point_menu(bible)

    system = (
        "你是一名剧集结构规划师。你产出的是**结构表**，不是故事梗概。\n"
        "最重要的纪律：每一集的核心难题必须能追溯到前面某一次成功的副作用。"
        "写不出这个追溯关系的集，就是注水集。\n"
        "第二条纪律：每一集只安排一个核心目标、至多一次角色选择、至多一次关系转折。"
        "结构表的价值在于可核对，而不在于内容丰富。"
    )
    user = (
        f"创意：{idea}\n赛道：{genre_id}\n总集数：{total_episodes}\n\n"
        f"【四幕结构】\n{acts}\n\n"
        f"【降维循环公式（本剧的引擎）】\n{loop_text}\n"
        f"第 5 步是全部关键。参考写法：\n{side_effects}\n\n"
        f"【长剧弧线规则】\n{arcs}\n\n"
        f"【结构规则】\n{k_rules}\n\n"
        f"【金手指】\n{json.dumps(gadget, ensure_ascii=False, indent=2)}\n\n"
        f"【角色】\n{json.dumps(cast, ensure_ascii=False, indent=2)}\n\n"
        f"【感官型资产】{sensory or '（无）'} —— 若存在，"
        "deployment 字段只在它实际出场的集数填写，且每次必须引入新变量（K18）。\n\n"
        f"{choice_block}\n\n{turn_block}\n\n"
        "要求：\n"
        f"1. 输出 {total_episodes} 条 entry，episode 从 1 升序。\n"
        "2. 凡 act=3 且 episode 大于落地段最后一集的，side_effect_of 必填，"
        "且指向更早的集数。\n"
        "3. gadget_failed 至少安排 1 集（每 5 次循环 1 次金手指失效）。\n"
        "4. polarity 为 negative 的集数不得连续超过 2 集。\n"
        "5. conflict_intensity 为 1–10 的整数，全剧峰值应落在最后 30%。\n"
        "6. exercised_choice 必须从上面的菜单中选择一条，格式「角色名@压力类型：选择内容」；"
        "不要每集都填，只在真正演练的那几集填。**至少有一集要分配到标注 ★ 的选择。**\n"
        "7. relation_turn 只在关系真的发生变化的那一集填，格式「甲→乙@轴」。\n\n"
        + _feedback(prior_findings)
    )
    return system, user


def _choice_menu(bible: dict | None) -> str:
    """把行为卡的选择规律摊成菜单，供大纲分配。

    这一步是"人物有魅力"进剧情的关键接口：行为卡在立项段生成，
    但只有被安排到具体集数上，它才从设定变成剧情。
    """
    if not bible:
        return ""
    lines: list[str] = []
    for card in bible.get("cards", []):
        for ch in card.get("choices", []):
            star = " ★违背自身利益" if ch.get("against_self_interest") else ""
            lines.append(f"- {card['name']}@{ch['pressure']}：{ch['trigger']} → {ch['choice']}｜"
                         f"代价：{ch['cost']}{star}")
    return "\n".join(lines)


def _turning_point_menu(bible: dict | None) -> str:
    if not bible:
        return ""
    lines: list[str] = []
    for rel in bible.get("relations", []):
        for t in rel.get("turning_points", []):
            lines.append(f"- 第 {t['episode']} 集：{rel['a']}→{rel['b']}@{rel['axis']}｜"
                         f"事件：{t['event']}")
    return ("【行为卡预设的关系转折（集号须与大纲一致）】\n" + "\n".join(lines)) if lines else ""


# ------------------------------------------------------------------ 逐集：节拍
def episode_beats(lib: RuleLibrary, entry: dict, cast: list[dict], gadget: dict,
                  duration_sec: int, prior_findings: list[dict] | None = None,
                  continuity_text: str = "") -> tuple[str, str]:
    sheet = lib.beat_sheet_for(duration_sec)
    beat_text = "\n".join(
        f"- {s['id']} {s['label']}｜{s['range'][0]}–{s['range'][1]} 秒｜规则：{s['rule']}"
        + (f"｜音频要求：{s.get('audio_requirement', '')}" if s.get("audio_requirement") else "")
        for s in sheet
    )
    subs = lib.formula.get("audio_visual_substitutes", {})
    cat_text = "\n".join(
        f"- {c['id']} {c['name']}：{'、'.join(c['items'])}" for c in subs.get("categories", [])
    )
    hooks = _bullets([f"{h['id']} {h['name']}（{h['emotion']}）音频改造：{h['audio_rewrite']}"
                      for h in lib.hook_types], str)
    principles = _bullets(lib.formula.get("audio_drama_constraints", {}).get("principles", []), str)

    system = (
        "你是一名广播剧编剧。你唯一的表达工具是：**人声、音效、音乐、静音**。\n"
        "画面不存在。任何你写下的『动作』都必须能变成声音。\n"
        "你这一集还背着一份额外的账：本集的连续性切片里写着必须承接与必须兑现的东西。"
        "**账目优先于灵感** —— 数字、余量、谁知道，一律以账目为准。"
    )
    user = (
        f"【本集任务】\n{json.dumps(entry, ensure_ascii=False, indent=2)}\n\n"
        f"【本集时长】{duration_sec} 秒\n\n"
        f"【连续性与人物切片（硬约束）】\n{continuity_text or '（本集无）'}\n\n"
        f"【节拍表（时间轴硬约束，不得改动边界）】\n{beat_text}\n\n"
        f"【四类听觉事件（视觉描写的唯一替代）】\n{cat_text}\n\n"
        f"【禁用词】以下词汇一律不得出现：{lib.visual_blacklist}\n\n"
        f"【钩子库】\n{hooks}\n\n"
        f"【广播剧写作原则】\n{principles}\n\n"
        f"【角色】\n{json.dumps(cast, ensure_ascii=False, indent=2)}\n\n"
        f"【金手指】\n{json.dumps(gadget, ensure_ascii=False, indent=2)}\n\n"
        "要求：\n"
        "1. S1 的第一条声音必须是 sfx 且 sfx_category=AV1（突发型）。S1 内不得出现旁白交代背景。\n"
        "2. S2 至少 4 句台词、至少 2 个说话人，让听众听出『谁/在哪/什么麻烦/想做什么』。\n"
        "3. S3 内必须有一条 event=release、emotion_peak>=7 的台词。\n"
        "4. 每 20–30 秒必须有一个 event 非空的节点（hook/beat/release/reversal/cliffhanger）。\n"
        "5. S6 的情绪峰值必须大于本集其余所有节拍；cliffhanger_hook_type 取六类钩子之一。\n"
        "6. threads 恰好 1 条。\n"
        "7. 每条台词不超过 20 字。\n"
        "8. 时长超过 15 秒的节拍必须同时含 AV4 环境音与 AV1 动作音。\n"
        "9. 本集任务里声明过的每一项（副作用来源、可量化成果、定点投放、金手指失效、"
        "角色选择、关系转折）**都必须在本集正文里被听见**。"
        "填了声明却在正文里找不到载体，就会被判为『标签空转』并打回重写。\n\n"
        + _feedback(prior_findings)
    )
    return system, user


# ------------------------------------------------------------------ 反馈注入
def _feedback(prior_findings: list[dict] | None) -> str:
    """把上一轮的违规回灌进提示词。

    这是修复回路的质量关键：不能只说"重写一遍"，必须告诉模型**具体错在哪一条规则上**。
    模型对"你违反了 K17，两项资产都落在 L1"的响应，远好于"这不太行，再写一版"。
    """
    if not prior_findings:
        return ""
    lines = []
    for f in prior_findings[:12]:
        rule = f.get("rule_id", "")
        msg = f.get("message", "")
        hint = f.get("repair_hint") or ""
        loc = f.get("location") or ""
        line = f"- [{rule}]{(' ' + loc) if loc else ''} {msg}"
        # 证据类违规必须把原文片段一并回灌：模型看到"第 S4-4 行『他嘴角微微一勾』"
        # 的响应，远好于看到"存在视觉描写"。
        if f.get("evidence"):
            line += f"\n  证据（正文原文）：{f['evidence']}"
        if hint:
            line += f"\n  修正方向：{hint}"
        lines.append(line)
    return (
        "【上一版未通过的校验项 —— 本版必须逐条修正】\n"
        + "\n".join(lines)
        + "\n\n只修正这些问题，不要改动已经通过的部分。"
    )


def repair_instruction(route: str, findings: list[dict]) -> str:
    """按修复节点给出针对性的指令。"""
    rules = sorted({f["rule_id"] for f in findings})
    base = f"本轮修复节点：{route}。需要修正的规则：{', '.join(rules)}。"
    if route == "repair_cast":
        return base + " 优先用『合并到已有角色』解决，而不是新增角色 —— 新增会立刻再次触发角色上限。"
    if route == "repair_audio":
        return base + " 只做听觉化改写与台词拆分，不得改动节拍边界与事件标记。"
    if route == "repair_beat":
        return base + " 只重写被点名的节拍段落，其余节拍原样保留。"
    if route == "repair_gadget":
        return base + " 这是立项层缺陷，必须回到金手指设定上修，不能靠改写台词糊过去。"
    if route == "repair_outline":
        return base + " 这是结构层缺陷，修正后所有下游剧集都会受影响。"
    if route == "repair_behavior":
        return base + " 这是人物层缺陷：改的是选择规律本身，不是台词。" \
                      " 缺的是『在某个压力下他会放弃什么』这条规律，补规律而不是补形容词。"
    if route == "repair_ledger":
        return base + " 这是账目层缺陷：改的是账本，不是台词。" \
                      " 数字、余量、认知边界必须记账；靠改台词掩盖账目矛盾只会让矛盾后移。"
    return base
