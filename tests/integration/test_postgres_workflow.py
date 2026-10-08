"""PostgreSQL 16 transaction and restart contract for the approved-plan workflow."""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from drama_engine.persistence.models import Base
from drama_engine.workflow.repository import SqlAlchemyWorkflowRepository, WorkflowConflictError
from drama_engine.workflow.schemas import EpisodeOutline, PlanContent
from drama_engine.workflow.service import StoryWorkflowService


class PlanGenerator:
    def generate(self, request, source, characters, previous=None, feedback=""):
        return PlanContent(
            title="数据库验收", premise=request.user_instruction, theme="选择",
            beginning="开场", development="冲突", climax="选择", ending="收束",
            episode_outlines=[EpisodeOutline(
                index=1, title="第一集", core_goal="完成选择",
                major_beats=["问题", "行动", "结果"], ending="结束",
                target_duration_sec=request.creation_preferences.target_duration_sec,
            )],
        )


class NeverExecute:
    def execute(self, snapshot):
        raise AssertionError("repository integration test must not generate a story")


@pytest.fixture
def pg_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    schema = "storyworkflow_test_" + uuid.uuid4().hex[:12]
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        if not schema.startswith("storyworkflow_test_"):
            raise RuntimeError("unsafe test schema name")
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.postgres
def test_postgres_approval_is_atomic_idempotent_and_survives_restart(pg_engine):
    request_id = uuid.uuid4().hex
    request = {
        "intent": "create", "request_id": request_id,
        "idempotency_key": request_id, "user_instruction": "一场真实数据库验收故事",
    }
    with Session(pg_engine) as session:
        service = StoryWorkflowService(SqlAlchemyWorkflowRepository(session), PlanGenerator(), NeverExecute())
        plan = service.prepare_story_plan(request)
        session.commit()

    def approve():
        with Session(pg_engine) as session:
            service = StoryWorkflowService(SqlAlchemyWorkflowRepository(session), PlanGenerator(), NeverExecute())
            try:
                job = service.approve_story_plan(plan.plan_id, 1, plan.plan_fingerprint, "same-key")
                session.commit()
                return job.job_id
            except WorkflowConflictError as exc:
                session.rollback()
                return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: approve(), range(2)))
    with Session(pg_engine) as session:
        service = StoryWorkflowService(SqlAlchemyWorkflowRepository(session), PlanGenerator(), NeverExecute())
        jobs = [item for item in results if service.get_generation_job(item) is not None]
        assert jobs
        assert len(set(jobs)) == 1
        restored = service.get_generation_job(jobs[0])
        assert restored.approved_plan_id == plan.plan_id
        assert restored.input_snapshot.request["user_instruction"] == request["user_instruction"]
        assert service.get_story_plan(plan.plan_id).status == "APPROVED"
