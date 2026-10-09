"""规则库装载层。

两份 JSON 是引擎的"宪法"，只读装载；所有节点与校验器都从这里取参数，
任何一处硬编码的阈值都应视为 bug。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FORMULA_LIB = "drama-formula-library.json"
TIMETRAVEL_LIB = "穿越剧引擎规则.json"
# 第三份规则库：人物选择规律 + 关系变化 + 事实账本 + 证据评审判据。
# 它单独成库而不是并进前两份，原因是它服务于一组全新的问题（人物是否有魅力、
# 剧情是否接得住），与"题材公式"和"穿越剧引擎"的关注点不同；
# 且规则改了重跑文档脚本即可同步，三库同源。
CONTINUITY_LIB = "人物与连续性规则.json"

# 规则库的候选位置（相对 workspace 根，按序查找）。
# 设计意图：装载器主动搜寻规则库，而不是要求目录结构迁就代码。
# 这样把规则库放进子文件夹（规则库/）、与包同级、或放在工作区根都能工作，
# 部署形态不被代码锁死 —— 也避免了"改了目录就跑不起来"这类脆弱耦合。
LIB_SEARCH_DIRS = ("", "规则库", "3-规则库", "rules", "..", "../规则库", "../3-规则库", "../rules")

# 提示词版本。规则库或提示词任一变化，都必须让生成缓存失效。
PROMPT_VERSION = "p1.5.0"


def _default_workspace() -> Path:
    env = os.environ.get("DRAMA_WORKSPACE")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _resolve_lib(filename: str, root: Path) -> Path:
    """在候选目录中定位规则库文件，全部落空时给出可操作的报错。"""
    tried: list[Path] = []
    for rel in LIB_SEARCH_DIRS:
        cand = (root / rel / filename).resolve() if rel else (root / filename).resolve()
        if cand.is_file():
            return cand
        tried.append(cand)
    raise FileNotFoundError(
        "找不到规则库「{}」。已尝试以下位置：\n  {}\n"
        "对策：把规则库放到上述任一目录，或用 DRAMA_WORKSPACE 环境变量 / "
        "--workspace 参数显式指定规则库所在目录。".format(
            filename, "\n  ".join(str(p) for p in tried)
        )
    )


@dataclass
class RuleLibrary:
    """两份规则库的只读视图 + 派生索引。"""

    formula: dict[str, Any] = field(default_factory=dict)
    timetravel: dict[str, Any] = field(default_factory=dict)
    continuity: dict[str, Any] = field(default_factory=dict)
    source_dir: Path = field(default_factory=_default_workspace)

    # ---------- 装载 ----------
    @classmethod
    def load(cls, workspace: str | Path | None = None) -> "RuleLibrary":
        root = Path(workspace) if workspace else _default_workspace()
        formula_path = _resolve_lib(FORMULA_LIB, root)
        timetravel_path = _resolve_lib(TIMETRAVEL_LIB, root)
        continuity_path = _resolve_lib(CONTINUITY_LIB, root)
        lib = cls(source_dir=formula_path.parent)
        lib.formula = _read_json(formula_path)
        lib.timetravel = _read_json(timetravel_path)
        lib.continuity = _read_json(continuity_path)
        return lib

    # ---------- 版本与缓存指纹 ----------
    @property
    def formula_version(self) -> str:
        return self.formula.get("meta", {}).get("version", "0.0.0")

    @property
    def timetravel_version(self) -> str:
        return self.timetravel.get("meta", {}).get("version", "0.0.0")

    @property
    def continuity_version(self) -> str:
        return self.continuity.get("meta", {}).get("version", "0.0.0")

    def cache_fingerprint(self, node: str, payload: str) -> str:
        """缓存键 = 节点 × 提示词版本 × 规则库版本（三库）× 输入。

        规则一变，旧缓存自动失效 —— 这条设计避免了"改了规则但输出没变"的隐蔽 bug。
        """
        raw = "|".join(
            [node, PROMPT_VERSION, self.formula_version, self.timetravel_version,
             self.continuity_version, payload]
        )
        return hashlib.blake2b(raw.encode("utf-8"), digest_size=12).hexdigest()

    # ---------- 派生索引（供节点与校验器 O(1) 取用）----------
    @property
    def genres(self) -> list[dict]:
        return self.formula.get("genre_fit_matrix", [])

    def genre(self, genre_id: str) -> dict | None:
        return next((g for g in self.genres if g.get("genre_id") == genre_id), None)

    @property
    def audio_ready_genres(self) -> list[dict]:
        """广播剧适配分 >= 70 的赛道。选题节点的白名单。"""
        return [g for g in self.genres if g.get("audio_fit_score", 0) >= 70]

    @property
    def recipes(self) -> list[dict]:
        return self.formula.get("roster_recipes", [])

    def recipe(self, recipe_id: str) -> dict | None:
        return next((r for r in self.recipes if r.get("id") == recipe_id), None)

    @property
    def beat_segments(self) -> list[dict]:
        return self.formula.get("episode_beat_sheet", {}).get("segments", [])

    def beat_sheet_for(self, duration_sec: int) -> list[dict]:
        """按目标时长解算节拍表。这是约束求解，不是让模型自由发挥。"""
        if duration_sec in (120, 180, 300):
            # The source JSON supplies a canonical 180-second sheet. Some
            # segment-level overrides for 300 seconds are incomplete; scale
            # every boundary together so the final hook reaches the target.
            source = self.beat_segments
            boundaries = [source[0]["range"][0], *(item["range"][1] for item in source)]
            base_duration = boundaries[-1]
            scaled = [round(value * duration_sec / base_duration) for value in boundaries]
            return [
                {**{k: v for k, v in segment.items() if k != "duration_scaling"},
                 "range": [scaled[index], scaled[index + 1]]}
                for index, segment in enumerate(source)
            ]
        out: list[dict] = []
        for seg in self.beat_segments:
            seg = dict(seg)
            scaling = seg.pop("duration_scaling", None)
            if scaling and f"{duration_sec}s" in scaling:
                seg["range"] = scaling[f"{duration_sec}s"]
            out.append(seg)
        return out

    @property
    def max_voiced_characters(self) -> int:
        return self.formula.get("audio_drama_constraints", {}).get("max_voiced_characters", 5)

    def max_characters(self, default: int = 5) -> int:
        """Phase 3: 泛用的角色上限（适用于 CharacterResolver）。

        当前默认读取 max_voiced_characters。未来不同 Mode 可 override。
        """
        return self.max_voiced_characters

    @property
    def visual_blacklist(self) -> list[str]:
        return (
            self.formula.get("audio_visual_substitutes", {}).get("blacklist_keywords", [])
        )

    @property
    def audio_event_categories(self) -> list[dict]:
        return self.formula.get("audio_visual_substitutes", {}).get("categories", [])

    @property
    def hook_types(self) -> list[dict]:
        return self.formula.get("hook_types", [])

    @property
    def hook_ids(self) -> list[str]:
        return [h["id"] for h in self.hook_types]

    @property
    def series_arc_rules(self) -> list[dict]:
        return self.formula.get("series_arc_rules", [])

    @property
    def validation_rules(self) -> dict[str, dict]:
        return {r["id"]: r for r in self.formula.get("validation_rules", [])}

    @property
    def k_rules(self) -> dict[str, dict]:
        return {r["id"]: r for r in self.timetravel.get("rules", [])}

    @property
    def failure_modes(self) -> list[dict]:
        return self.timetravel.get("failure_modes", [])

    @property
    def value_layers(self) -> dict[str, dict]:
        return {x["id"]: x for x in self.timetravel.get("value_layers", [])}

    @property
    def tension_curves(self) -> dict[str, dict]:
        return {x["id"]: x for x in self.timetravel.get("asset_tension_curves", [])}

    @property
    def four_act_structure(self) -> list[dict]:
        return self.timetravel.get("four_act_structure", [])

    @property
    def master_formula(self) -> str:
        return self.timetravel.get("master_formula", "")

    @property
    def application_checklist(self) -> list[str]:
        return self.timetravel.get("application_checklist", [])

    # ---------- 人物与连续性规则库的派生索引 ----------
    @property
    def pressure_types(self) -> dict[str, dict]:
        return {p["id"]: p for p in self.continuity.get("pressure_types", [])}

    @property
    def relationship_axes(self) -> dict[str, dict]:
        return {a["id"]: a for a in self.continuity.get("relationship_axes", [])}

    @property
    def slow_axes(self) -> set[str]:
        """慢变量关系轴。方向反转需要更多转折点（RL04）—— 阈值来自规则库，不硬编码。"""
        return {a["id"] for a in self.continuity.get("relationship_axes", [])
                if a.get("slow_variable")}

    @property
    def choice_rules(self) -> dict[str, dict]:
        return {r["id"]: r for r in self.continuity.get("character_choice_rules", [])}

    @property
    def relation_rules(self) -> dict[str, dict]:
        return {r["id"]: r for r in self.continuity.get("relationship_rules", [])}

    @property
    def fact_rules(self) -> dict[str, dict]:
        return {r["id"]: r for r in self.continuity.get("fact_ledger_rules", [])}

    @property
    def evidence_rules(self) -> dict[str, dict]:
        return {r["id"]: r for r in self.continuity.get("evidence_review_rules", [])}

    @property
    def fake_patterns(self) -> dict[str, dict]:
        return {p["id"]: p for p in self.continuity.get("fake_patterns", [])}

    @property
    def choice_cliche_blacklist(self) -> list[str]:
        """代价与底线字段的套话黑名单。『代价是消耗体力』这类表述等于没写。"""
        return self.continuity.get("cliche_blacklist", [])

    @property
    def choice_placeholder_values(self) -> list[str]:
        """占位符取值表。与套话黑名单的区别是匹配方式：占位符**整字段相等**才算命中。

        不区分这两类的后果是双向的：把『没有』当子串匹配，会误杀『从此没有回头路』，
        又会放过『还没有想好，大概是失去一些东西』这类敷衍回答。
        """
        spec = self.continuity.get("placeholder_values", {})
        return list(spec.get("values", [])) if isinstance(spec, dict) else []

    @property
    def choice_field_spec(self) -> list[dict]:
        return self.continuity.get("choice_field_spec", [])

    @property
    def choice_rule_field_spec(self) -> list[dict]:
        """单条选择规律的字段规格（压力 / 触发 / 选择 / 代价 / 是否反自身利益 / 外显形态）。"""
        return self.continuity.get("choice_rule_field_spec", [])

    @property
    def resource_balance(self) -> dict:
        """资源余量判定的材料与规则（字段名 / 耗尽标记 / 判定理由）。"""
        spec = self.continuity.get("resource_balance", {})
        return spec if isinstance(spec, dict) else {}

    @property
    def depletion_markers(self) -> list[str]:
        """耗尽标记 —— 资源漂移（resource_drift）的静态判定词表。"""
        return list(self.resource_balance.get("depletion_markers", []))

    @property
    def thresholds(self) -> dict[str, float]:
        """人物与连续性层的阈值。全部从规则库取 —— 阈值写进代码就是 bug。"""
        return dict(self.continuity.get("thresholds", {}))

    def threshold(self, key: str, default: float) -> float:
        return self.thresholds.get(key, default)

    @property
    def evidence_max_chars(self) -> int:
        return int(self.continuity.get("evidence_requirements", {}).get("max_evidence_chars", 120))

    def rule_by_id(self, rule_id: str) -> dict:
        """跨三库统一查询一条规则。

        为什么要这个：_severity() 需要按规则编号取严重级别，而规则现在分布在三个库里。
        写三处 if 分支会在加第四个库时静默失效。
        """
        for table in (self.validation_rules, self.k_rules, self.choice_rules,
                      self.relation_rules, self.fact_rules, self.evidence_rules):
            if rule_id in table:
                return table[rule_id]
        return {}

    def rule_meta(self, family: str) -> dict[str, dict]:
        """按族取规则（供文档与规格导出使用）。"""
        return {
            "K": self.k_rules,
            "R": self.validation_rules,
            "CH": self.choice_rules,
            "RL": self.relation_rules,
            "FC": self.fact_rules,
            "EV": self.evidence_rules,
        }.get(family, {})

    def manifest(self) -> dict:
        """给前端/监控用的规则库指纹。"""
        return {
            "formula_version": self.formula_version,
            "timetravel_version": self.timetravel_version,
            "continuity_version": self.continuity_version,
            "prompt_version": PROMPT_VERSION,
            "genres": len(self.genres),
            "recipes": len(self.recipes),
            "r_rules": len(self.validation_rules),
            "k_rules": len(self.k_rules),
            "ch_rules": len(self.choice_rules),
            "rl_rules": len(self.relation_rules),
            "fc_rules": len(self.fact_rules),
            "ev_rules": len(self.evidence_rules),
            "max_voiced_characters": self.max_voiced_characters,
        }


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"规则库缺失: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
