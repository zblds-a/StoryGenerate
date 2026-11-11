"""Explicit OpenAI-compatible SSE support, with no implicit paid-request replay."""
import json
import re
import time
import os
from datetime import datetime, timezone
import httpx
from ..llm.base import BaseLLMProvider, LLMResult, estimate_tokens


class StreamingProvider(BaseLLMProvider):
    def __init__(self, provider, preview, enabled=False):
        self.provider, self.preview, self.enabled = provider, preview, enabled
        provider.max_retries = 0
        self.call_history = provider.call_history
        self.max_retries = 0

    def complete(self, spec, system, user, deadline=None):
        thinking = os.environ.get('STORY_INTERACTIVE_THINKING')
        if thinking in ('enabled', 'disabled'):
            extra = dict(spec.extra)
            extra['provider_params'] = {**extra.get('provider_params', {}), 'thinking': {'type': thinking}}
            spec = spec.model_copy(update={'extra': extra})
        if not self.enabled:
            return self.provider.complete(spec, system, user, deadline)
        source = self.provider
        if not hasattr(source, '_attempt_metadata'):
            # Capability fallback is selected before sending a request.
            return source.complete(spec, system, user, deadline)
        meta = source._attempt_metadata(spec, 0, datetime.now(timezone.utc))
        payload = dict(model=spec.model, messages=[{'role': 'system', 'content': system},
            {'role': 'user', 'content': user}], temperature=spec.temperature, max_tokens=spec.max_tokens,
            stream=True, stream_options={'include_usage': True}, response_format={'type': 'json_object'})
        payload.update(spec.extra.get('provider_params', {}))
        start, raw, usage, model, request_id = time.monotonic(), '', {}, spec.model, None
        offset, finished = 0, False
        headers = {'Authorization': 'Bearer ' + source.api_key, 'Content-Type': 'application/json'}
        if source.base_url == 'https://opencode.ai/inference/go/openai/v1':
            headers.update({'User-Agent': 'my-legend-story/1.0', 'x-opencode-session': meta['call_id']})
        try:
            with httpx.stream('POST', source.base_url + '/chat/completions', headers=headers,
                              json=payload, timeout=source._timeout, follow_redirects=False) as response:
                response.raise_for_status()
                request_id = response.headers.get('x-request-id')
                for line in response.iter_lines():
                    if not line.startswith('data:'):
                        continue
                    data = line[5:].strip()
                    if data == '[DONE]':
                        finished = True
                        break
                    chunk = json.loads(data)
                    usage = chunk.get('usage') or usage
                    model = chunk.get('model', model)
                    request_id = request_id or chunk.get('id')
                    for choice in chunk.get('choices', []):
                        if choice.get('finish_reason') == 'stop':
                            finished = True
                        raw += choice.get('delta', {}).get('content') or ''
                    # Publish complete whitelisted string fields, never raw JSON or reasoning deltas.
                    while True:
                        match = re.search(r'"(title|premise|text)"\s*:\s*', raw[offset:])
                        if not match:
                            break
                        pos = offset + match.end()
                        try:
                            value, length = json.JSONDecoder().raw_decode(raw[pos:])
                        except ValueError:
                            break
                        offset = pos + length
                        if isinstance(value, str):
                            self.preview(meta['call_id'], match.group(1), value)
            if not finished or not raw.strip():
                raise ValueError('MODEL_STREAM_INCOMPLETE')
            result = LLMResult(text=raw, model=model, input_tokens=usage.get('prompt_tokens', estimate_tokens(system + user)),
                output_tokens=usage.get('completion_tokens', 0), latency_ms=int((time.monotonic() - start) * 1000))
            self.call_history.append({**meta, 'actual_model': model, 'status': 'success',
                'input_tokens': result.input_tokens, 'output_tokens': result.output_tokens,
                'cache_read_tokens': (usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0),
                'reasoning_tokens': (usage.get('completion_tokens_details') or {}).get('reasoning_tokens', 0),
                'reasoning_included_in_output': True,
                'usage_source': 'reported' if usage else 'estimated', 'provider_request_id': request_id,
                'latency_ms': result.latency_ms, 'completed_at': datetime.now(timezone.utc).isoformat()})
            return result
        except Exception:
            self.call_history.append({**meta, 'status': 'error', 'usage_source': 'unavailable',
                'error_code': 'MODEL_STREAM_FAILED', 'provider_request_id': request_id,
                'latency_ms': int((time.monotonic() - start) * 1000)})
            raise
