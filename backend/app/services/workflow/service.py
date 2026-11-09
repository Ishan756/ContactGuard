import json
import uuid
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.security import ReviewerPrincipal
from app.db.models import (
    Document,
    DocumentStatus,
    ReviewDecision,
    ReviewDecisionType,
    RiskFinding,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowRun,
    WorkflowStatus,
)
from app.schemas.risk import RetryTarget
from app.schemas.workflow import WorkflowResumeRequest, WorkflowStartRequest
from app.services.workflow.graph import build_workflow_graph
from app.services.workflow.nodes import WorkflowDependencies

logger = get_logger("contractguard.workflow.service")


def _now() -> datetime:
    return datetime.now(UTC)


def _state_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in state.items() if not key.startswith("__")}


class WorkflowService:
    """Durable orchestration and human-review service around the compiled graph."""

    def __init__(
        self,
        *,
        dependencies: WorkflowDependencies,
        checkpointer: BaseCheckpointSaver,
        settings: Settings,
    ) -> None:
        self.deps = dependencies
        self.settings = settings
        self.graph = build_workflow_graph(
            checkpointer=checkpointer,
            deps=dependencies,
            settings=settings,
        )

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self.deps.session_factory

    async def _load_owned(
        self, workflow_id: str, principal: ReviewerPrincipal
    ) -> WorkflowRun:
        async with self.session_factory() as db:
            run = (
                await db.execute(
                    select(WorkflowRun)
                    .options(
                        selectinload(WorkflowRun.events),
                        selectinload(WorkflowRun.decisions),
                    )
                    .where(WorkflowRun.id == workflow_id)
                )
            ).scalar_one_or_none()
            if run is None:
                raise NotFoundError(f"Workflow '{workflow_id}' not found.")
            if run.owner_reviewer_id != principal.reviewer_id:
                raise ForbiddenError("You are not authorized to access this workflow.")
            return run

    async def _apply_result(
        self, workflow_id: str, result: dict[str, Any]
    ) -> None:
        interrupts = result.get("__interrupt__") or []
        state = _state_snapshot(result)
        now = _now()
        async with self.session_factory() as db:
            run = await db.get(WorkflowRun, workflow_id)
            if run is None:
                return
            run.step_count = int(state.get("step_count", run.step_count))
            run.retry_count = int(state.get("retry_count", run.retry_count))
            run.revision_count = int(state.get("revision_count", run.revision_count))
            if state.get("clause_extraction_run_id"):
                run.clause_extraction_run_id = state["clause_extraction_run_id"]
            if state.get("policy_retrieval_run_id"):
                run.policy_retrieval_run_id = state["policy_retrieval_run_id"]
            if state.get("risk_analysis_run_id"):
                run.risk_analysis_run_id = state["risk_analysis_run_id"]
            if state.get("validation_run_id"):
                run.validation_run_id = state["validation_run_id"]
            run.state_snapshot = json.dumps(state, default=str)
            report = state.get("review_report")
            if report:
                run.review_report = json.dumps(report, default=str)

            if interrupts:
                request = interrupts[0].value if interrupts else None
                run.status = WorkflowStatus.AWAITING_REVIEW.value
                run.current_node = "human_review"
                run.interrupted_node = "human_review"
                run.review_requested_at = now
                run.completed_at = None
                run.review_request = json.dumps(request or {}, default=str)
                db.add(
                    WorkflowEvent(
                        workflow_run_id=workflow_id,
                        event_type=WorkflowEventType.INTERRUPTED,
                        node="human_review",
                        status_from=WorkflowStatus.RUNNING.value,
                        status_to=WorkflowStatus.AWAITING_REVIEW.value,
                        message="Workflow paused for human review.",
                    )
                )
            else:
                final_status = str(
                    state.get("workflow_status") or run.status or WorkflowStatus.COMPLETED
                )
                if final_status == WorkflowStatus.FAILED.value:
                    run.status = WorkflowStatus.FAILED.value
                    run.error_code = state.get("error_code")
                    errors = state.get("errors") or []
                    if errors:
                        run.error_code = errors[0].get("code")
                        run.error_message = errors[0].get("message")
                    run.completed_at = now
                    db.add(
                        WorkflowEvent(
                            workflow_run_id=workflow_id,
                            event_type=WorkflowEventType.FAILED,
                            node=run.current_node,
                            status_to=WorkflowStatus.FAILED.value,
                            message=run.error_message,
                        )
                    )
                else:
                    run.status = WorkflowStatus.COMPLETED.value
                    run.current_node = "finalize_workflow"
                    run.interrupted_node = None
                    run.review_request = None
                    run.completed_at = now
                    db.add(
                        WorkflowEvent(
                            workflow_run_id=workflow_id,
                            event_type=WorkflowEventType.COMPLETED,
                            node="finalize_workflow",
                            status_to=WorkflowStatus.COMPLETED.value,
                            message="Workflow completed.",
                        )
                    )
            await db.commit()

    async def _fail_invocation(
        self, workflow_id: str, exc: Exception
    ) -> None:
        logger.exception("Workflow %s invocation failed", workflow_id)
        async with self.session_factory() as db:
            run = await db.get(WorkflowRun, workflow_id)
            if run is None:
                return
            message = str(exc)[:1000]
            run.status = WorkflowStatus.FAILED.value
            run.error_code = "WORKFLOW_INVOCATION_FAILED"
            run.error_message = message
            run.completed_at = _now()
            db.add(
                WorkflowEvent(
                    workflow_run_id=workflow_id,
                    event_type=WorkflowEventType.FAILED,
                    node=run.current_node,
                    status_to=WorkflowStatus.FAILED.value,
                    message=message,
                )
            )
            await db.commit()

    async def start_workflow(
        self,
        request: WorkflowStartRequest,
        principal: ReviewerPrincipal,
        *,
        idempotency_key: str | None = None,
    ) -> WorkflowRun:
        async with self.session_factory() as db:
            existing = None
            if idempotency_key:
                existing = (
                    await db.execute(
                        select(WorkflowRun).where(
                            WorkflowRun.owner_reviewer_id == principal.reviewer_id,
                            WorkflowRun.idempotency_key == idempotency_key,
                        )
                    )
                ).scalar_one_or_none()
            if existing is not None:
                if existing.document_id != request.document_id:
                    raise ConflictError(
                        "Idempotency key was already used for a different document."
                    )
                return await self._load_owned(existing.id, principal)

            document = await db.get(Document, request.document_id)
            if document is None:
                raise NotFoundError(
                    f"Document with ID '{request.document_id}' not found."
                )
            if document.status != DocumentStatus.COMPLETED:
                raise ValidationError(
                    f"Document '{request.document_id}' is in status '{document.status}' "
                    "and cannot start a review workflow."
                )

            workflow_id = str(uuid.uuid4())
            max_retries = (
                request.max_retries
                if request.max_retries is not None
                else self.settings.workflow_max_retries
            )
            max_steps = (
                request.max_steps
                if request.max_steps is not None
                else self.settings.workflow_max_steps
            )
            run = WorkflowRun(
                id=workflow_id,
                thread_id=workflow_id,
                document_id=request.document_id,
                owner_reviewer_id=principal.reviewer_id,
                idempotency_key=idempotency_key,
                status=WorkflowStatus.PENDING.value,
                max_retries=max_retries,
                max_steps=max_steps,
                models_enabled=(
                    self.settings.risk_analysis_enable_model
                    if request.enable_model_analysis is None
                    else request.enable_model_analysis
                ),
            )
            db.add(run)
            db.add(
                WorkflowEvent(
                    workflow_run_id=workflow_id,
                    event_type=WorkflowEventType.STARTED,
                    actor_id=principal.reviewer_id,
                    status_to=WorkflowStatus.PENDING.value,
                    message="Workflow created.",
                )
            )
            await db.commit()
            run_id = run.id
            max_retries_value = run.max_retries
            max_steps_value = run.max_steps
            models_enabled = run.models_enabled

        initial_state: dict[str, Any] = {
            "workflow_id": run_id,
            "thread_id": run_id,
            "document_id": request.document_id,
            "owner_reviewer_id": principal.reviewer_id,
            "workflow_status": WorkflowStatus.RUNNING.value,
            "step_count": 0,
            "retry_count": 0,
            "revision_count": 0,
            "max_retries": max_retries_value,
            "max_steps": max_steps_value,
            "enable_model_analysis": models_enabled,
            "clause_extraction_run_id": None,
            "policy_retrieval_run_id": None,
            "risk_analysis_run_id": None,
            "validation_run_id": None,
            "clauses": [],
            "retrieved_evidence": [],
            "findings": [],
            "validation": {},
            "retrieval_missing_coverage_count": 0,
            "retry_target": RetryTarget.NONE.value,
            "missing_evidence": False,
            "review_required": False,
            "errors": [],
            "warnings": [],
            "failed_node": None,
            "review_request": None,
            "review_report": None,
            "review_decision": None,
            "run_metadata": {
                "created_at": _now().isoformat(),
                "owner_reviewer_id": principal.reviewer_id,
                "llm_provider": self.deps.risk_analysis.llm.provider_name,
                "llm_model": self.deps.risk_analysis.llm.model_name,
                "embedding_model": self.deps.policy_retrieval.embedding_provider.model_name,
            },
        }
        config = self._config(run_id, max_steps_value)
        async with self.session_factory() as db:
            run = await db.get(WorkflowRun, run_id)
            if run is not None:
                run.status = WorkflowStatus.RUNNING.value
                run.started_at = _now()
                db.add(
                    WorkflowEvent(
                        workflow_run_id=run_id,
                        event_type=WorkflowEventType.STARTED,
                        actor_id=principal.reviewer_id,
                        status_from=WorkflowStatus.PENDING.value,
                        status_to=WorkflowStatus.RUNNING.value,
                        message="Workflow graph started.",
                    )
                )
                await db.commit()
        try:
            result = await self.graph.ainvoke(initial_state, config)
            await self._apply_result(run_id, result)
        except Exception as exc:
            await self._fail_invocation(run_id, exc)
        return await self._load_owned(run_id, principal)

    async def get_workflow(
        self, workflow_id: str, principal: ReviewerPrincipal
    ) -> WorkflowRun:
        return await self._load_owned(workflow_id, principal)

    async def list_workflows(
        self,
        principal: ReviewerPrincipal,
        *,
        document_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[WorkflowRun], int]:
        async with self.session_factory() as db:
            filters = [WorkflowRun.owner_reviewer_id == principal.reviewer_id]
            if document_id:
                filters.append(WorkflowRun.document_id == document_id)
            total = (
                await db.execute(
                    select(func.count(WorkflowRun.id)).where(*filters)
                )
            ).scalar() or 0
            runs = list(
                (
                    await db.execute(
                        select(WorkflowRun)
                        .options(
                            selectinload(WorkflowRun.events),
                            selectinload(WorkflowRun.decisions),
                        )
                        .where(*filters)
                        .order_by(WorkflowRun.created_at.desc())
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return runs, total

    async def get_results(
        self, workflow_id: str, principal: ReviewerPrincipal
    ) -> tuple[WorkflowRun, list[RiskFinding], dict[str, Any] | None]:
        run = await self._load_owned(workflow_id, principal)
        async with self.session_factory() as db:
            findings: list[RiskFinding] = []
            if run.risk_analysis_run_id:
                findings = list(
                    (
                        await db.execute(
                            select(RiskFinding)
                            .where(
                                RiskFinding.analysis_run_id == run.risk_analysis_run_id
                            )
                            .order_by(RiskFinding.created_at, RiskFinding.id)
                        )
                    )
                    .scalars()
                    .all()
                )
        report = None
        if run.review_report:
            try:
                report = json.loads(run.review_report)
            except (TypeError, json.JSONDecodeError):
                report = None
        return run, findings, report

    async def _validate_resume(
        self,
        run: WorkflowRun,
        request: WorkflowResumeRequest,
        principal: ReviewerPrincipal,
    ) -> None:
        if run.status != WorkflowStatus.AWAITING_REVIEW.value:
            raise ConflictError(
                f"Workflow '{run.id}' is in status '{run.status}' and cannot be resumed."
            )
        if request.decision == ReviewDecisionType.REQUEST_REVISION:
            if not (request.revision_instructions or request.notes):
                raise ValidationError(
                    "A revision request requires revision_instructions or notes."
                )
            if request.revision_target == RetryTarget.NONE:
                raise ValidationError(
                    "A revision request must target analysis or retrieval."
                )
            if run.revision_count >= self.settings.workflow_max_revisions:
                raise ValidationError(
                    "The maximum number of human revision cycles has been reached."
                )
        if request.finding_ids:
            async with self.session_factory() as db:
                current_ids = set(
                    (
                        await db.execute(
                            select(RiskFinding.id).where(
                                RiskFinding.analysis_run_id == run.risk_analysis_run_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            unknown = set(request.finding_ids) - current_ids
            if unknown:
                raise ValidationError(
                    "One or more finding IDs do not belong to the current analysis run.",
                    details={"unknown_finding_ids": sorted(unknown)},
                )

    async def resume_workflow(
        self,
        workflow_id: str,
        request: WorkflowResumeRequest,
        principal: ReviewerPrincipal,
        *,
        idempotency_key: str | None = None,
    ) -> WorkflowRun:
        run = await self._load_owned(workflow_id, principal)
        command_key = idempotency_key or request.command_id
        if command_key:
            async with self.session_factory() as db:
                existing = (
                    await db.execute(
                        select(ReviewDecision).where(
                            ReviewDecision.workflow_run_id == workflow_id,
                            ReviewDecision.idempotency_key == command_key,
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return await self._load_owned(workflow_id, principal)

        await self._validate_resume(run, request, principal)
        decision = {
            "decision": request.decision.value,
            "reviewer_id": principal.reviewer_id,
            "finding_ids": request.finding_ids,
            "notes": request.notes,
            "revision_instructions": request.revision_instructions,
            "revision_target": request.revision_target.value,
            "idempotency_key": command_key,
            "decided_at": _now().isoformat(),
        }
        async with self.session_factory() as db:
            current = await db.get(WorkflowRun, workflow_id)
            if current is not None:
                current.status = WorkflowStatus.RUNNING.value
                current.completed_at = None
                db.add(
                    WorkflowEvent(
                        workflow_run_id=workflow_id,
                        event_type=WorkflowEventType.RESUMED,
                        node="human_review",
                        actor_id=principal.reviewer_id,
                        status_from=WorkflowStatus.AWAITING_REVIEW.value,
                        status_to=WorkflowStatus.RUNNING.value,
                        message=f"Reviewer resumed workflow with decision '{request.decision.value}'.",
                        payload=json.dumps(
                            {
                                "decision": request.decision.value,
                                "finding_ids": request.finding_ids,
                            }
                        ),
                    )
                )
                await db.commit()
        config = self._config(workflow_id, run.max_steps)
        try:
            result = await self.graph.ainvoke(Command(resume=decision), config)
            await self._apply_result(workflow_id, result)
        except Exception as exc:
            await self._fail_invocation(workflow_id, exc)
        return await self._load_owned(workflow_id, principal)

    def _config(self, thread_id: str, max_steps: int) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": max_steps + 10,
        }
