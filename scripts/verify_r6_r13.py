"""Real-model verification for R6-R13 recipes.

Selects 4 representative cases from 24 test ideas, generates stories with
2 different recipes each, and saves Plan / StoryDelivery / readable script
/ token + timing data.

Usage:
    $env:DRAMA_LLM_API_KEY = "..."
    python scripts/verify_r6_r13.py
"""
from __future__ import annotations

import json, os, sys, time, uuid
from pathlib import Path
from dataclasses import dataclass, field

# Ensure `drama_engine` is importable
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "4-引擎代码"))

from drama_engine.config import RuleLibrary
from drama_engine.workflow.strategy import StoryStrategyResolver
from drama_engine.workflow.service import StoryWorkflowService
from drama_engine.workflow.schemas import (
    StoryDelivery, StoryPreferences, StoryIntent,
    CreationPreferences, StoryModeChoice, TemplateRef,
)
from drama_engine.workflow.delivery import (
    delivery_to_json, delivery_to_readable_script,
    export_delivery_bundle, verify_round_trip,
)
from drama_engine.core.provider import (
    build_provider_from_env, LLMProvider,
)
from drama_engine.config import StoryEngineConfig

# ── Cases ──────────────────────────────────────────────────────────────────

CASES = [
    {
        "id": "A_R6_vs_R11",
        "idea": "一个退休刑警在整理旧案时发现了一桩二十年前的失踪案与他最信任的搭档有关。",
        "genre": "G11",  # 悬疑推理
        "mode": "mystery",
        "recipe_a": "R6",  # 悬疑反转
        "recipe_b": "R11",  # 先婚后爱 (对比: 同样悬疑，不同情感处理)
        "note": "测试R6悬疑反转机制 vs 情感向配方在悬疑题材的差异",
    },
    {
        "id": "B_R7_vs_R13",
        "idea": "被公司以'能力不足'为由辞退的中年程序员，拿着赔偿金和同事的源代码，在共享办公室里开发出颠覆原公司的产品。",
        "genre": "G14",  # 职场生存
        "mode": "viral_drama",
        "recipe_a": "R7",  # 逆袭打脸
        "recipe_b": "R13",  # 职场商战
        "note": "测试R7逆袭打脸 vs R13职场商战在同一个职场创意的差异",
    },
    {
        "id": "C_R8_identity",
        "idea": "高考后，两个被调换身份的女生同时收到了对方的录取通知书——一个该去清华，一个该去职校。",
        "genre": "G11",  # 悬疑推理
        "mode": "general",
        "recipe_a": "R8",  # 身份反转
        "recipe_b": "R6",  # 悬疑反转
        "note": "测试R8身份反转 vs R6悬疑反转在身份错位题材的差异",
    },
    {
        "id": "D_R4_vs_R12",
        "idea": "离婚冷静期的最后一天，妻子在收拾行李时发现了丈夫藏在衣柜夹层里的器官捐献登记卡——器官接收人是她。",
        "genre": "G01",  # 现实家庭冲突
        "mode": "general",
        "recipe_a": "R4",  # 家庭反击
        "recipe_b": "R12",  # 替身虐恋
        "note": "测试R4家庭反击 vs R12替身虐恋在同一高情感创意下的差异",
    },
]

OUT_DIR = PROJECT / "6-实测产物" / "acceptance" / "r6_r13_verification"


def main():
    print("=== R6-R13 真实模型验证 ===\n")

    # Check API key
    api_key = os.environ.get("DRAMA_LLM_API_KEY")
    if not api_key:
        print("❌ 需要设置 DRAMA_LLM_API_KEY 环境变量")
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)

    lib = RuleLibrary.load()
    resolver = StoryStrategyResolver(lib)
    provider = build_provider_from_env()
    config = StoryEngineConfig(provider=provider, rule_library=lib)

    print(f"Provider: {provider.__class__.__name__}")
    print(f"Model: {os.environ.get('DRAMA_LLM_MODEL', 'default')}")
    print(f"Cases: {len(CASES)}")
    print()

    results_summary = []

    for case in CASES:
        case_id = case["id"]
        print(f"=== {case_id}: {case['note']} ===")
        print(f"  创意: {case['idea'][:60]}...")

        for recipe_label, recipe_id in [("A", case["recipe_a"]), ("B", case["recipe_b"])]:
            label = f"{case_id}_{recipe_label}_{recipe_id}"
            print(f"\n  [{label}] 开始生成...")

            # Resolve strategy
            try:
                strategy = resolver.resolve(
                    story_mode=case["mode"],
                    genre=case["genre"],
                    recipe_id=recipe_id,
                    user_instruction=case["idea"],
                    explicit_fields=["story_mode", "genre", "recipe_id"],
                )
            except Exception as e:
                print(f"    ❌ Strategy resolve 失败: {e}")
                results_summary.append({
                    "case": case_id, "recipe": recipe_id, "status": "strategy_error",
                    "error": str(e),
                })
                continue

            print(f"    Strategy: {strategy.recipe_name} / {strategy.genre_name} / {strategy.story_mode}")

            # Build preferences
            prefs = CreationPreferences(
                story_mode=case["mode"],
                genre=case["genre"],
                recipe_id=recipe_id,
            )

            # Prepare request
            request = StoryPreferences(
                intent=StoryIntent.CREATE,
                user_instruction=case["idea"],
                creation_preferences=prefs,
                request_id=uuid.uuid4().hex,
            )

            # Generate
            start = time.time()
            try:
                plan = config.service.prepare_story_plan(request)
            except Exception as e:
                elapsed = time.time() - start
                print(f"    ❌ Plan 生成失败 ({elapsed:.0f}s): {e}")
                results_summary.append({
                    "case": case_id, "recipe": recipe_id, "status": "plan_error",
                    "error": str(e), "elapsed_sec": elapsed,
                })
                continue

            elapsed = time.time() - start
            print(f"    ✓ Plan 生成 ({elapsed:.0f}s)")

            # Save plan
            plan_path = OUT_DIR / f"{label}_plan.json"
            plan_path.write_text(
                json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # Approve and generate delivery
            try:
                approved = config.service.approve_story_plan(plan.plan_id, request.creation_preferences)
            except Exception as e:
                print(f"    ❌ Approve 失败: {e}")
                results_summary.append({
                    "case": case_id, "recipe": recipe_id, "status": "approve_error",
                    "error": str(e),
                })
                continue

            try:
                delivery = config.service.generate_from_approved_plan(
                    approved, request.creation_preferences, request.user_instruction,
                )
            except Exception as e:
                print(f"    ❌ Generate 失败: {e}")
                results_summary.append({
                    "case": case_id, "recipe": recipe_id, "status": "generate_error",
                    "error": str(e),
                })
                continue

            # Verify round-trip
            rt_ok = verify_round_trip(delivery)
            print(f"    ✓ Round-trip: {'OK' if rt_ok else 'FAIL'}")

            # Export
            export_delivery_bundle(delivery, str(OUT_DIR), label)
            print(f"    ✓ 导出: {label}.json + .txt + _characters.json")

            # Quick stats
            total_utterances = sum(
                len(scene.utterances)
                for ep in delivery.episodes
                for scene in ep.scenes
            )
            duration = sum(
                sum(u.duration_estimate_sec or 0 for u in scene.utterances)
                for ep in delivery.episodes
                for scene in ep.scenes
            )
            print(f"    📊 {len(delivery.episodes)} 集 / {total_utterances} 句台词 / ~{duration:.0f}s")

            results_summary.append({
                "case": case_id,
                "recipe": recipe_id,
                "recipe_name": strategy.recipe_name,
                "status": "ok",
                "elapsed_sec": elapsed,
                "episodes": len(delivery.episodes),
                "utterances": total_utterances,
                "duration_sec": round(duration),
            })

    # ── Summary ──
    print("\n\n=== 验证结果汇总 ===\n")
    summary_path = OUT_DIR / "_summary.json"
    summary_path.write_text(
        json.dumps(results_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ok = [r for r in results_summary if r["status"] == "ok"]
    err = [r for r in results_summary if r["status"] != "ok"]
    print(f"✅ 成功: {len(ok)}")
    print(f"❌ 失败: {len(err)}")
    if err:
        for e in err:
            print(f"   {e['case']}/{e['recipe']}: {e['status']} — {e.get('error', '')}")
    print(f"\n产物目录: {OUT_DIR}")
    print(f"汇总文件: {summary_path}")


if __name__ == "__main__":
    main()