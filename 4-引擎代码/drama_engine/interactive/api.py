"""Optional business-facing routes. Reads never dispatch work or start providers."""
import asyncio
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, FileResponse
from .models import Creation, Command, options
from .store import Conflict, public


def register_routes(app, service, owner, resolve_characters, image_root, validate_creation=None):
    router = APIRouter(prefix='/api/v1')

    def invoke(fn):
        try:
            return fn()
        except KeyError:
            raise HTTPException(404, 'SESSION_NOT_FOUND') from None
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None

    def envelope(data):
        return {'code': 0, 'message': 'ok', 'data': data}

    @router.get('/story-options')
    def get_options(request: Request):
        owner(request)
        value = options(service.images_enabled)
        value['outputs'] = ['script'] if service.story_only else ['script', 'audio', 'h5']
        value['story_only'] = service.story_only
        return envelope(value)

    @router.post('/story-sessions', status_code=202)
    def create(value: Creation, request: Request):
        principal = owner(request)
        if validate_creation:
            value = validate_creation(value)
        return envelope(invoke(lambda: service.create(principal, value, resolve_characters(principal, value.character_ids))))

    @router.get('/story-sessions')
    def listing(request: Request):
        principal = owner(request)
        values = service.store.list_owned(principal)
        return envelope({'items': [{'id': s['id'], 'title': (s['outline'] or {}).get('title', '构思中的故事'),
            'stage': s['stage'], 'creation': s['creation'], 'episode_number': s['episode_number'],
            'can_continue': bool(s['confirmed_version'] and s['creation']['form'] == 'series'
                                 and s['episode_number'] < s['creation']['series_episodes'])} for s in values[:100]
                                 if not service.story_only or s['creation']['output'] == 'script']})

    @router.get('/story-sessions/{sid}')
    def get(sid: str, request: Request):
        return envelope(invoke(lambda: public(service.store.get(sid, owner(request)))))

    @router.post('/story-sessions/{sid}/commands', status_code=202)
    def command(sid: str, value: Command, request: Request):
        return envelope(invoke(lambda: service.command(sid, owner(request), value)))

    @router.get('/story-sessions/{sid}/events')
    async def events(sid: str, request: Request, after: int = Query(default=0, ge=0), poll: bool = False):
        principal = owner(request)
        state = invoke(lambda: service.store.get(sid, principal))
        header = request.headers.get('last-event-id')
        if header:
            try:
                after = max(after, int(header))
            except ValueError:
                raise HTTPException(400, 'INVALID_EVENT_CURSOR') from None
        if after > state['last_seq']:
            raise HTTPException(409, 'EVENT_CURSOR_AHEAD')
        if poll:
            batch = [e for e in state['events'] if e['seq'] > after][:200]
            return envelope({'events': batch, 'last_seq': batch[-1]['seq'] if batch else after})
        async def stream():
            cursor = after
            for _ in range(50):  # bounded connection; client reconnects with last committed sequence
                if await request.is_disconnected():
                    break
                current = await asyncio.to_thread(service.store.get, sid, principal)
                for event in current['events']:
                    if event['seq'] > cursor:
                        yield 'id: ' + str(event['seq']) + '\ndata: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
                        cursor = event['seq']
                yield ': heartbeat\n\n'
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type='text/event-stream',
            headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

    @router.get('/story-sessions/{sid}/backgrounds/{key}/image')
    def image(sid: str, key: str, request: Request):
        state = invoke(lambda: service.store.get(sid, owner(request)))
        bg = state['backgrounds'].get(key)
        if not bg or bg['status'] != 'ready':
            raise HTTPException(404, 'BACKGROUND_NOT_READY')
        digest = bg['image']['sha256']
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise HTTPException(404, 'BACKGROUND_NOT_READY')
        path = Path(image_root) / (digest + '.png')
        if not path.is_file():
            raise HTTPException(404, 'BACKGROUND_NOT_READY')
        return FileResponse(path, media_type='image/png', filename=key + '.png', headers={'Cache-Control': 'private, no-store'})

    @router.get('/story-sessions/{sid}/export')
    def export(sid: str, request: Request):
        state = invoke(lambda: service.store.get(sid, owner(request)))
        return envelope({'session_id': sid, 'revision': state['revision'],
            'story_version_id': (state['delivery'] or {}).get('story_version_id'),
            'confirmed': bool(state['confirmed_version'] and not state['pending_change']
                and state['stage'] in ('confirmed', 'media_pending', 'media_ready')
                and state['confirmed_version'] == (state['delivery'] or {}).get('story_version_id')),
            'content_fingerprint': state.get('script_fingerprint'),
            'delivery': state['delivery'], 'backgrounds': state['backgrounds'],
            'version_history': state.get('version_history', [])})

    app.include_router(router)
