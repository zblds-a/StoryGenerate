"""Story Strategy Resolver — deterministic, 0-LLM.

Unifies Story Mode + Genre + Recipe + Template into a single
ResolvedStoryStrategy that the Plan and Writer stages can consume.

Design principles:
- Deterministic: no LLM call, purely rule-based matching.
- Explicit-first: user-specified values always win; auto-match only fills gaps.
- Conflict-aware: incompatible combinations produce clear errors, not silent overwrites.
- Lightweight: reuses existing RuleLibrary, TemplateResolver, and ModeRegistry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from ..config import RuleLibrary
from ..core.errors import EngineErrorCode, StoryEngineError


class StrategyConflictError(StoryEngineError):
    """Raised when the user's explicit choices are incompatible."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code=EngineErrorCode.MODE_NOT_SUPPORTED,
            message=message,
        )


# ---------------------------------------------------------------------------
# Resolved Story Strategy
# ---------------------------------------------------------------------------

class ResolvedStoryStrategy(BaseModel):
    """The frozen strategy snapshot that enters Plan and Writer stages.

    Every field that was auto-filled is recorded so the system can report
    what was inferred vs. what the user specified.
    """

    story_mode: str = Field(description="Final resolved story mode key")
    mode_label: str = Field(default="", description="Human-readable mode name")

    genre_id: str = Field(description="Genre from formula library, e.g. G01")
    genre_name: str = Field(default="", description="Human-readable genre name")
    genre_mechanism: str = Field(default="", description="Core conflict/emotional mechanism")
    genre_emotion: str = Field(default="", description="Emotional arc, e.g. '怒→爽→暖'")

    recipe_id: str = Field(default="", description="Recipe id, e.g. R1")
    recipe_name: str = Field(default="", description="Human-readable recipe name")
    recipe_slots: dict[str, str] = Field(
        default_factory=dict,
        description="Slot assignments A→E from the recipe",
    )
    recipe_landing_note: str = Field(
        default="",
        description="Audio-adaptation guidance from the recipe",
    )

    template_ref: str = Field(default="", description="Resolved template id")
    template_version: int = Field(default=1, description="Template version")

    # Which fields were explicitly specified by the user
    explicit_fields: list[str] = Field(default_factory=list)
    auto_filled_fields: list[str] = Field(default_factory=list)

    # Derived writing guidance — not raw rule dumps
    conflict_mechanism: str = Field(
        default="",
        description="How conflict escalates in this strategy",
    )
    causal_driver: str = Field(
        default="",
        description="What drives causal progression: character choices, clue discovery, etc.",
    )
    ending_strategy: str = Field(
        default="",
        description="How the story should end: closed, open, cliffhanger, etc.",
    )
    tone_guidance: str = Field(
        default="",
        description="Tone hints for the writer",
    )

    # The raw snapshot of the underlying data for debugging
    genre_data: dict[str, Any] = Field(default_factory=dict)
    recipe_data: dict[str, Any] = Field(default_factory=dict)

    def plan_context(self) -> str:
        """Compact context for injection into the Plan system prompt."""
        parts = [
            f"故事模式：{self.mode_label}（{self.story_mode}）",
            f"题材赛道：{self.genre_name}（{self.genre_id}）",
            f"题材机制：{self.genre_mechanism}",
            f"情绪弧线：{self.genre_emotion}",
        ]
        if self.recipe_id:
            parts.extend([
                f"角色配方：{self.recipe_name}（{self.recipe_id}）",
                f"配方落地提醒：{self.recipe_landing_note}",
            ])
        if self.conflict_mechanism:
            parts.append(f"核心冲突机制：{self.conflict_mechanism}")
        if self.causal_driver:
            parts.append(f"因果推进方式：{self.causal_driver}")
        if self.ending_strategy:
            parts.append(f"结局策略：{self.ending_strategy}")
        if self.tone_guidance:
            parts.append(f"基调指导：{self.tone_guidance}")
        return "\n".join(parts)

    def writer_context(self) -> list[str]:
        """Compact strategy hints for the Writer creative packet."""
        hints = []
        if self.conflict_mechanism:
            hints.append(f"冲突机制：{self.conflict_mechanism}")
        if self.causal_driver:
            hints.append(f"因果驱动：{self.causal_driver}")
        if self.ending_strategy:
            hints.append(f"结局策略：{self.ending_strategy}")
        if self.tone_guidance:
            hints.append(f"基调：{self.tone_guidance}")
        return hints


# ---------------------------------------------------------------------------
# Recipe → Mode compatibility table
# ---------------------------------------------------------------------------
# Each recipe has a natural story-mode affinity.  Mismatches produce warnings
# but only *explicit* conflicts raise errors.
_RECIPE_MODE_AFFINITY: dict[str, set[str]] = {
    "R1": {"viral_drama", "serialized"},       # 大女主升级流
    "R2": {"viral_drama", "serialized"},       # 萌宝团宠
    "R3": {"viral_drama", "general"},           # 反差搞事业
    "R4": {"general", "viral_drama"},           # 家庭反击
    "R5": {"general"},                          # 破镜重圆治愈
}

# Recipe → default mode when user doesn't specify
_RECIPE_DEFAULT_MODE: dict[str, str] = {
    "R1": "viral_drama",
    "R2": "viral_drama",
    "R3": "viral_drama",
    "R4": "general",
    "R5": "general",
}

# Genre → default recipe
_GENRE_DEFAULT_RECIPE: dict[str, str] = {
    "G01": "R4",  # 现实家庭冲突 → 家庭反击
    "G02": "R5",  # 成年人治愈爱情 → 破镜重圆治愈
    "G03": "R5",  # 重生虐恋 → 破镜重圆治愈
    "G04": "R1",  # 宫斗复仇 → 大女主升级流
    "G05": "R5",  # 现实治愈/救赎 → 破镜重圆治愈
    "G06": "R4",  # 反差霸总×草根女 → 家庭反击 (closest match)
    "G07": "R2",  # 萌宝团宠 → 萌宝团宠
    "G08": "R3",  # 脑洞穿越搞事业 → 反差搞事业
    "G09": "R1",  # 反差修仙喜剧 → 大女主升级流
    "G10": "R1",  # 国风玄幻升级流 → 大女主升级流
}

# Genre → default mode
_GENRE_DEFAULT_MODE: dict[str, str] = {
    "G01": "general",
    "G02": "general",
    "G03": "general",
    "G04": "viral_drama",
    "G05": "general",
    "G06": "viral_drama",
    "G07": "viral_drama",
    "G08": "viral_drama",
    "G09": "viral_drama",
    "G10": "viral_drama",
}


# ---------------------------------------------------------------------------
# Recipe-specific story mechanisms
# ---------------------------------------------------------------------------
# Each recipe has a conflict mechanism, causal driver, ending strategy, and
# tone guidance beyond slot assignments — these make the recipe actually
# affect the story instead of just providing labels.
_RECIPE_MECHANISMS: dict[str, dict[str, str]] = {
    "R1": {
        "conflict_mechanism": (
            "升级式冲突：主角能力每提升一层，敌人也随之升级。冲突来自能力边界的不断测试，"
            "而非一次性对决。每一次胜利都带来更大的责任或更强的对手。"
        ),
        "causal_driver": (
            "主角的主动选择驱动：每一次升级都源于主角决定挑战更强的对手或更难的副本。"
            "金手指提供能力，但选择如何使用（或克制不使用）才是剧情推进的核心。"
        ),
        "ending_strategy": (
            "阶段性成就 + 更大世界的暗示。当前冲突解决，但主角的成长远未结束。"
            "结局应展示主角在新层次上的状态，为续集留下自然入口。"
        ),
        "tone_guidance": "热血、成长感、阶段性爽感。避免全程碾压的无聊感。",
    },
    "R2": {
        "conflict_mechanism": (
            "反差式冲突：冲突来自外界对主角的低估与主角真实身份/能力之间的差距。"
            "每一次打脸都是身份揭示，而非暴力对抗。轻量反派，重情绪供给。"
        ),
        "causal_driver": (
            "外界误解 → 主角自然行动 → 真相逐步揭示。主角不需要主动证明自己，"
            "护短群体（师兄团等）的介入是事件触发器。"
        ),
        "ending_strategy": (
            "温馨团聚 + 身份完全揭示。家人/师兄团真正理解主角的价值。"
            "结局是情感层面的圆满，不一定是武力层面的胜利。"
        ),
        "tone_guidance": "温暖、甜、轻度爽感。萌点是核心，不要引入沉重虐点。",
    },
    "R3": {
        "conflict_mechanism": (
            "认知差冲突：主角用现代思维/异世界知识解决古代/异界问题，"
            "冲突来自新旧观念的碰撞，而非武力对抗。喜剧化处理矛盾，避免严肃权谋。"
        ),
        "causal_driver": (
            "信息差变现：主角发现一个被本地人忽视的机会（经济、技术、组织方式），"
            "通过现代知识降维打击。每一次成功都来自知识应用，不是运气或武力。"
        ),
        "ending_strategy": (
            "事业阶段性成功 + 新世界立足。主角证明了自己的价值，获得认可。"
            "结局可以开放（继续搞事业）但不能悲剧收场。"
        ),
        "tone_guidance": "爽快、喜剧、聪明。核心爽点是'他们不懂但我懂'的知识碾压。",
    },
    "R4": {
        "conflict_mechanism": (
            "亲密关系中的权力反转：冲突来自家庭内部的压迫与反抗。"
            "反派必须是私人化的（婆婆、丈夫、小姑），冲突发生在日常场景中。"
            "每一次反击都是界限的重新划定，不是暴力宣泄。"
        ),
        "causal_driver": (
            "憋屈积累 → 觉醒时刻 → 用事实反击。主角的觉醒是因果链的起点，"
            "实证（账目、证据、外部身份）是反击的武器。"
            "冲突升级来自反派的不甘与反扑。"
        ),
        "ending_strategy": (
            "关系重新定义，而非简单的'赢'。结局展示新的家庭平衡状态，"
            "可以和解也可以分离，但主角获得了尊重和自主权。不建议强制大团圆。"
        ),
        "tone_guidance": "真实、情绪浓度高、渐进式爽感。核心是'终于等到这一天'的释放感。",
    },
    "R5": {
        "conflict_mechanism": (
            "内心拉扯式冲突：冲突主要来自人物的内心障碍和过去创伤，外部冲突为辅助。"
            "以'拉扯'代替'对抗'——两个人互相靠近又推开的过程。"
            "旧误会是障碍，但解决方案不是一次性真相大白，而是渐进理解。"
        ),
        "causal_driver": (
            "一次偶然重逢/交集 → 旧伤被触发 → 被迫面对 → 渐进理解。"
            "关系变化来自双方的主动选择，不是命运安排。"
            "金手指（重生记忆）只提供'提前知道'，不改变人物需要做的选择。"
        ),
        "ending_strategy": (
            "和解与重新开始。不一定是复合，但双方都在过程中成长了。"
            "结局展示新的关系状态，可以是'带着伤痕继续前行'。"
            "不建议强行圆满——'不完美但真实'的结局更有力量。"
        ),
        "tone_guidance": "细腻、酸涩、温暖。情感张力来自台词中的未尽之言，不靠激烈冲突。",
    },
}


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

# Characters that carry semantic weight in Chinese genre names
_SIGNIFICANT_CHARS: set[str] = {
    "虐", "宠", "甜", "暖", "爽", "恨", "怒", "酸", "笑",
    "穿", "越", "斗", "战", "修", "反", "萌", "宝",
    "爱", "情", "家", "庭", "治", "愈", "复", "仇",
    "悬", "疑", "推", "理", "宫", "谋", "霸", "总",
}


def _is_significant_char(ch: str) -> bool:
    return ch in _SIGNIFICANT_CHARS


def _chinese_keywords(text: str) -> list[str]:
    """Split Chinese text into meaningful 1-3 character keyword chunks.

    Example: "现实家庭冲突" → ["现实", "家庭", "冲突", "实家", "庭冲"]
    Example: "憋屈积累→反击打脸" → ["憋屈", "积累", "反击", "打脸"]
    """
    # Remove arrows and other delimiters
    cleaned = text.replace("→", " ").replace("·", " ").replace("/", " ").replace("、", " ")
    # Extract all CJK character sequences
    result: list[str] = []
    current: list[str] = []
    for ch in cleaned:
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            current.append(ch)
        else:
            if current:
                result.extend(_sliding_windows("".join(current)))
                current = []
    if current:
        result.extend(_sliding_windows("".join(current)))
    return result


def _sliding_windows(s: str) -> list[str]:
    """Generate 1-3 char sliding windows from a CJK string."""
    n = len(s)
    windows: list[str] = []
    for size in (2, 3):
        if n >= size:
            for i in range(n - size + 1):
                windows.append(s[i:i + size])
    # Also include individual significant chars
    for ch in s:
        if _is_significant_char(ch):
            windows.append(ch)
    return windows


@dataclass
class StoryStrategyResolver:
    """Deterministic resolver that produces a ResolvedStoryStrategy.

    Usage:
        resolver = StoryStrategyResolver(lib)
        strategy = resolver.resolve(
            story_mode="auto",
            genre="auto",
            recipe_id=None,
            template_ref=None,
            user_instruction="一个人在城市重新找到生活方向",
            explicit_fields=["user_instruction"],
        )
    """

    lib: RuleLibrary

    # ---- helpers ----

    def _match_genre_from_idea(self, idea: str) -> str | None:
        """Simple keyword matching against genre matrix names and mechanisms.

        Deliberately NOT an LLM call — this is a fast deterministic match that
        can be overridden by explicit user specification.
        """
        idea_lower = idea.casefold()
        best_score = 0
        best_genre: str | None = None

        for genre in self.lib.genres:
            score = 0
            name = genre.get("name", "").casefold()
            mechanism = genre.get("mechanism", "").casefold()
            emotion = genre.get("emotion", "").casefold()

            # Collect all keywords, deduplicate across sources
            seen_single: set[str] = set()
            seen_multi: set[str] = set()

            # Check name keywords (highest weight — genre name is most specific)
            for kw in _chinese_keywords(name):
                if len(kw) >= 2:
                    if kw not in seen_multi and kw in idea_lower:
                        score += 20
                        seen_multi.add(kw)
                elif len(kw) == 1 and _is_significant_char(kw):
                    if kw not in seen_single and kw in idea_lower:
                        score += 12
                        seen_single.add(kw)

            # Check mechanism keywords (medium weight)
            for kw in _chinese_keywords(mechanism):
                if len(kw) >= 2:
                    if kw not in seen_multi and kw in idea_lower:
                        score += 10
                        seen_multi.add(kw)
                elif len(kw) == 1 and _is_significant_char(kw):
                    if kw not in seen_single and kw in idea_lower:
                        score += 8
                        seen_single.add(kw)

            # Check emotion keywords (lowest weight)
            for kw in _chinese_keywords(emotion):
                if len(kw) >= 2:
                    if kw not in seen_multi and kw in idea_lower:
                        score += 8
                        seen_multi.add(kw)
                elif len(kw) == 1 and _is_significant_char(kw):
                    if kw not in seen_single and kw in idea_lower:
                        score += 5
                        seen_single.add(kw)

            if score > best_score:
                best_score = score
                best_genre = genre.get("genre_id")

        # Only auto-match when we have a meaningful signal
        if best_score < 10:
            return None
        return best_genre

    def _mode_from_genre(self, genre_id: str) -> str:
        return _GENRE_DEFAULT_MODE.get(genre_id, "general")

    def _recipe_from_genre(self, genre_id: str) -> str | None:
        return _GENRE_DEFAULT_RECIPE.get(genre_id)

    # ---- main resolve ----

    def resolve(
        self,
        story_mode: str = "auto",
        genre: str = "auto",
        recipe_id: str | None = None,
        template_ref: str | None = None,
        user_instruction: str = "",
        explicit_fields: list[str] | None = None,
    ) -> ResolvedStoryStrategy:
        """Resolve a complete story strategy.

        Resolution order (explicit wins, auto fills gaps):
        1. story_mode: explicit → genre-derived → "general"
        2. genre: explicit → keyword-match from user_instruction → best audio-fit
        3. recipe: explicit → genre-derived → None
        4. template: explicit → mode-default → ""
        """
        explicit = set(explicit_fields or [])
        auto_filled: list[str] = []

        # --- Step 1: resolve genre ---
        resolved_genre_id: str | None = None
        if genre and genre != "auto":
            resolved_genre_id = genre
        else:
            # Auto-match from user instruction
            matched = self._match_genre_from_idea(user_instruction)
            if matched:
                resolved_genre_id = matched
                auto_filled.append("genre")
            else:
                # Fall back to highest audio-fit genre
                best = max(self.lib.genres, key=lambda g: g.get("audio_fit_score", 0),
                          default=None)
                resolved_genre_id = best.get("genre_id") if best else "G01"
                auto_filled.append("genre")

        genre_data = self.lib.genre(resolved_genre_id) or {}

        # --- Step 2: resolve story_mode ---
        resolved_mode: str
        if story_mode != "auto":
            resolved_mode = story_mode
        else:
            resolved_mode = self._mode_from_genre(resolved_genre_id)
            auto_filled.append("story_mode")

        # --- Step 3: resolve recipe ---
        resolved_recipe_id: str | None = None
        if recipe_id:
            resolved_recipe_id = recipe_id
        else:
            resolved_recipe_id = self._recipe_from_genre(resolved_genre_id)
            if resolved_recipe_id:
                auto_filled.append("recipe_id")

        recipe_data = self.lib.recipe(resolved_recipe_id) if resolved_recipe_id else {}

        # --- Step 4: validate compatibility ---
        if recipe_id and resolved_mode:
            allowed = _RECIPE_MODE_AFFINITY.get(recipe_id, set())
            if allowed and resolved_mode not in allowed:
                # If recipe is explicit but mode is auto-resolved, adjust mode
                if story_mode == "auto":
                    resolved_mode = _RECIPE_DEFAULT_MODE.get(recipe_id, next(iter(allowed), "general"))
                    auto_filled.append("story_mode")
                else:
                    raise StrategyConflictError(
                        f"配方 '{recipe_id}'（{recipe_data.get('name', '')}）与模式 "
                        f"'{resolved_mode}' 不兼容。"
                        f"该配方支持的模式：{', '.join(sorted(allowed))}。"
                    )

        # --- Step 5: derive story mechanisms ---
        mechanisms = _RECIPE_MECHANISMS.get(
            resolved_recipe_id or "",
            {
                "conflict_mechanism": "人物选择驱动的自然冲突",
                "causal_driver": "人物目标 → 行动 → 阻力 → 选择 → 后果",
                "ending_strategy": "根据故事自然收束，闭合或开放均可",
                "tone_guidance": "自然、真实",
            },
        )

        # --- Build strategy ---
        recipe_slots: dict[str, str] = {}
        for slot_key in ("A", "B", "C", "D", "E"):
            val = recipe_data.get(slot_key, "")
            if val:
                recipe_slots[slot_key] = val

        return ResolvedStoryStrategy(
            story_mode=resolved_mode,
            mode_label={
                "viral_drama": "爆款广播剧",
                "general": "通用故事",
                "mystery": "悬疑推理",
                "serialized": "连载",
            }.get(resolved_mode, resolved_mode),
            genre_id=resolved_genre_id,
            genre_name=genre_data.get("name", ""),
            genre_mechanism=genre_data.get("mechanism", ""),
            genre_emotion=genre_data.get("emotion", ""),
            recipe_id=resolved_recipe_id or "",
            recipe_name=recipe_data.get("name", ""),
            recipe_slots=recipe_slots,
            recipe_landing_note=recipe_data.get("landing_note", ""),
            template_ref=template_ref or "",
            template_version=1,
            explicit_fields=sorted(explicit),
            auto_filled_fields=sorted(auto_filled),
            conflict_mechanism=mechanisms["conflict_mechanism"],
            causal_driver=mechanisms["causal_driver"],
            ending_strategy=mechanisms["ending_strategy"],
            tone_guidance=mechanisms["tone_guidance"],
            genre_data=genre_data,
            recipe_data=recipe_data,
        )