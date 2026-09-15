"""Phase 5: PostgresStoryTemplateRepository。

复用 Phase 4.1 persistence 体系（SQLAlchemy, Session）。
与 MemoryStoryTemplateRepository 实现相同 Protocol。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import StoryTemplateSpec
from .repository import StoryTemplateRepository


class PostgresStoryTemplateRepository:
    """PostgreSQL 实现的模板仓库。

    使用 Phase 4 的 SQLAlchemy Session（与 character_templates 同实例）。
    物理 PG 不可用时，使用 MemoryStoryTemplateRepository。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, template_id: str, version: int | None = None) -> StoryTemplateSpec | None:
        if version is not None:
            stmt = (
                select(StoryTemplateSpec)
                .where(
                    StoryTemplateSpec.template_id == template_id,
                    StoryTemplateSpec.version == version,
                )
            )
        else:
            # 最新 active version
            stmt = (
                select(StoryTemplateSpec)
                .where(StoryTemplateSpec.template_id == template_id)
                .order_by(StoryTemplateSpec.version.desc())
                .limit(1)
            )
        return self._session.execute(stmt).scalars().first()

    def create(self, spec: StoryTemplateSpec) -> StoryTemplateSpec:
        existing = self.get(spec.template_id, spec.version)
        if existing:
            raise ValueError(
                f"模板 {spec.template_id} v{spec.version} 已存在。"
                f"请增加 version 或删除旧版。"
            )
        self._session.add(spec)
        self._session.flush()
        return spec

    def list(self, mode: str | None = None) -> list[StoryTemplateSpec]:
        stmt = select(StoryTemplateSpec).order_by(
            StoryTemplateSpec.template_id,
            StoryTemplateSpec.version.desc(),
        )
        results = self._session.execute(stmt).scalars().all()
        if mode:
            results = [t for t in results if mode in (t.supported_modes or [])]
        return list(results)


def build_postgres_template_repo(session: Session) -> PostgresStoryTemplateRepository:
    """工厂：构建 PostgresStoryTemplateRepository。"""
    return PostgresStoryTemplateRepository(session)