"""Quick R6 verification — single case test."""
import json, sys, time, uuid, os
from pathlib import Path

PROJECT = Path(r'H:\Projects\StoryGenerate')
sys.path.insert(0, str(PROJECT / '4-引擎代码'))
OUT_DIR = PROJECT / '6-实测产物' / 'acceptance' / 'r6_r13_verification'
os.makedirs(OUT_DIR, exist_ok=True)

from drama_engine.config import RuleLibrary
from drama_engine.workflow.strategy import StoryStrategyResolver
from drama_engine.workflow.service import StoryWorkflowService
from drama_engine.workflow.schemas import (
    StoryPreferences, StoryIntent, CreationPreferences,
)
from drama_engine.workflow.delivery import export_delivery_bundle, verify_round_trip
from drama_engine.core.provider import build_provider_from_env

def main():
    lib = RuleLibrary.load()
    resolver = StoryStrategyResolver(lib)
    provider = build_provider_from_env()
    service = StoryWorkflowService(
        plan_generator=provider,
        repository=None,
        template_resolver=None,
        strategy_resolver=resolver,
    )

    idea = '一个退休刑警在整理旧案时发现了一桩二十年前的失踪案与他最信任的搭档有关。'
    print('=== R6 悬疑反转 验证 ===')
    print(f'创意: {idea}')
    start = time.time()

    strategy = resolver.resolve(
        story_mode='mystery', genre='G11', recipe_id='R6',
        user_instruction=idea,
        explicit_fields=['story_mode', 'genre', 'recipe_id'],
    )
    print(f'Strategy: {strategy.recipe_name} / {strategy.genre_name} / mode={strategy.story_mode}')

    prefs = CreationPreferences(story_mode='mystery', genre='G11', recipe_id='R6')
    request = StoryPreferences(
        intent=StoryIntent.CREATE, user_instruction=idea,
        creation_preferences=prefs, request_id=uuid.uuid4().hex,
    )

    try:
        plan = service.prepare_story_plan(request)
        elapsed_plan = time.time() - start
        print(f'Plan 完成 ({elapsed_plan:.0f}s)')
        plan_path = OUT_DIR / 'A_R6_plan.json'
        plan_path.write_text(json.dumps(plan.model_dump(mode='json'), ensure_ascii=False, indent=2), encoding='utf-8')

        approved = service.approve_story_plan(plan.plan_id, prefs)
        delivery = service.generate_from_approved_plan(approved, prefs, idea)
        elapsed_total = time.time() - start
        print(f'Generate 完成 ({elapsed_total:.0f}s)')

        rt_ok = verify_round_trip(delivery)
        print(f'Round-trip: {"OK" if rt_ok else "FAIL"}')

        export_delivery_bundle(delivery, str(OUT_DIR), 'A_R6')

        total_utts = sum(len(scene.utterances) for ep in delivery.episodes for scene in ep.scenes)
        duration = sum(sum(u.duration_estimate_sec or 0 for u in scene.utterances) for ep in delivery.episodes for scene in ep.scenes)
        print(f'{len(delivery.episodes)} 集 / {total_utts} 句 / ~{duration:.0f}s')
        print('OK: R6 verification succeeded')
    except Exception as e:
        elapsed = time.time() - start
        print(f'FAIL ({elapsed:.0f}s): {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()