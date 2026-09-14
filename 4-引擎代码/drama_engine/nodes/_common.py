"""节点公共工具：从 RunnableConfig 取规则库与运行时，以及计数/重试的工具函数。"""
from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from ..config import RuleLibrary
from ..contracts import Runtime

MAX_ATTEMPTS = 3


def deps(config: RunnableConfig | None) -> tuple[RuleLibrary, Runtime]:
    """约定：图以 config={"configurable": {"lib": ..., "runtime": ...}} 调用。

    依赖从 config 走而不是全局单例，是为了让同一进程内可以并行跑多个不同规则库版本的项目
    （灰度发布新规则库时必须有这个能力）。
    """
    cfg: dict[str, Any] = (config or {}).get("configurable") or {}
    lib = cfg.get("lib")
    runtime = cfg.get("runtime")
    if lib is None or runtime is None:
        raise RuntimeError("图必须以 config={'configurable': {'lib':…, 'runtime':…}} 调用")
    return lib, runtime


# ---------------------------------------------------------------- 计数器（累加）
def bump(key: str, n: int = 1) -> dict[str, int]:
    """返回计数器增量。由 sum_dict reducer 负责累加 —— 节点只管报自己用了几次。"""
    return {key: n}


# ---------------------------------------------------------------- 重试轮次（覆盖）
def attempt_of(state: dict, key: str) -> int:
    return int((state.get("attempts") or {}).get(key, 0))


def next_attempt(state: dict, key: str) -> tuple[int, dict[str, int]]:
    """返回 (新一轮次号, 待写入的 attempts 增量)。"""
    value = attempt_of(state, key) + 1
    return value, {key: value}


# ---------------------------------------------------------------- 校验结论工具
def findings_payload(findings) -> list[dict]:
    out = []
    for f in findings or []:
        out.append(f.model_dump() if hasattr(f, "model_dump") else dict(f))
    return out


def only(findings, route: str) -> list[dict]:
    """取出应交给某个修复节点的违规。"""
    return [p for p in findings_payload(findings) if p.get("route") == route]


def has_errors(report) -> bool:
    if report is None:
        return False
    return bool(report.errors)


def error_signature(report) -> str:
    """违规集合的指纹（只看规则编号，不看具体文案）。"""
    if report is None:
        return ""
    return ",".join(sorted({f.rule_id for f in report.errors}))


def stuck_guard(state: dict, key: str, report) -> dict[str, Any]:
    """记录本轮违规指纹，并判断修复是否"卡住"。

    动机：模型在某条规则上反复失败时，再重试一次的结果通常与上一次相同。
    无限重试是最常见的生产事故来源 —— 预算被烧光，问题一个没解决。
    因此只要**连续两轮的违规指纹完全一致**，就判定修复无效，立即放弃并交人工。
    """
    sig = error_signature(report)
    prev = (state.get("attempts") or {}).get(f"{key}_sig")
    return {
        f"{key}_sig": sig,
        f"{key}_stuck": 1 if (prev and prev == sig) else 0,
    }


def is_stuck(state: dict, key: str) -> bool:
    return bool((state.get("attempts") or {}).get(f"{key}_stuck", 0))


def should_repair(state: dict, key: str, limit_key: str | None = None) -> bool:
    """统一的修复决策：有 error、未超轮次上限、且没有卡住。"""
    if not has_errors(state.get("project_report")):
        return False
    if attempt_of(state, limit_key or key) >= MAX_ATTEMPTS:
        return False
    return not is_stuck(state, key)
