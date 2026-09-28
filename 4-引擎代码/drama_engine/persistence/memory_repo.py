"""Phase 6.5: In-memory repository for persistence roundtrip testing.

Provides create() + get_by_story_id() with the same interface as
the Postgres repository, enabling true save+reload tests without a DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .repository import StoryRecord


@dataclass
class InMemoryRecordRepo:
    """In-memory StoryRecord repository for testing."""

    _store: dict[str, StoryRecord] = field(default_factory=dict)

    def create(self, record: StoryRecord) -> StoryRecord:
        self._store[record.story_id] = record
        return record

    def get_by_story_id(self, story_id: str) -> StoryRecord | None:
        return self._store.get(story_id)

    def list_all(self) -> list[StoryRecord]:
        return list(self._store.values())