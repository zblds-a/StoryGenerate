"""Bootstrap the pre-Phase-7 core tables for a fresh installation.

Existing installations stamped at 001 or later are not replayed through this
revision. The migration is additive and leaves an existing story_jobs table
untouched.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from drama_engine.persistence.models import Base

revision = "000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    legacy_tables = [
        Base.metadata.tables[name] for name in (
            "character_templates", "story_templates", "story_records",
            "generation_traces", "quality_results",
        )
    ]
    Base.metadata.create_all(bind, tables=legacy_tables, checkfirst=True)
    if not sa.inspect(bind).has_table("story_jobs"):
        op.create_table(
            "story_jobs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("job_id", sa.String(64), nullable=False),
            sa.Column("request_id", sa.String(64), nullable=False, unique=True),
            sa.Column("status", sa.String(32), nullable=True),
            sa.Column("current_stage", sa.String(64), nullable=True),
            sa.Column("input_json", JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True),
            sa.Column("story_mode", sa.String(32), nullable=True),
            sa.Column("mode_version", sa.String(16), nullable=True),
            sa.Column("error_code", sa.String(64), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_story_jobs_job_id", "story_jobs", ["job_id"])


def downgrade() -> None:
    # Existing data may predate Alembic; do not destroy core tables on rollback.
    pass
