"""Framework-agnostic application service for story planning and delivery."""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import TypeAdapter

from .adapters import PlanGenerator, StoryExecutor
from .performance import validate_story_delivery
from .repository import WorkflowConflictError, WorkflowNotFoundError
from .schemas import (
    AudienceBand,
    CharacterSnapshot,
    CreateStoryRequest,
    GenerationJob,
    OperationContext,
    PlanPreview,
    PlanStatus,
    ResolvedSourceReference,
    StoryIntent,
    StoryModeChoice,
    StoryOperationRequest,
    StoryVersionStatus,
    WorkflowJobStatus,
    plan_fingerprint,
    utcnow,
)

_REQUEST_ADAPTER = TypeAdapter(StoryOperationRequest)
_CANON_LOCKED_FIELDS = {
    "character_id", "name", "appearance", "gender", "species",
    "character_type", "hardware_identity", "device_type", "immutable_facts",
}


class StoryWorkflowService:
    def __init__(self, repository, plan_generator: PlanGenerator, story_executor: StoryExecutor):
        self.repository = repository
        self.plan_generator = plan_generator
        self.story_executor = story_executor

    def prepare_story_plan(
        self, request: StoryOperationRequest | dict[str, Any],
        operation_context: OperationContext | None = None,
    ) -> PlanPreview:
        request = request if hasattr(request, "intent") else _REQUEST_ADAPTER.validate_python(request)
        if request.intent == StoryIntent.CONTINUE and request.continuation_kind == "resume_playback":
            raise WorkflowConflictError("PLAYBACK_RESUME_NOT_A_GENERATION_OPERATION")
        context = operation_context or OperationContext()
        source = None
        if request.intent != StoryIntent.CREATE:
            source = self.repository.resolve_source(request.source_selector, context.principal_id)
        characters = self._resolve_characters(request, context)
        impact_analysis = self._analyze_impact(request, source)
        explicit_fields = sorted(request.creation_preferences.model_fields_set)
        preferences, auto_fields = self._resolve_preferences(request)
        request = request.model_copy(update={"creation_preferences": preferences})
        content = self.plan_generator.generate(request, source, characters)
        self._validate_plan_shape(content, preferences)
        plan_id = uuid.uuid4().hex
        payload = {
            "plan": content.model_dump(mode="json"),
            "preferences": preferences.model_dump(mode="json"),
            "characters": [item.model_dump(mode="json") for item in characters],
            "source": source.model_dump(mode="json") if source else None,
            "impact_analysis": impact_analysis,
        }
        preview = PlanPreview(
            plan_id=plan_id,
            plan_revision=1,
            status=PlanStatus.AWAITING_APPROVAL,
            intent=request.intent,
            source_reference=source,
            plan=content,
            resolved_preferences=preferences,
            character_snapshots=characters,
            character_profile_revision_map={item.character_id: item.profile_revision for item in characters},
            auto_filled_fields=auto_fields,
            impact_analysis=impact_analysis,
            explicit_fields=explicit_fields,
            plan_fingerprint=plan_fingerprint(payload),
        )
        return self.repository.create_plan(request, context, preview)

    def revise_story_plan(self, plan_id: str, expected_revision: int, feedback: str) -> PlanPreview:
        if not feedback.strip():
            raise ValueError("feedback is required")
        current = self.repository.get_plan(plan_id)
        raw_request = self.repository.get_plan_request(plan_id)
        if current is None or raw_request is None:
            raise WorkflowNotFoundError(plan_id)
        if current.status != PlanStatus.AWAITING_APPROVAL or current.plan_revision != expected_revision:
            raise WorkflowConflictError("STALE_PLAN")
        request = _REQUEST_ADAPTER.validate_python(raw_request)
        content = self.plan_generator.generate(
            request, current.source_reference, current.character_snapshots,
            previous=current.plan, feedback=feedback,
        )
        self._validate_plan_shape(content, current.resolved_preferences)
        payload = {
            "plan": content.model_dump(mode="json"),
            "preferences": current.resolved_preferences.model_dump(mode="json"),
            "characters": [item.model_dump(mode="json") for item in current.character_snapshots],
            "source": current.source_reference.model_dump(mode="json") if current.source_reference else None,
            "impact_analysis": current.impact_analysis,
        }
        revised = current.model_copy(update={
            "plan_revision": expected_revision + 1,
            "plan": content,
            "plan_fingerprint": plan_fingerprint(payload),
            "updated_at": utcnow(),
        })
        return self.repository.save_revision(revised, feedback)

    def approve_story_plan(
        self, plan_id: str, expected_revision: int,
        fingerprint: str, idempotency_key: str,
    ) -> GenerationJob:
        plan = self.repository.get_plan(plan_id)
        if plan is None:
            raise WorkflowNotFoundError(plan_id)
        return self.repository.approve_and_create_job(
            plan_id, expected_revision, fingerprint, idempotency_key
        )

    def generate_from_approved_plan(self, job_id: str):
        job = self.repository.get_job(job_id)
        if job is None:
            raise WorkflowNotFoundError(job_id)
        if job.status == WorkflowJobStatus.SUCCEEDED and job.result_story_version_id:
            return self.repository.get_story_version(job.result_story_version_id)
        if job.status != WorkflowJobStatus.QUEUED:
            raise WorkflowConflictError(f"JOB_NOT_RUNNABLE: {job.status}")
        running = job.model_copy(update={
            "status": WorkflowJobStatus.RUNNING, "stage": "generation", "progress_pct": 10,
        })
        self.repository.save_job(running)
        try:
            delivery = self.story_executor.execute(job.input_snapshot)
            validating = running.model_copy(update={
                "status": WorkflowJobStatus.VALIDATING, "stage": "validating", "progress_pct": 90,
            })
            self.repository.save_job(validating)
            report = validate_story_delivery(delivery)
            executor_report = delivery.quality_report
            report = report.model_copy(update={
                "outline_alignment_passed": executor_report.outline_alignment_passed,
                "continuity_passed": executor_report.continuity_passed,
                "warnings": [*report.warnings, *executor_report.warnings],
            })
            approved = job.input_snapshot.preview
            episode_ready = (
                len(delivery.episodes) == approved.resolved_preferences.target_episodes
                and all(ep.ready_for_playback and ep.validation_status == "PASSED" for ep in delivery.episodes)
                and [ep.index for ep in delivery.episodes] == list(range(1, len(delivery.episodes) + 1))
                and all(ep.duration_target_sec == approved.resolved_preferences.target_duration_sec for ep in delivery.episodes)
            )
            snapshot_match = (
                delivery.approved_plan_id == approved.plan_id
                and delivery.approved_plan_revision == approved.plan_revision
                and delivery.outline == approved.plan
                and delivery.story_mode == approved.resolved_preferences.story_mode
                and delivery.content_form == approved.resolved_preferences.content_form
            )
            ready = (
                report.validation_status == "PASSED"
                and executor_report.validation_status == "PASSED"
                and report.outline_alignment_passed
                and report.continuity_passed
                and episode_ready and snapshot_match
            )
            delivery = delivery.model_copy(update={
                "quality_report": report,
                "ready_for_playback": ready,
                "status": StoryVersionStatus.READY if ready else StoryVersionStatus.CANDIDATE,
            })
            if not ready:
                raise ValueError("PERFORMANCE_OR_STORY_VALIDATION_FAILED")
            self.repository.save_story_version(delivery)
            succeeded = validating.model_copy(update={
                "status": WorkflowJobStatus.SUCCEEDED,
                "stage": "completed",
                "progress_pct": 100,
                "result_story_version_id": delivery.story_version_id,
            })
            self.repository.save_job(succeeded)
            return delivery
        except Exception as exc:
            failed = running.model_copy(update={
                "status": WorkflowJobStatus.FAILED,
                "stage": "failed",
                "error_code": getattr(getattr(exc, "code", None), "value", None) or "WORKFLOW_GENERATION_FAILED",
                "error_message": str(exc),
            })
            self.repository.save_job(failed)
            raise

    def get_story_plan(self, plan_id: str):
        return self.repository.get_plan(plan_id)

    def get_generation_job(self, job_id: str):
        return self.repository.get_job(job_id)

    def get_story_version(self, story_version_id: str):
        return self.repository.get_story_version(story_version_id)

    def resolve_story_reference(self, selector, operation_context: OperationContext | None = None):
        context = operation_context or OperationContext()
        return self.repository.resolve_source(selector, context.principal_id)

    def cancel_generation_job(self, job_id: str):
        job = self.repository.get_job(job_id)
        if job is None:
            raise WorkflowNotFoundError(job_id)
        if job.status == WorkflowJobStatus.QUEUED:
            updated = job.model_copy(update={"status": WorkflowJobStatus.CANCELLED, "stage": "cancelled"})
        elif job.status in (WorkflowJobStatus.RUNNING, WorkflowJobStatus.VALIDATING):
            updated = job.model_copy(update={"status": WorkflowJobStatus.CANCEL_REQUESTED})
        else:
            return job
        return self.repository.save_job(updated)

    def update_character_profile(
        self, character_id: str, expected_revision: int, patch: dict[str, Any],
        operation_context: OperationContext | None = None,
    ):
        forbidden = sorted(_CANON_LOCKED_FIELDS & set(patch))
        if forbidden:
            raise ValueError(f"CHARACTER_CANON_LOCKED: {forbidden}")
        context = operation_context or OperationContext()
        return self.repository.update_character_profile(
            context.principal_id, character_id, expected_revision, patch
        )

    def record_playback_event(self, event: dict[str, Any], operation_context=None) -> None:
        context = operation_context or OperationContext()
        payload = dict(event)
        payload.setdefault("event_id", uuid.uuid4().hex)
        payload["principal_id"] = context.principal_id
        self.repository.record_playback_event(payload)

    @staticmethod
    def _resolve_preferences(request):
        prefs = request.creation_preferences
        auto_fields = sorted(set(type(prefs).model_fields) - set(prefs.model_fields_set))
        if prefs.story_mode == StoryModeChoice.AUTO:
            genre = prefs.genre.casefold()
            resolved = "mystery" if "mystery" in genre or "悬疑" in genre or "推理" in genre else "general"
            prefs = prefs.model_copy(update={"story_mode": resolved})
            if "story_mode" not in auto_fields:
                auto_fields.append("story_mode")
        return prefs, auto_fields

    @staticmethod
    def _resolve_characters(request, context: OperationContext) -> list[CharacterSnapshot]:
        output: list[CharacterSnapshot] = []
        bindings = {
            item.get("character_id"): item
            for item in request.characters.role_bindings
            if item.get("character_id")
        }
        for character_id in request.characters.selected_character_ids:
            raw = context.character_snapshots.get(character_id)
            if raw is None:
                raise ValueError(f"CHARACTER_NOT_FOUND: {character_id}")
            canon = dict(raw.get("canon") or {})
            profile = dict(raw.get("profile") or {})
            profile.update(request.characters.temporary_profile_overrides.get(character_id, {}))
            binding = bindings.get(character_id, {})
            output.append(CharacterSnapshot(
                character_id=character_id,
                canon_revision=raw.get("canon_revision", 1),
                profile_revision=raw.get(
                    "profile_revision",
                    request.characters.character_profile_revisions.get(character_id, 1),
                ),
                canon=canon,
                profile=profile,
                role_id=binding.get("story_role_id"),
                performer_id=binding.get("performer_id"),
            ))
        return output

    @staticmethod
    def _validate_plan_shape(content, preferences) -> None:
        if len(content.episode_outlines) != preferences.target_episodes:
            raise ValueError("plan episode count does not match target_episodes")
        if any(item.target_duration_sec != preferences.target_duration_sec for item in content.episode_outlines):
            raise ValueError("plan duration does not match target_duration_sec")

    def _analyze_impact(self, request, source):
        if request.intent != StoryIntent.REVISE or source is None:
            return {}
        delivery = self.repository.get_story_version(source.story_version_id)
        if delivery is None:
            raise WorkflowNotFoundError(source.story_version_id)
        target = request.edit.target
        target_episode_id = target.get("episode_id") or source.episode_id
        indexes = [ep.index for ep in delivery.episodes]
        matched = next((ep.index for ep in delivery.episodes if ep.episode_id == target_episode_id), None)
        if request.edit.scope in ("whole_story", "arc"):
            affected = indexes
        elif request.edit.scope == "ending" and not target_episode_id:
            affected = indexes[-1:]
        elif matched is None:
            raise WorkflowConflictError("REVISION_TARGET_NOT_FOUND")
        elif request.edit.downstream_policy == "replan_affected":
            affected = [index for index in indexes if index >= matched]
        else:
            affected = [matched]
        return {
            "source_version_id": source.story_version_id,
            "scope": request.edit.scope,
            "downstream_policy": request.edit.downstream_policy,
            "affected_episode_indexes": affected,
            "requires_continuity_recheck": bool(affected),
        }
