from __future__ import annotations

import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ..workflow.schemas import CharacterSnapshot


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


GENRES = {
    '国风奇幻': ('general', 'G10', 'R11'),
    '冒险成长': ('general', 'G12', 'R10'),
    '悬疑推理': ('mystery', 'G11', 'R6'),
    '生活治愈': ('general', 'G05', 'R5'),
}
QUICK = {'warmer': '加强温暖与理解', 'lighter': '减少沉重感，增加轻松互动',
         'tension': '加强悬念与可听线索', 'interaction': '增加人物之间自然的互动',
         'faster': '节奏更紧凑', 'suspense': '保留后续悬念', 'new_direction': '更换核心冲突与故事方向'}


class Creation(Model):
    idempotency_key: str = Field(min_length=8, max_length=128)
    form: Literal['short', 'series'] = 'short'
    method: Literal['assist', 'idea', 'continue'] = 'assist'
    idea: str = Field(default='', max_length=2000)
    genre: Literal['国风奇幻', '冒险成长', '悬疑推理', '生活治愈'] = '国风奇幻'
    feeling: Literal['warm', 'light', 'tense', 'fantastic'] = 'warm'
    ending: Literal['happy', 'open', 'cliffhanger'] = 'happy'
    art_style: Literal['watercolor', 'guofeng', 'animation'] = 'guofeng'
    series_episodes: int = Field(default=6, ge=2, le=24)
    character_ids: list[str] = Field(min_length=1, max_length=6)
    source_session_id: str | None = None
    output: Literal['audio', 'script', 'h5'] = 'audio'
    casting: dict | None = None

    @model_validator(mode='after')
    def required(self):
        if self.method == 'idea' and not self.idea.strip():
            raise ValueError('IDEA_REQUIRED')
        if self.method == 'continue' and not self.source_session_id:
            raise ValueError('SOURCE_REQUIRED')
        if self.source_session_id and self.method != 'continue':
            raise ValueError('SOURCE_ONLY_FOR_CONTINUE')
        if len(set(self.character_ids)) != len(self.character_ids):
            raise ValueError('DUPLICATE_CHARACTERS')
        return self


class Command(Model):
    command_id: str = Field(min_length=8, max_length=128)
    expected_revision: int = Field(ge=1)
    kind: Literal['select_direction', 'revise_outline', 'confirm_outline', 'change', 'confirm_change',
                  'confirm_script', 'next_episode', 'cancel', 'retry_background', 'retry']
    target_id: str | None = None
    fingerprint: str | None = None
    option_id: str | None = None
    text: str = Field(default='', max_length=2000)
    scope: Literal['scene', 'following'] = 'following'


class Direction(Model):
    title: str = Field(min_length=1)
    premise: str = Field(min_length=1)


class Directions(Model):
    directions: list[Direction] = Field(min_length=3, max_length=3)


class SceneCard(Model):
    title: str = Field(min_length=1)
    location: str = Field(min_length=1)
    time_of_day: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    atmosphere: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    beats: list[str] = Field(min_length=1)
    background_prompt: str = Field(min_length=1)
    must_include: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    choices: list[Direction] = Field(default_factory=list, max_length=3)


class Outline(Model):
    title: str = Field(min_length=1)
    premise: str = Field(min_length=1)
    relationships: list[str]
    series_arc: str = ''
    episode_summaries: list[str] = Field(min_length=1, max_length=24)
    duration_sec: Literal[90, 120, 150, 180, 300]
    scenes: list[SceneCard] = Field(min_length=2, max_length=6)


class BackgroundSpec(Model):
    scene_key: str
    revision: int
    plan_id: str
    generation_epoch: int
    location: str
    time_of_day: str
    environment: str
    atmosphere: str
    must_include: list[str]
    must_avoid: list[str]
    art_style: str
    composition: str = '环境建立镜头，前景留出角色叠加空间'
    prompt: str
    negative_prompt: str = '人物，主角，文字，字幕，水印，标志'
    aspect_ratio: Literal['16:9'] = '16:9'
    parameters: dict = Field(default_factory=lambda: {'width': 1536, 'height': 864})


def options(images=False):
    return {'version': 'story-options/1', 'enabled': True, 'images_enabled': images,
            'genres': list(GENRES), 'forms': ['short', 'series'], 'methods': ['assist', 'idea', 'continue'],
            'feelings': ['warm', 'light', 'tense', 'fantastic'], 'endings': ['happy', 'open', 'cliffhanger'],
            'art_styles': ['guofeng', 'watercolor', 'animation'], 'quick_changes': QUICK,
            'defaults': {'form': 'short', 'series_episodes': 6, 'feeling': 'warm', 'ending': 'happy', 'art_style': 'guofeng'},
            'streaming': 'sse', 'background_parallelism': 2}
