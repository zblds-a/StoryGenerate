"""SQLAlchemy storage: owner isolation, row serialization and atomic event/command writes."""
from __future__ import annotations
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Table, Column, MetaData, String, Integer, JSON, UniqueConstraint, select, update

metadata = MetaData()
sessions = Table('interactive_story_sessions', metadata,
    Column('id', String(64), primary_key=True), Column('owner', String(256), nullable=False),
    Column('create_key', String(128), nullable=False), Column('create_hash', String(64), nullable=False),
    Column('revision', Integer, nullable=False), Column('body', JSON, nullable=False),
    UniqueConstraint('owner', 'create_key'))


class Conflict(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def emit(state, kind, payload=None):
    event = dict(event_id=uuid4().hex, seq=state['last_seq'] + 1, session_id=state['id'],
                 revision=state['revision'], generation_epoch=state['generation_epoch'], type=kind,
                 occurred_at=now(), payload=payload or {})
    state['last_seq'] = event['seq']
    state['events'].append(event)
    return event


class Store:
    def __init__(self, engine):
        self.engine = engine

    def migrate(self):
        metadata.create_all(self.engine)

    @contextmanager
    def transaction(self):
        with self.engine.connect() as conn:
            if self.engine.dialect.name == 'sqlite':
                conn.exec_driver_sql('BEGIN IMMEDIATE')
            else:
                conn.begin()
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def create(self, owner, key, digest, body):
        with self.transaction() as db:
            # Serialize same-key creation even when the row does not exist yet.
            if self.engine.dialect.name == 'postgresql':
                from sqlalchemy import text
                db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': owner + ':' + key})
            row = db.execute(select(sessions).where(sessions.c.owner == owner, sessions.c.create_key == key)).mappings().first()
            if row:
                if row['create_hash'] != digest:
                    raise Conflict('IDEMPOTENCY_CONFLICT')
                return copy.deepcopy(row['body'])
            db.execute(sessions.insert().values(id=body['id'], owner=owner, create_key=key,
                       create_hash=digest, revision=body['revision'], body=body))
            return copy.deepcopy(body)

    def get(self, sid, owner):
        with self.engine.connect() as db:
            row = db.execute(select(sessions.c.body).where(sessions.c.id == sid, sessions.c.owner == owner)).first()
            if not row:
                raise KeyError('SESSION_NOT_FOUND')
            return copy.deepcopy(row[0])

    def mutate(self, sid, owner, fn):
        with self.transaction() as db:
            row = db.execute(select(sessions).where(sessions.c.id == sid, sessions.c.owner == owner).with_for_update()).mappings().first()
            if not row:
                raise KeyError('SESSION_NOT_FOUND')
            state = copy.deepcopy(row['body'])
            state['revision'] += 1
            result = fn(state)
            state['updated_at'] = now()
            db.execute(update(sessions).where(sessions.c.id == sid).values(revision=state['revision'], body=state))
            return copy.deepcopy(state), copy.deepcopy(result)

    def all(self):
        with self.engine.connect() as db:
            return [copy.deepcopy(r[0]) for r in db.execute(select(sessions.c.body))]

    def list_owned(self, owner, limit=100):
        with self.engine.connect() as db:
            rows = db.execute(select(sessions.c.body).where(sessions.c.owner == owner))
            values = [copy.deepcopy(r[0]) for r in rows]
            return sorted(values, key=lambda s: s['updated_at'], reverse=True)[:limit]


def public(state):
    from .models import fingerprint
    hidden = {'owner', 'events', 'commands', 'work', 'background_work', 'characters', 'request_hash', 'call_records', 'background_calls'}
    value = {k: copy.deepcopy(v) for k, v in state.items() if k not in hidden}
    stage = state['stage']
    actions = {'directions_ready': ['select_direction'], 'outline_ready': ['revise_outline', 'confirm_outline'],
               'writing': ['change'], 'outlining': ['change'], 'change_ready': ['change', 'confirm_change'],
               'script_ready': ['change', 'confirm_script'], 'media_ready': ['next_episode', 'change'],
               'confirmed': ['next_episode', 'change'], 'failed': ['retry']}.get(stage, [])
    if stage == 'failed':
        actions = [] if state.get('inflight_unknown') else (['retry', 'change'] if state.get('outline') else ['retry'])
    if stage == 'outline_ready' and not state.get('source_delivery') and not state.get('approved_outline'):
        actions = [*actions, 'set_preferences']
    if state['creation']['form'] != 'series' or state['episode_number'] >= state['creation']['series_episodes']:
        actions = [action for action in actions if action != 'next_episode']
    if stage not in ('cancelled', 'confirmed', 'media_ready'):
        actions = [*actions, 'cancel']
    if stage != 'cancelled' and any(b['status'] == 'failed' for b in state['backgrounds'].values()):
        actions = [*actions, 'retry_background']
    value['available_actions'] = actions
    value['pending_change_fingerprint'] = fingerprint(state['pending_change']) if state['pending_change'] else None
    value['events_url'] = f"/api/v1/story-sessions/{state['id']}/events"
    return value
