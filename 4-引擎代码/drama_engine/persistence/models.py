"""Phase 4 SQLAlchemy ORM 模型。

所有表：character_templates, story_templates, story_jobs,
         story_records, generation_traces, quality_results。

JSONB 字段用于 semi-structured 数据（Canon, Runtime, Snapshot）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

# ---- constraint naming convention for Alembic ---- #
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    metadata = metadata


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex


# ============================================================================
# character_templates
# ============================================================================
class CharacterTemplateModel(Base):
    __tablename__ = "character_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(String(64), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(
        Enum("draft", "active", "archived", name="character_template_status"),
        default="active",
        nullable=False,
    )
    name = Column(String(128), nullable=False)

    # JSONB: Phase 3 CharacterCanon (semi-structured)
    canon_json = Column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=dict)
    # JSONB: CharacterRuntimeInput-compatible defaults
    runtime_defaults_json = Column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("character_id", "version", name="uq_ct_charid_version"),
    )


# ============================================================================
# story_templates
# ============================================================================
class StoryTemplateModel(Base):
    __tablename__ = "story_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(String(64), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(
        Enum("draft", "active", "archived", name="story_template_status"),
        default="active",
        nullable=False,
    )
    name = Column(String(256), nullable=False)
    genre_key = Column(String(32), nullable=True)

    supported_modes = Column(JSONB().with_variant(JSON, "sqlite"), default=list)
    supported_forms = Column(JSONB().with_variant(JSON, "sqlite"), default=list)
    tags = Column(JSONB().with_variant(JSON, "sqlite"), default=list)

    # JSONB: 模板本体（semi-structured）
    template_json = Column(JSONB().with_variant(JSON, "sqlite"), nullable=False, default=dict)

    quality_score = Column(Integer, default=0)
    usage_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_st_tid_version"),
    )


# ============================================================================
# story_jobs
# ============================================================================
class StoryJobModel(Base):
    __tablename__ = "story_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=False, index=True)
    request_id = Column(String(64), nullable=False, unique=True)

    # Phase 7: long-form linking
    run_id = Column(String(64), nullable=True, index=True)
    story_id = Column(String(64), nullable=True, index=True)

    status = Column(String(32), default="pending")
    current_stage = Column(String(64), nullable=True)

    input_json = Column(JSONB().with_variant(JSON, "sqlite"), default=dict)

    story_mode = Column(String(32), nullable=True)
    mode_version = Column(String(16), nullable=True)

    # Phase 7: additional config
    template_id = Column(String(64), nullable=True)
    content_form = Column(String(32), nullable=True)
    generation_scale = Column(String(32), nullable=True)

    # Phase 7: progress tracking
    progress_pct = Column(Integer, default=0)
    current_chapter = Column(Integer, default=0)
    total_chapters = Column(Integer, default=0)
    message = Column(Text, nullable=True)

    # Phase 7: cancellation
    cancel_requested = Column(Integer, default=0)  # 0/1 boolean

    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    deadline_at = Column(DateTime(timezone=True), nullable=True)


# ============================================================================
# story_records
# ============================================================================
class StoryRecordModel(Base):
    __tablename__ = "story_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    story_id = Column(String(64), nullable=False, index=True)
    job_id = Column(String(64), nullable=True, index=True)
    request_id = Column(String(64), nullable=False)

    story_mode = Column(String(32), nullable=True)
    mode_version = Column(String(16), nullable=True)

    title = Column(String(512), nullable=True)
    summary = Column(Text, nullable=True)

    # JSONB: 正文 + 完整输出
    content_json = Column(JSONB().with_variant(JSON, "sqlite"), default=dict)
    output_json = Column(JSONB().with_variant(JSON, "sqlite"), default=dict)

    # Phase 3/4 关键：角色快照（JSONB）
    resolved_character_snapshot = Column(JSONB().with_variant(JSON, "sqlite"), default=list)

    engine_version = Column(String(32), nullable=True)
    model_mapping_snapshot = Column(JSONB().with_variant(JSON, "sqlite"), default=dict)
    rule_versions = Column(JSONB().with_variant(JSON, "sqlite"), default=dict)
    template_ids = Column(JSONB().with_variant(JSON, "sqlite"), default=list)

    created_at = Column(DateTime(timezone=True), default=_utcnow)


# ============================================================================
# generation_traces
# ============================================================================
class GenerationTraceModel(Base):
    __tablename__ = "generation_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(64), nullable=False, index=True)
    request_id = Column(String(64), nullable=False, index=True)
    job_id = Column(String(64), nullable=True)

    node = Column(String(64), nullable=False)
    llm_role = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    model_tier = Column(String(16), nullable=True)

    attempt = Column(Integer, default=0)

    latency_ms = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)

    status = Column(String(16), default="ok")
    error_code = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow)


# ============================================================================
# quality_results
# ============================================================================
class QualityResultModel(Base):
    __tablename__ = "quality_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    story_id = Column(String(64), nullable=False, index=True)

    validator = Column(String(64), nullable=True)
    severity = Column(String(16), nullable=True)  # "error" | "warning" | "info"
    rule_id = Column(String(32), nullable=True)
    passed = Column(Integer, default=1)  # 1=pass, 0=fail

    details_json = Column(JSONB().with_variant(JSON, "sqlite"), default=dict)

    created_at = Column(DateTime(timezone=True), default=_utcnow)


# ============================================================================
# generation_checkpoints  (Phase 7)
# ============================================================================
class GenerationCheckpointModel(Base):
    __tablename__ = "generation_checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, index=True)
    story_id = Column(String(64), nullable=True)

    generation_scale = Column(String(32), default="long_form")
    stage = Column(String(64), nullable=False)

    last_completed_chapter = Column(Integer, default=0)
    next_chapter = Column(Integer, default=1)

    # JSONB: 完整的可恢复状态 (plan, context, etc.)
    state_json = Column(JSONB().with_variant(JSON, "sqlite"), default=dict)

    config_fingerprint = Column(String(64), nullable=True)
    status = Column(String(32), default="resumable")
    version = Column(String(16), default="1.0")

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("run_id", "stage", name="uq_gcp_runid_stage"),
    )