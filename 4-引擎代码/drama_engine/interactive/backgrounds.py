"""Independent background workers; configured providers return bytes, never arbitrary file paths."""
import base64
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import hashlib
import httpx
from .store import emit, now


class OpenAIImageAdapter:
    def __init__(self, url, key, model):
        self.url, self.key, self.model = url.rstrip('/'), key, model

    def generate(self, spec):
        response = httpx.post(self.url + '/images/generations', headers={'Authorization': 'Bearer ' + self.key},
            json={'model': self.model, 'prompt': spec['prompt'] + '\n避免：' + spec['negative_prompt'],
                  'size': '1536x1024', 'response_format': 'b64_json', 'n': 1}, timeout=180,
            follow_redirects=False)
        response.raise_for_status()
        return base64.b64decode(response.json()['data'][0]['b64_json'], validate=True), self.model


def save_image(root, data):
    from PIL import Image, ImageOps
    with Image.open(BytesIO(data)) as img:
        original = list(img.size)
        if img.width * img.height > 40_000_000:
            raise ValueError('IMAGE_TOO_LARGE')
        img = ImageOps.fit(img.convert('RGB'), (1536, 864), method=Image.Resampling.LANCZOS)
        out = BytesIO()
        img.save(out, format='PNG')
    content = out.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (digest + '.png')
    if not path.exists():
        tmp = root / (uuid4().hex + '.tmp')
        tmp.write_bytes(content)
        tmp.replace(path)
    return {'sha256': digest, 'original_size': original, 'size': [1536, 864], 'media_type': 'image/png'}


class BackgroundWorker:
    def __init__(self, service, adapter, root):
        self.service, self.store, self.adapter, self.root = service, service.store, adapter, root

    def run_once(self):
        if not self.adapter:
            return False
        for snapshot in self.store.all():
            if self.service.story_only and snapshot['creation']['output'] != 'script':
                continue
            for key, bg in snapshot['backgrounds'].items():
                if bg['status'] == 'running' and bg.get('expires_at', now()) < now():
                    def expire(s):
                        target = s['backgrounds'].get(key)
                        if target and target['status'] == 'running' and target.get('expires_at', now()) < now():
                            target.update(status='failed', error_code='BACKGROUND_RESULT_UNKNOWN')
                            for call in s.get('background_calls', []):
                                if call['call_id'] == target.get('token') and call['status'] == 'inflight':
                                    call['status'] = 'unknown'
                            emit(s, 'background.failed', {'scene_key': key, 'code': 'BACKGROUND_RESULT_UNKNOWN'})
                    self.store.mutate(snapshot['id'], snapshot['owner'], expire)
                    continue
                if bg['status'] != 'queued' or snapshot['stage'] == 'cancelled':
                    continue
                token = uuid4().hex
                def claim(s):
                    current = s['backgrounds'].get(key)
                    running = sum(b['status'] == 'running' for b in s['backgrounds'].values())
                    if s['stage'] == 'cancelled' or not current or current['status'] != 'queued' or running >= 2:
                        return False
                    current.update(status='running', token=token, epoch=s['generation_epoch'],
                        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
                    emit(s, 'background.started', {'scene_key': key})
                    return True
                state, claimed = self.store.mutate(snapshot['id'], snapshot['owner'], claim)
                if not claimed:
                    continue
                current = state['backgrounds'][key]
                # Cache only known successful owned artifacts.
                cached = next((b['image'] for s in self.store.all() if s['owner'] == state['owner']
                    for b in s['backgrounds'].values() if b['hash'] == current['hash'] and b['status'] == 'ready'), None)
                try:
                    if cached:
                        image = cached
                    else:
                        def reserve(s):
                            target = s['backgrounds'].get(key)
                            if not target or target.get('token') != token or target['status'] != 'running' or s['stage'] == 'cancelled':
                                raise ValueError('IMAGE_EXECUTION_FENCED')
                            s.setdefault('background_calls', []).append({'call_id': token, 'scene_key': key,
                                'spec_hash': current['hash'], 'status': 'inflight', 'started_at': now(),
                                'usage_source': 'unavailable'})
                        self.store.mutate(state['id'], state['owner'], reserve)
                        data, model = self.adapter.generate(current['spec'])
                        image = {**save_image(self.root, data), 'model': model, 'provider': type(self.adapter).__name__}
                    error = None
                except Exception:
                    image, error = None, 'BACKGROUND_GENERATION_FAILED'
                def finish(s):
                    for call in s.get('background_calls', []):
                        if call['call_id'] == token:
                            call.update(status='unknown' if error else 'success', completed_at=now(),
                                image_sha256=image['sha256'] if image else None)
                    target = s['backgrounds'].get(key)
                    if not target or target.get('token') != token or target['status'] != 'running':
                        return
                    if target['epoch'] != s['generation_epoch'] or s['stage'] == 'cancelled':
                        target['status'] = 'stale'
                        emit(s, 'background.stale', {'scene_key': key})
                        return
                    target['status'] = 'failed' if error else 'ready'
                    target['image'], target['error_code'] = image, error
                    emit(s, 'background.failed' if error else 'background.ready', {'scene_key': key, 'background': target})
                self.store.mutate(state['id'], state['owner'], finish)
                return True
        return False
