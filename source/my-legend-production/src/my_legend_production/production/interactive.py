"""Opt-in session API and worker integration; existing production flows stay unchanged."""
import os
from pathlib import Path
from sqlalchemy import create_engine
import psycopg
from fastapi import Request

from drama_engine.interactive.store import Store
from drama_engine.interactive.service import Service, Worker
from drama_engine.interactive.generator import Generator
from drama_engine.interactive.streaming import StreamingProvider
from drama_engine.interactive.backgrounds import OpenAIImageAdapter, BackgroundWorker
from drama_engine.interactive.api import register_routes
from .settings import ProductionSettings
from .story import StoryClient
from .repository import ProductionError


def session_service(repository):
    # Same PostgreSQL namespace as the production repository; no second credential source.
    engine = create_engine('postgresql+psycopg://', creator=lambda: psycopg.connect(repository.dsn,
        options='-c search_path=' + repository.schema + ',pg_catalog'), pool_pre_ping=True)
    return Service(Store(engine), images_enabled=all(os.environ.get(k) for k in
        ('STORY_IMAGE_BASE_URL', 'STORY_IMAGE_API_KEY', 'STORY_IMAGE_MODEL')), story_only=True)


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
    register_routes(app, service, owner, resolve, artifacts.root.parent / 'story-backgrounds')


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
    return service, Worker(service, factory), BackgroundWorker(
        service, image, artifacts.root.parent / 'story-backgrounds')
