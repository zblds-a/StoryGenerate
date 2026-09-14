"""模型分级路由。

这里是成本控制的核心论点：**不是所有节点都值得用最强模型。**

杠杆率差异极大：
  - 开场 3 秒钩子、二次反转、结尾强钩子 —— 决定完播率，用最强模型，一个 token 都不能省。
  - 中段推进、音频化改写、字段补全 —— 结构固定、可校验，用便宜模型，错了还有校验节点兜底。

因此"用哪个模型"是节点的属性，不是全局配置。
"""
from __future__ import annotations

from .base import LLMSpec

# 节点 role → 模型档位。tier 由部署方在部署配置里映射到具体模型名。
MODEL_ROUTING: dict[str, dict] = {
    # 高杠杆：结构决策 + 剧作判断，一旦错，后面全错
    "topic_select":        {"tier": "reasoning", "temperature": 0.3, "max_tokens": 2048},
    "gadget_design":       {"tier": "reasoning", "temperature": 0.5, "max_tokens": 3072},
    "cast_design":         {"tier": "reasoning", "temperature": 0.6, "max_tokens": 3072},
    # 人物选择规律：决定"人物是否有魅力"，与开头钩子同级的高杠杆节点
    "behavior_design":     {"tier": "reasoning", "temperature": 0.7, "max_tokens": 6144},
    # 账本是核对型产物，需要的是严谨而非灵感，温度压低
    "fact_ledger":         {"tier": "reasoning", "temperature": 0.2, "max_tokens": 6144},
    "outline":             {"tier": "reasoning", "temperature": 0.5, "max_tokens": 8192},
    # 最高杠杆：三处钩子单独用强模型生成
    "hook_open":           {"tier": "strong",    "temperature": 0.9, "max_tokens": 1024},
    "hook_reversal":       {"tier": "strong",    "temperature": 0.9, "max_tokens": 1024},
    "hook_cliffhanger":    {"tier": "strong",    "temperature": 0.95, "max_tokens": 1024},
    # 中低杠杆：结构化填充，便宜模型足够，校验节点兜底
    "episode_beats":       {"tier": "cheap",     "temperature": 0.85, "max_tokens": 4096},
    "audio_adapt":         {"tier": "cheap",     "temperature": 0.4, "max_tokens": 4096},
    "repair_beat":         {"tier": "strong",    "temperature": 0.7, "max_tokens": 2048},
    "repair_audio":        {"tier": "cheap",     "temperature": 0.3, "max_tokens": 2048},
    "repair_cast":         {"tier": "reasoning", "temperature": 0.4, "max_tokens": 2048},
    "repair_gadget":       {"tier": "reasoning", "temperature": 0.4, "max_tokens": 2048},
    "repair_behavior":     {"tier": "reasoning", "temperature": 0.6, "max_tokens": 4096},
    "repair_ledger":       {"tier": "reasoning", "temperature": 0.3, "max_tokens": 4096},
    "repair_outline":      {"tier": "reasoning", "temperature": 0.4, "max_tokens": 4096},
    "repair_compliance":   {"tier": "reasoning", "temperature": 0.3, "max_tokens": 2048},
    # 语义裁判：温度 0，同一份剧本两次跑必须得到同一结论
    "judge":               {"tier": "strong",    "temperature": 0.0, "max_tokens": 4096},
}

DEFAULT_ROUTE = {"tier": "cheap", "temperature": 0.7, "max_tokens": 4096}


class ModelTierMap:
    """档位 → 具体模型名。部署时用环境变量或配置文件覆盖即可，无需改代码。"""

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self.mapping = mapping or {
            "reasoning": "mock",
            "strong": "mock",
            "cheap": "mock",
        }

    def resolve(self, tier: str) -> str:
        return self.mapping.get(tier, self.mapping.get("cheap", "mock"))


def resolve_spec(role: str, tier_map: ModelTierMap | None = None, **overrides) -> LLMSpec:
    tier_map = tier_map or ModelTierMap()
    config = dict(MODEL_ROUTING.get(role, DEFAULT_ROUTE))
    model = tier_map.resolve(config.pop("tier"))
    config.update(overrides)
    return LLMSpec(role=role, model=model, **config)
