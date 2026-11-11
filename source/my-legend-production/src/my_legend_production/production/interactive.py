"""Opt-in session API and worker integration; existing production flows stay unchanged."""
import os
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine
import psycopg
from fastapi import Request
from psycopg.types.json import Jsonb

from drama_engine.interactive.store import Store
from drama_engine.interactive.service import Service, Worker
from drama_engine.interactive.generator import Generator
from drama_engine.interactive.streaming import StreamingProvider
from drama_engine.interactive.backgrounds import OpenAIImageAdapter, BackgroundWorker
from drama_engine.interactive.api import register_routes
from drama_engine.workflow.schemas import StoryDelivery
from drama_engine.service.downstream import rendering_manifest
from .contracts import ProductionRequest
from .settings import ProductionSettings
from .story import StoryClient
from .repository import ProductionError


def session_service(repository):
    # Same PostgreSQL namespace as the production repository; no second credential source.
    engine = create_engine('postgresql+psycopg://', creator=lambda: psycopg.connect(repository.dsn,
        options='-c search_path=' + repository.schema + ',pg_catalog'), pool_pre_ping=True)
    return Service(Store(engine), images_enabled=all(os.environ.get(k) for k in
        ('STORY_IMAGE_BASE_URL', 'STORY_IMAGE_API_KEY', 'STORY_IMAGE_MODEL')))


def register(app, repository, artifacts, owner):
    from fastapi import HTTPException
    enabled = os.environ.get('MY_LEGEND_INTERACTIVE_STORIES') == '1'
    if not enabled:
        @app.get('/api/v1/story-options')
        def disabled(request: Request):
            owner(request)
            return {'code': 0, 'message': 'ok', 'data': {'enabled': False}}
        return
    service = session_service(repository)
    # Schema is installed by the explicit migration/worker setup command, never by reads.
    app.state.story_sessions = service
    client = StoryClient(ProductionSettings.environment().story_url, os.environ['MY_LEGEND_STORY_TOKEN'])

    def resolve(principal, ids):
        values = []
        for cid in ids:
            try:
                view = client.call('GET', '/v1/characters/' + __import__('urllib.parse', fromlist=['quote']).quote(cid, safe=''))
            except ProductionError:
                raise HTTPException(409, 'CHARACTERS_NOT_AVAILABLE') from None
            voice = view.get('assets', {}).get('voice', {})
            values.append(dict(character_id=cid, role_id=cid,
                performer_id=voice.get('performer_id') or 'performer-' + cid,
                canon_revision=view['version'], profile_revision=0,
                canon=view['canon'], profile={**view['runtime_defaults'], 'asset_refs': view.get('assets', {})}))
        return values
    def validate(value):
        if value.output == 'h5':
            from .flows import FlowCasting, freeze_casting
            if not value.casting or not set(value.casting.get('bindings', {})) <= set(value.character_ids):
                raise HTTPException(409, 'DIRECTING_CASTING_INVALID')
            try:
                frozen = freeze_casting(FlowCasting.model_validate(value.casting))
            except (ValueError, ProductionError):
                raise HTTPException(409, 'DIRECTING_CASTING_INVALID') from None
            # Freeze catalog references, not paths or user-supplied generated images.
            value = value.model_copy(update={'casting': frozen})
        return value
    register_routes(app, service, owner, resolve, artifacts.root.parent / 'story-backgrounds', validate)


def media_submit(repository, artifacts):
    def submit(state, key):
        version = state['confirmed_version']
        if not version or state['delivery']['story_version_id'] != version:
            raise ValueError('SCRIPT_CONFIRMATION_REQUIRED')
        delivery = StoryDelivery.model_validate(state['delivery'])
        refs = [artifacts.put_json('StoryDelivery', version, state['delivery']),
                artifacts.put_json('RenderManifest', version, rendering_manifest(delivery).model_dump(mode='json'))]
        # Explicitly register confirmed sources for the production ownership check.
        with repository.transaction() as db:
            for ref in refs:
                db.execute('''INSERT INTO interactive_story_sources(owner_id,session_id,story_version_id,kind,sha256,metadata)
                    VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                    (state['owner'], state['id'], version, ref.kind, ref.sha256, Jsonb(ref.model_dump())))
        request = ProductionRequest.model_validate(dict(idempotency_key=key, work_id=state['story_id'],
            source=dict(kind='delivery', source_version_id=version, delivery=refs[0].model_dump(), manifest=refs[1].model_dump()),
            outputs=['audio'], mode='automatic', review_policy='listen_first',
            sound_workflow='sound_bridge/1', audio_delivery_policy='audio_first'))
        from .flows import FlowService
        flow = FlowService(repository, artifacts)
        body = dict(title=delivery.title, duration=delivery.episodes[-1].duration_target_sec,
                    sound=request.model_dump(mode='json'), kind='create', output=state['creation']['output'], stage_mode='basic_stage/1')
        fid = flow.insert(state['owner'], key, {'session_id': state['id'], 'version': version}, body,
                          state['creation'].get('casting') or {}, state['story_id'])
        return {'flow_id': fid, 'story_version_id': version, 'path': '/pages/flow/index?id=' + fid}
    return submit


def workers(repository, artifacts):
    from drama_engine.llm.openai_compat import build_provider_from_env
    service = session_service(repository)
    def factory():
        provider = build_provider_from_env()
        if provider.name == 'mock':
            raise ValueError('REAL_MODEL_REQUIRED')
        stream = StreamingProvider(provider, lambda *args: None,
            enabled=os.environ.get('STORY_INTERACTIVE_STREAMING') == '1')
        return Generator(stream)
    image = OpenAIImageAdapter(os.environ['STORY_IMAGE_BASE_URL'], os.environ['STORY_IMAGE_API_KEY'],
        os.environ['STORY_IMAGE_MODEL']) if service.images_enabled else None
    return service, Worker(service, factory, media_submit(repository, artifacts)), BackgroundWorker(
        service, image, artifacts.root.parent / 'story-backgrounds')
