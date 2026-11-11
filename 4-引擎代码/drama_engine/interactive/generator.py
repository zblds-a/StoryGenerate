"""Model adapter. Only complete fields are exposed when streaming is unavailable."""
from __future__ import annotations
import json
from typing import Literal
from uuid import uuid4
from pydantic import Field, create_model, model_validator
from .models import Model, Outline, Directions, GENRES
from ..llm.router import resolve_spec
from ..workflow.adapters import DraftLine, DraftScene, normalize_draft_stage_directions, DraftEpisode, LLMPerformanceAnnotator
from ..workflow.schemas import (CharacterSnapshot, CharacterPortrayal, PlanContent, EpisodeOutline,
                                SceneDelivery, EpisodeDelivery, StoryDelivery)
from ..workflow.performance import validate_story_delivery
from ..workflow.delivery import validate_delivery_integrity
from ..workflow.strategy import StoryStrategyResolver
from ..config import RuleLibrary
from .prompts import CRAFT


class SceneResult(Model):
    scene: DraftScene
    facts: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    preview_blurb: str = Field(min_length=15, max_length=160)


class StoryOutline(Outline):
    character_portrayals: list[CharacterPortrayal] = Field(min_length=1)


def bound_scene_schema(role_ids, budget=None):
    role_type = Literal[tuple(sorted(role_ids))]
    def check_voice(self):
        if self.kind == 'dialogue' and self.speaker_role_id not in role_ids:
            raise ValueError('Dialogue requires an approved speaker: ' + ','.join(sorted(role_ids)) +
                             '. Rewrite unbound third-party speech as the approved characters reactions or non-spoken action.')
        return self
    line = create_model('ApprovedCastLine', __base__=DraftLine,
        kind=(Literal['dialogue', 'narration', 'sfx', 'music', 'action'], ...),
        speaker_role_id=(role_type | None, None),
        __validators__={'approved_dialogue': model_validator(mode='after')(check_voice)})
    def check_size(self):
        if budget:
            count = sum(len(x.text) for x in self.lines if x.kind in ('dialogue','narration'))
            if not budget[0] <= count <= budget[2]:
                raise ValueError(f'Scene spoken text has {count} characters; required {budget[0]} to {budget[2]}, target {budget[1]}. Revise only this scene, retaining its approved actions and facts.')
        return self
    scene = create_model('ApprovedCastScene', __base__=DraftScene, lines=(list[line], Field(min_length=1)),
        __validators__={'spoken_budget': model_validator(mode='after')(check_size)})
    return create_model('ApprovedCastSceneResult', __base__=SceneResult, scene=(scene, ...))


class Generator:
    def __init__(self, provider):
        self.provider = provider

    def call(self, role, system, data, schema):
        return self.provider.complete_structured(resolve_spec(role), CRAFT + system, json.dumps(data, ensure_ascii=False), schema)

    def directions(self, state):
        return self.call('outline', '你是专业广播剧策划。按角色和选项给出三个不同、可演、简短的故事方向。',
                         {'creation': state['creation'], 'characters': state['characters']}, Directions).model_dump(mode='json')

    def outline(self, state):
        c = dict(state['creation'])
        expected_episodes = c['series_episodes'] if c['form'] == 'series' else 1
        if c['form'] == 'short':
            c.pop('series_episodes', None)
        schema = create_model('InteractiveOutline_' + str(expected_episodes), __base__=StoryOutline,
            episode_summaries=(list[str], Field(min_length=expected_episodes, max_length=expected_episodes)))
        mode, genre, recipe = GENRES[c['genre']]
        strategy = StoryStrategyResolver(RuleLibrary.load()).resolve(story_mode=mode, genre=genre,
            recipe_id=recipe, user_instruction=c['idea'], explicit_fields=['story_mode', 'genre', 'recipe_id'])
        return self.call('outline',
            '你是广播剧编剧。一次生成因果清楚的大纲、每幕背景描述和至多三个方向选项。'
            '只使用输入角色，保持身份与语言特点。不在背景提示词中画人物、文字、水印。'
            '短剧完整收束；长剧规划整个系列，仅展开当前集为2至6幕。所有角色ID必须来自输入。'
            '已完成的幕是不可改前缀，新的分幕规划必须逐项保留此前缀。'
            '选择合适的单集篇幅，不能把整个系列一次写完。',
            {'creation': c, 'direction': state.get('direction'), 'characters': state['characters'],
             'strategy': strategy.model_dump(mode='json'),
             'episode_count_required': expected_episodes,
             'episode_number': state['episode_number'], 'previous_outline': state.get('outline'),
             'series_outline': state.get('series_outline'), 'history': state['history'],
             'feedback': state.get('feedback', []), 'protected_scenes': state['scenes']}, schema).model_dump(mode='json')

    def scene(self, state, index):
        card = state['outline']['scenes'][index]
        previous = [*state['scenes'], *state.get('protected_suffix', [])]
        spent = sum(len(u['text']) for s in previous for u in s['scene']['utterances'] if u['kind'] in ('dialogue','narration'))
        remaining = 1 if state.get('protected_suffix') else len(state['outline']['scenes']) - index
        hard_remaining = int(1.6 * state['outline']['duration_sec'] * 3.5) - spent
        if hard_remaining < 30 and not state.get('_spoken_budget_override'):
            raise ValueError('DURATION_BUDGET_EXHAUSTED')
        target = max(20, round((state['outline']['duration_sec'] * 3.5 - spent) / remaining))
        maximum = min(max(30, int(1.3 * target)), max(30, hard_remaining // remaining))
        budget = state.get('_spoken_budget_override') or (min(maximum, max(10, int(.55 * target))), min(maximum, target), maximum)
        schema = bound_scene_schema({c['role_id'] for c in state['characters']}, budget)
        result = self.call('storycraft_episode_writer',
            '按已确认分幕写这一幕广播剧，不能新增角色、改变已发生事实或提前演完后续幕。'
            'dialogue/narration的text只写朗读内容，动作、音乐、音效独立列出。'
            '未绑定人物即使在大纲出现也不能发声，不能用空speaker_role_id掩盖第三人对白。'
            '给出本幕之后的事实及未解线索，用于下一幕延续。依照每幕字数预算完成剧情。',
            {'scene_card': card, 'characters': state['characters'],
             'character_portrayals': state['outline']['character_portrayals'],
             'strategy': StoryStrategyResolver(RuleLibrary.load()).resolve(
                 story_mode=GENRES[state['creation']['genre']][0], genre=GENRES[state['creation']['genre']][1],
                 recipe_id=GENRES[state['creation']['genre']][2], user_instruction='', explicit_fields=[]).writer_context(),
             'continuity': [s['continuity'] for s in state['scenes']], 'prior_episodes': state['history'],
             'spoken_character_budget': {'minimum': budget[0], 'target': budget[1], 'maximum': budget[2]},
             'remaining_scene_goals': [s['goal'] for s in state['outline']['scenes'][index + 1:]],
             'protected_following_scenes': state.get('protected_suffix', []),
             'feedback': state.get('feedback', [])}, schema)
        draft = normalize_draft_stage_directions(DraftEpisode(title=card['title'], synopsis='',
            preview_blurb=result.preview_blurb, scenes=[result.scene], episode_summary=''))
        scene = draft.scenes[0]
        if scene.location.strip() and scene.location.strip() != card['location'].strip():
            raise ValueError('SCENE_LOCATION_CONFLICT')
        roles = {c['role_id']: c['performer_id'] for c in state['characters']}
        if any(l.kind == 'dialogue' and l.speaker_role_id not in roles for l in scene.lines):
            raise ValueError('UNAPPROVED_ROLE')
        if not any(l.kind in ('dialogue', 'narration') and l.text.strip() for l in scene.lines):
            raise ValueError('EMPTY_SCENE')
        key = state['scene_keys'][index]
        lines = [{'line_id': key + '-l' + str(i + 1), 'kind': l.kind, 'speaker': l.speaker_role_id,
                  'text': l.text, 'performance_hint': l.performance_hint,
                  'performer_id': roles.get(l.speaker_role_id, 'narrator')} for i, l in enumerate(scene.lines)]
        utterances = LLMPerformanceAnnotator(self.provider).annotate(lines, {'scene': card['title']})
        delivery = SceneDelivery(scene_id=key, scene_index=index + 1, title=scene.title,
            location=card['location'], dramatic_goal=card['goal'], utterances=utterances)
        return {'scene': delivery.model_dump(mode='json'), 'preview_blurb': result.preview_blurb,
                'continuity': {'facts': result.facts, 'open_threads': result.open_threads}}

    def finalize(self, state):
        import copy
        state = copy.deepcopy(state)
        repaired = []
        target = state['outline']['duration_sec']
        count = sum(len(u['text']) for s in state['scenes'] for u in s['scene']['utterances'] if u['kind'] in ('dialogue','narration'))
        if not .3 * target <= round(count / 3.5) <= 1.6 * target:
            if state.get('change_scope') == 'scene' and state.get('change_start') != len(state['scenes']) - 1:
                raise ValueError('EPISODE_DURATION_OUT_OF_RANGE')
            old = state['scenes'][-1]
            prior = count - sum(len(u['text']) for u in old['scene']['utterances'] if u['kind'] in ('dialogue','narration'))
            high = int(1.6 * target * 3.5) - prior
            low = max(15, int(.3 * target * 3.5) - prior + 4)
            if high < low:
                raise ValueError('EPISODE_DURATION_OUT_OF_RANGE')
            desired = min(high, max(low, round(target * 3.5 - prior)))
            state['scenes'] = state['scenes'][:-1]
            state['_spoken_budget_override'] = (low, desired, high)
            from ..llm.usage_context import usage_scope
            with usage_scope(attempt_kind='targeted_duration_repair'):
                replacement = self.scene(state, len(state['scenes']))
            state['scenes'].append(replacement)
            repaired = [replacement]
        delivery = self._delivery(state)
        return {'delivery': delivery, 'scene_updates': repaired} if repaired else delivery

    def _delivery(self, state):
        outline = state['outline']
        chars = [CharacterSnapshot.model_validate(c) for c in state['characters']]
        expected = {c.role_id for c in chars}
        if {p['role_id'] for p in outline['character_portrayals']} != expected:
            raise ValueError('OUTLINE_CAST_MISMATCH')
        scenes = [SceneDelivery.model_validate(s['scene']) for s in state['scenes']]
        count = sum(len(u.text) for s in scenes for u in s.utterances if u.kind in ('dialogue', 'narration'))
        estimate = round(count / 3.5)
        if not .3 * outline['duration_sec'] <= estimate <= 1.6 * outline['duration_sec']:
            raise ValueError('EPISODE_DURATION_OUT_OF_RANGE')
        episode = EpisodeDelivery(episode_id=state['episode_id'], index=state['episode_number'],
            title=outline['title'], duration_target_sec=outline['duration_sec'], duration_estimate_sec=estimate,
            scenes=scenes, episode_summary='；'.join(f for s in state['scenes'] for f in s['continuity']['facts']),
            validation_status='PASSED', ready_for_playback=True)
        old = state.get('source_delivery')
        episodes = [EpisodeDelivery.model_validate(e) for e in (old['episodes'] if old else [])] + [episode]
        plan = PlanContent(title=outline['title'], premise=outline['premise'], theme=state['creation']['feeling'],
            beginning=outline['scenes'][0]['goal'], development='；'.join(s['goal'] for s in outline['scenes']),
            climax=outline['scenes'][-1]['goal'], ending=outline['episode_summaries'][state['episode_number'] - 1],
            episode_outlines=[EpisodeOutline(index=episode.index, title=episode.title, core_goal=outline['premise'],
                major_beats=[b for s in outline['scenes'] for b in s['beats']], ending=outline['scenes'][-1]['goal'],
                target_duration_sec=outline['duration_sec'])],
            character_portrayals=outline['character_portrayals'])
        delivery = StoryDelivery(story_id=state['story_id'], story_version_id=uuid4().hex,
            version_no=state['version_no'], parent_story_version_id=state.get('parent_story_version_id'),
            lineage_type='continue' if old else ('revise' if state.get('parent_story_version_id') else 'create'),
            series_id=state['series_id'] if state['creation']['form'] == 'series' else None,
            approved_plan_id=state['plan_id'], approved_plan_revision=state['plan_revision'],
            title=outline['title'], summary=outline['premise'], preview_blurb=state['scenes'][0]['preview_blurb'],
            story_mode=GENRES[state['creation']['genre']][0], character_snapshot=chars,
            character_portrayals=outline['character_portrayals'], outline=plan, episodes=episodes,
            continuity_state={'facts': [*((old or {}).get('continuity_state', {}).get('facts') or []),
                                       *(f for s in state['scenes'] for f in s['continuity']['facts'])],
                              'unresolved_threads': state['scenes'][-1]['continuity']['open_threads']},
            quality_report={'validation_status': 'FAILED'})
        report = validate_story_delivery(delivery).model_copy(update={'outline_alignment_passed': False,
            'continuity_passed': False, 'content_rating_passed': False,
            'warnings': ['LISTEN_FIRST_SEMANTIC_REVIEW_SKIPPED: 用户确认不是语义质量审核']})
        integrity = validate_delivery_integrity(delivery)
        if report.validation_status != 'PASSED' or not integrity.valid:
            raise ValueError('DELIVERY_TECHNICAL_CHECK_FAILED')
        payload = delivery.model_dump(mode='json')
        # Integrated schema includes this additive field; local compatibility remains unchanged.
        if 'generated_episode_ids' in StoryDelivery.model_fields:
            payload['generated_episode_ids'] = [episode.episode_id]
        payload.update(quality_report=report.model_dump(mode='json'), status='READY', ready_for_playback=True)
        return payload
