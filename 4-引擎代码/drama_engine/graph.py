"""主图编排。

                          ┌──────── 立项段（串行，因为每一步都依赖前一步的结论）
                          │
  START ─▶ s0_intake ─▶ s1_topic ─▶ s2_gadget ─▶ [gate_gadget] ─┐
                                                    ▲             │ 不通过
                                                    └── repair_gadget
                                                                  │ 通过
                                                                  ▼
                              s3_cast ─▶ [gate_cast] ─┬─(不通过)─▶ repair_cast
                                                      └─(通过)──▶ s3b_behavior
                                                                        │
                              [gate_behavior] ─┬─(不通过)─▶ repair_behavior
                                               └─(通过)──▶ s4_outline ─▶ [gate_outline]
                                                                              │
                          ┌───────────────────────────────────────────────────┘
                          │  通过
                          ▼
                    s5_ledger ─▶ [gate_ledger] ─┬─(不通过)─▶ repair_ledger
                                                └─(通过)──▶ gate_bible
                                                                  │
                          ┌────────────────────────────────────────┘
                          │  并行 fan-out（每集一个独立任务，互不可见）
                          ▼
                    gen_episode × N  ──▶ s7_series_validate ──▶ s8_assemble ──▶ END

四处值得说明的编排决策：

1. **立项段必须串行。** 金手指决定角色（C 槽位是权力保护者还是护短群体，取决于金手指强度），
   角色决定行为（要为每个有声角色产行为卡），行为决定大纲（大纲要把"本集演练哪条选择"
   排到具体集数上），大纲决定账本（账本要引用具体集号）。
   依赖链是四级的，任何"并行加速立项"的尝试都会产出自相矛盾的底座。

2. **门放在能修它的那一步之后。** 金手指门紧跟金手指节点，角色门紧跟角色节点，
   人物门紧跟行为卡节点，账本门紧跟账本节点。放在末尾统一校验，
   等于把便宜的错误升级成昂贵的错误。

3. **逐集段必须并行且相互隔离。** 见 nodes/series.py 的说明 —— 隔离是为了内容的多样性。
   注意隔离的是**文本**：本集仍会拿到"必须承接的账目 + 出场角色的选择规律"这一份切片，
   但不读任何其它集的正文。事实连续，文本不连续。

4. **立项段收尾在 gate_bible。** 冻结的东西现在是五样：金手指、角色、行为卡、大纲、账本。
"""
from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .config import RuleLibrary
from .contracts import Runtime, set_runtime_factory
from .nodes import (
    dispatch_episodes,
    gate_behavior,
    gate_bible,
    gate_cast,
    gate_gadget,
    gate_ledger,
    gate_outline,
    gen_episode,
    repair_behavior,
    repair_cast,
    repair_gadget,
    repair_ledger,
    repair_outline,
    route_after_behavior,
    route_after_cast,
    route_after_gadget,
    route_after_ledger,
    route_after_outline,
    s0_intake,
    s1_topic,
    s2_gadget,
    s3_cast,
    s3b_behavior,
    s4_outline,
    s5_ledger,
    s7_series_validate,
    s8_assemble,
)
from .schemas import Brief
from .state import DramaState


def build_graph(checkpointer=None, use_checkpoint: bool = True):
    """编译主图。

    checkpoint 的意义：生成一部 60 集广播剧是**分钟到小时级的长任务**。
    没有 checkpoint，进程中断就意味着从第 1 集重来。
    接入生产时应把 InMemorySaver 换成 SqliteSaver 或 PostgresSaver。
    """
    graph = StateGraph(DramaState)

    # ---- 立项段 ----
    graph.add_node("s0_intake", s0_intake)
    graph.add_node("s1_topic", s1_topic)
    graph.add_node("s2_gadget", s2_gadget)
    graph.add_node("gate_gadget", gate_gadget)
    graph.add_node("repair_gadget", repair_gadget)
    graph.add_node("s3_cast", s3_cast)
    graph.add_node("gate_cast", gate_cast)
    graph.add_node("repair_cast", repair_cast)
    graph.add_node("s3b_behavior", s3b_behavior)
    graph.add_node("gate_behavior", gate_behavior)
    graph.add_node("repair_behavior", repair_behavior)
    graph.add_node("s4_outline", s4_outline)
    graph.add_node("gate_outline", gate_outline)
    graph.add_node("repair_outline", repair_outline)
    graph.add_node("s5_ledger", s5_ledger)
    graph.add_node("gate_ledger", gate_ledger)
    graph.add_node("repair_ledger", repair_ledger)
    graph.add_node("gate_bible", gate_bible)

    # ---- 逐集段 ----
    graph.add_node("gen_episode", gen_episode)
    graph.add_node("s7_series_validate", s7_series_validate)
    graph.add_node("s8_assemble", s8_assemble)

    # ---- 立项段连边 ----
    graph.add_edge(START, "s0_intake")
    graph.add_edge("s0_intake", "s1_topic")
    graph.add_edge("s1_topic", "s2_gadget")
    graph.add_edge("s2_gadget", "gate_gadget")
    graph.add_conditional_edges(
        "gate_gadget", route_after_gadget,
        {"repair_gadget": "repair_gadget", "s3_cast": "s3_cast"},
    )
    graph.add_edge("repair_gadget", "gate_gadget")

    graph.add_edge("s3_cast", "gate_cast")
    graph.add_conditional_edges(
        "gate_cast", route_after_cast,
        {"repair_cast": "repair_cast", "s3b_behavior": "s3b_behavior"},
    )
    graph.add_edge("repair_cast", "gate_cast")

    graph.add_edge("s3b_behavior", "gate_behavior")
    graph.add_conditional_edges(
        "gate_behavior", route_after_behavior,
        {"repair_behavior": "repair_behavior", "s4_outline": "s4_outline"},
    )
    graph.add_edge("repair_behavior", "gate_behavior")

    graph.add_edge("s4_outline", "gate_outline")
    graph.add_conditional_edges(
        "gate_outline", route_after_outline,
        {"repair_outline": "repair_outline", "s5_ledger": "s5_ledger"},
    )
    graph.add_edge("repair_outline", "gate_outline")

    graph.add_edge("s5_ledger", "gate_ledger")
    graph.add_conditional_edges(
        "gate_ledger", route_after_ledger,
        {"repair_ledger": "repair_ledger", "gate_bible": "gate_bible"},
    )
    graph.add_edge("repair_ledger", "gate_ledger")

    # ---- 立项冻结 → 并行派发 ----
    # 条件边的返回值是 list[Send]，LangGraph 会据此创建 N 个并行任务
    graph.add_conditional_edges("gate_bible", dispatch_episodes, ["gen_episode"])

    # ---- 归约：所有 gen_episode 分支都汇入 s7 ----
    graph.add_edge("gen_episode", "s7_series_validate")
    graph.add_edge("s7_series_validate", "s8_assemble")
    graph.add_edge("s8_assemble", END)

    saver = checkpointer if checkpointer is not None else (InMemorySaver() if use_checkpoint else None)
    return graph.compile(checkpointer=saver)


def run_pipeline(
    idea: str,
    workspace: str,
    lib: RuleLibrary,
    runtime: Runtime,
    target_episodes: int = 8,
    target_duration_sec: int = 180,
    locked_assets: list[str] | None = None,
    thread_id: str = "local",
    story_mode: str | None = None,
    graph=None,
) -> dict[str, Any]:
    """命令行 / 服务层入口。

    Runtime 通过工厂注入而不是当作参数层层传递 —— 节点只需要 LLMSpec 与 Protocol，
    不应该看见 HTTP 客户端、API key 这类基础设施细节。

    Phase 2: 新增 story_mode 参数。默认 None → viral_drama。
    """
    from .modes import get_mode, ModeContext

    mode = get_mode(story_mode)
    mode_ctx = ModeContext.from_mode(mode)

    set_runtime_factory(lambda: runtime)
    app = graph or build_graph()
    initial = {
        "brief": Brief(
            raw_idea=idea,
            target_episodes=target_episodes,
            target_duration_sec=target_duration_sec,
            locked_assets=locked_assets or [],
        ),
        "mode_context": mode_ctx,
        "workspace": workspace,
        "episodes": [],
        "findings": [],
        "unclaimed": [],
        "trace": [],
        "budgets": {},
    }
    config = {"configurable": {"lib": lib, "runtime": runtime}, "recursion_limit": 120,
              "configurable_thread": thread_id}
    config["configurable"]["thread_id"] = thread_id
    return app.invoke(initial, config)
