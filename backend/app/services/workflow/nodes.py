import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppException, ValidationError
from app.core.logging import get_logger
from app.db.models import (
    ReviewDecision,
    ReviewDecisionType,
    RiskFinding,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowRun,
    WorkflowStatus,
)
from app.schemas.risk import RetryTarget, ReviewStatus
from app.services.clause.service import ClauseExtractionService
from app.services.risk.analysis import RiskAnalysisService
from app.services.risk.retrieval import PolicyRetrievalService
from app.services.risk.validation import EvidenceValidationService, retry_target_for_finding
from app.services.workflow.state import WorkflowState

logger = get_logger("contractguard.workflow.nodes")


@dataclass
class WorkflowDependencies:
    clause_extraction: ClauseExtractionService
    policy_retrieval: PolicyRetrievalService
    risk_analysis: RiskAnalysisService
    evidence_validation: EvidenceValidationService
    session_factory: async_sessionmaker[AsyncSession]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _error_payload(exc: Exception) -> dict[str, Any]:
    code = exc.code if isinstance(exc, AppException) else "WORKFLOW_NODE_FAILED"
    message = exc.message if isinstance(exc, AppException) else str(exc)
    return {
        "code": code,
        "message": message[:1000],
        "exception_type": type(exc).__name__,
    }


def _compact_finding(finding: RiskFinding) -> dict[str, Any]:
    return {
        "finding_id": finding.id,
        "finding_type": finding.finding_type,
        "risk_category": finding.risk_category,
        "severity": finding.severity,
        "rule_id": finding.rule_id,
        "validation_status": finding.validation_status,
        "review_status": finding.review_status,
        "validation_attempts": finding.validation_attempts or 0,
        "validation_error_categories": _parse_json_list(
            finding.validation_error_categories
        ),
        "last_validated_at": (
            finding.last_validated_at.isoformat()
            if finding.last_validated_at is not None
            else None
        ),
        "explanation": finding.explanation,
        "suggested_question": finding.suggested_question,
    }


async def _update_run(
    deps: WorkflowDependencies,
    workflow_id: str,
    *,
    event_type: str,
    node: str | None = None,
    actor_id: str | None = None,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    **fields: Any,
) -> None:
    async with deps.session_factory() as db:
        run = await db.get(WorkflowRun, workflow_id)
        if run is None:
            return
        status_from = run.status
        for name, value in fields.items():
            setattr(run, name, value)
        status_to = run.status
        db.add(
            WorkflowEvent(
                workflow_run_id=workflow_id,
                event_type=event_type,
                node=node,
                actor_id=actor_id,
                status_from=status_from,
                status_to=status_to,
                message=message,
                payload=json.dumps(payload, default=str) if payload else None,
            )
        )
        await db.commit()


def make_node(
    name: str,
    fn: Callable[[WorkflowState], Awaitable[dict[str, Any]]],
    deps: WorkflowDependencies,
) -> Callable[[WorkflowState], Awaitable[dict[str, Any]]]:
    async def wrapped(state: WorkflowState) -> dict[str, Any]:
        step = int(state.get("step_count", 0)) + 1
        max_steps = int(state.get("max_steps", 30))
        workflow_id = state["workflow_id"]
        try:
            if name != "fail_workflow" and step > max_steps:
                raise ValidationError(
                    f"Workflow exceeded the maximum graph step limit ({max_steps})."
                )
            await _update_run(
                deps,
                workflow_id,
                event_type=WorkflowEventType.NODE_STARTED,
                node=name,
                current_node=name,
                step_count=step,
                status=WorkflowStatus.RUNNING,
            )
            updates = await fn(state)
            updates.setdefault("step_count", step)
            errors = updates.get("errors") or []
            if errors:
                first = errors[0]
                await _update_run(
                    deps,
                    workflow_id,
                    event_type=WorkflowEventType.FAILED,
                    node=name,
                    message=first.get("message"),
                    payload=first,
                    status=WorkflowStatus.FAILED,
                    current_node=name,
                    step_count=step,
                    error_code=first.get("code"),
                    error_message=first.get("message"),
                )
            else:
                await _update_run(
                    deps,
                    workflow_id,
                    event_type=WorkflowEventType.NODE_COMPLETED,
                    node=name,
                    current_node=name,
                    step_count=step,
                )
            return updates
        except GraphInterrupt:
            raise
        except Exception as exc:
            error = _error_payload(exc)
            logger.warning("Workflow %s node %s failed: %s", workflow_id, name, exc)
            await _update_run(
                deps,
                workflow_id,
                event_type=WorkflowEventType.FAILED,
                node=name,
                message=error["message"],
                payload=error,
                status=WorkflowStatus.FAILED,
                current_node=name,
                step_count=step,
                error_code=error["code"],
                error_message=error["message"],
            )
            return {
                "errors": [error],
                "failed_node": name,
                "workflow_status": WorkflowStatus.FAILED.value,
                "step_count": step,
            }

    wrapped.__name__ = f"node_{name}"
    return wrapped


async def extract_clauses(
    state: WorkflowState, deps: WorkflowDependencies
) -> dict[str, Any]:
    async with deps.session_factory() as db:
        run, clauses = await deps.clause_extraction.extract_clauses(
            document_id=state["document_id"], db=db
        )
    if not clauses:
        raise ValidationError("Clause extraction completed without any validated clauses.")
    return {
        "clause_extraction_run_id": run.id,
        "clauses": [
            {
                "clause_id": clause.id,
                "category": clause.category,
                "page_number": clause.page_number,
                "validation_status": clause.validation_status,
            }
            for clause in clauses
        ],
        "warnings": _parse_json_list(run.warnings),
    }


async def retrieve_policies(
    state: WorkflowState, deps: WorkflowDependencies
) -> dict[str, Any]:
    async with deps.session_factory() as db:
        run, results = await deps.policy_retrieval.retrieve(
            document_id=state["document_id"], db=db
        )
    evidence: list[dict[str, Any]] = []
    for result in results:
        for item in result.evidence:
            evidence.append(
                {
                    "clause_id": result.clause.id,
                    "chunk_id": item.chunk_id,
                    "policy_id": item.policy_id,
                    "source_identifier": item.source_identifier,
                    "policy_version": item.policy_version,
                    "page_number": item.page_number,
                    "similarity_score": item.similarity_score,
                    "coverage_status": result.coverage_status.value,
                }
            )
    return {
        "policy_retrieval_run_id": run.id,
        "retrieved_evidence": evidence,
        "retrieval_missing_coverage_count": run.missing_coverage_count,
        "warnings": _parse_json_list(run.warnings),
    }


async def analyze_risk(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    async with deps.session_factory() as db:
        run, findings = await deps.risk_analysis.analyze(
            document_id=state["document_id"],
            db=db,
            retrieval_run_id=state.get("policy_retrieval_run_id"),
            enable_model_analysis=state.get("enable_model_analysis"),
        )
    return {
        "risk_analysis_run_id": run.id,
        "findings": [_compact_finding(finding) for finding in findings],
        "warnings": _parse_json_list(run.warnings),
    }


async def validate_evidence(
    state: WorkflowState, deps: WorkflowDependencies
) -> dict[str, Any]:
    analysis_run_id = state.get("risk_analysis_run_id")
    if not analysis_run_id:
        raise ValidationError("Risk analysis did not produce a run before validation.")
    async with deps.session_factory() as db:
        run, findings, _attempts = await deps.evidence_validation.validate_findings(
            document_id=state["document_id"],
            db=db,
            analysis_run_id=analysis_run_id,
            max_retries=0,
            enable_retries=False,
        )
    retry_target = RetryTarget.NONE
    for finding in findings:
        target = retry_target_for_finding(finding)
        if target == RetryTarget.ANALYSIS:
            retry_target = RetryTarget.ANALYSIS
            break
        if target == RetryTarget.RETRIEVAL:
            retry_target = RetryTarget.RETRIEVAL
    missing_evidence = bool(
        run.missing_evidence_count or state.get("retrieval_missing_coverage_count")
    )
    return {
        "validation_run_id": run.id,
        "findings": [_compact_finding(finding) for finding in findings],
        "validation": {
            "status": run.status,
            "findings_validated": run.findings_validated,
            "verified_count": run.verified_count,
            "unverified_count": run.unverified_count,
            "needs_review_count": run.needs_review_count,
            "missing_evidence_count": run.missing_evidence_count,
            "inconclusive_count": run.inconclusive_count,
            "max_retries": run.max_retries,
            "warnings": _parse_json_list(run.warnings),
        },
        "retry_target": retry_target.value,
        "missing_evidence": missing_evidence,
        "warnings": _parse_json_list(run.warnings),
    }


def build_review_request(state: WorkflowState) -> dict[str, Any]:
    return {
        "workflow_id": state["workflow_id"],
        "document_id": state["document_id"],
        "interrupt": "human_review",
        "allowed_decisions": [
            ReviewDecisionType.APPROVE.value,
            ReviewDecisionType.DISMISS.value,
            ReviewDecisionType.REQUEST_REVISION.value,
        ],
        "instructions": (
            "Review the automatically verified findings. Approval acknowledges a human "
            "review only; it does not execute legal or contractual actions."
        ),
        "findings": state.get("findings", []),
        "validation": state.get("validation", {}),
        "warnings": state.get("warnings", []),
    }


def build_review_report(state: WorkflowState) -> dict[str, Any]:
    validation = state.get("validation", {})
    findings = state.get("findings", [])
    if not findings:
        report_status = "no_findings"
    elif validation.get("unverified_count") or validation.get("missing_evidence_count"):
        report_status = "needs_human_review_with_validation_gaps"
    else:
        report_status = "ready_for_human_review"
    return {
        "workflow_id": state["workflow_id"],
        "document_id": state["document_id"],
        "generated_at": _now_iso(),
        "status": report_status,
        "summary": {
            "clauses_extracted": len(state.get("clauses", [])),
            "policy_evidence_retrieved": len(state.get("retrieved_evidence", [])),
            "findings": len(findings),
            "verified": validation.get("verified_count", 0),
            "unverified": validation.get("unverified_count", 0),
            "missing_evidence": validation.get("missing_evidence_count", 0),
            "inconclusive": validation.get("inconclusive_count", 0),
            "automatic_retries": state.get("retry_count", 0),
            "human_revisions": state.get("revision_count", 0),
        },
        "validation": validation,
        "findings": findings,
        "warnings": state.get("warnings", []),
        "human_review": None,
        "legal_action_performed": False,
        "notice": (
            "Decision-support output only. No legal or contractual action is executed."
        ),
    }


async def prepare_retry(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    retry_count = int(state.get("retry_count", 0)) + 1
    target = state.get("retry_target", RetryTarget.ANALYSIS.value)
    await _update_run(
        deps,
        state["workflow_id"],
        event_type=WorkflowEventType.RESUMED,
        node="prepare_retry",
        message="Automatic validation correction retry requested.",
        payload={"retry_count": retry_count, "target": target},
        retry_count=retry_count,
    )
    return {
        "retry_count": retry_count,
        "workflow_status": WorkflowStatus.RUNNING.value,
        "errors": [],
        "failed_node": None,
    }


async def review_report(state: WorkflowState, _deps: WorkflowDependencies) -> dict[str, Any]:
    report = build_review_report(state)
    review_required = bool(state.get("findings"))
    request = build_review_request(state) if review_required else None
    return {
        "review_report": report,
        "review_request": request,
        "review_required": review_required,
        "workflow_status": (
            WorkflowStatus.AWAITING_REVIEW.value
            if review_required
            else WorkflowStatus.COMPLETED.value
        ),
    }


async def human_review(state: WorkflowState, _deps: WorkflowDependencies) -> dict[str, Any]:
    request = state.get("review_request") or build_review_request(state)
    decision = interrupt(request)
    if not isinstance(decision, dict):
        raise ValidationError("Human review resume payload must be an object.")
    return {"review_decision": decision}


async def persist_review_decision(
    state: WorkflowState, deps: WorkflowDependencies
) -> dict[str, Any]:
    decision = state.get("review_decision") or {}
    decision_type = str(decision.get("decision", ""))
    if decision_type not in {
        ReviewDecisionType.APPROVE.value,
        ReviewDecisionType.DISMISS.value,
        ReviewDecisionType.REQUEST_REVISION.value,
    }:
        raise ValidationError("A valid human review decision is required.")
    idempotency_key = decision.get("idempotency_key")
    workflow_id = state["workflow_id"]
    analysis_run_id = state.get("risk_analysis_run_id")

    async with deps.session_factory() as db:
        existing = None
        if idempotency_key:
            existing = (
                await db.execute(
                    select(ReviewDecision).where(
                        ReviewDecision.workflow_run_id == workflow_id,
                        ReviewDecision.idempotency_key == idempotency_key,
                    )
                )
            ).scalar_one_or_none()
        if existing is None:
            current_findings = list(
                (
                    await db.execute(
                        select(RiskFinding).where(
                            RiskFinding.document_id == state["document_id"],
                            RiskFinding.analysis_run_id == analysis_run_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            available_ids = {finding.id for finding in current_findings}
            requested_ids = decision.get("finding_ids")
            target_ids = (
                sorted(set(requested_ids)) if requested_ids else sorted(available_ids)
            )
            unknown = set(target_ids) - available_ids
            if unknown:
                raise ValidationError(
                    "Review decision references findings outside the current analysis run.",
                    details={"unknown_finding_ids": sorted(unknown)},
                )
            existing = ReviewDecision(
                workflow_run_id=workflow_id,
                reviewer_id=str(decision.get("reviewer_id") or state["owner_reviewer_id"]),
                decision=decision_type,
                finding_ids=json.dumps(target_ids),
                notes=decision.get("notes"),
                revision_instructions=decision.get("revision_instructions"),
                revision_target=decision.get("revision_target"),
                idempotency_key=idempotency_key,
            )
            db.add(existing)
            if decision_type == ReviewDecisionType.APPROVE.value:
                for finding in current_findings:
                    if finding.id in target_ids:
                        finding.review_status = ReviewStatus.REVIEWED.value
            elif decision_type == ReviewDecisionType.DISMISS.value:
                for finding in current_findings:
                    if finding.id in target_ids:
                        finding.review_status = ReviewStatus.DISMISSED.value
            run = await db.get(WorkflowRun, workflow_id)
            if run is not None:
                run.revision_count = int(state.get("revision_count", run.revision_count))
            db.add(
                WorkflowEvent(
                    workflow_run_id=workflow_id,
                    event_type=WorkflowEventType.REVIEW_DECISION,
                    node="persist_review_decision",
                    actor_id=existing.reviewer_id,
                    message=f"Reviewer decision: {decision_type}",
                    payload=json.dumps(
                        {
                            "decision": decision_type,
                            "finding_ids": target_ids,
                            "notes": decision.get("notes"),
                            "revision_instructions": decision.get("revision_instructions"),
                        }
                    ),
                )
            )
            await db.commit()
        decision = {**decision, "decision_id": existing.id}
    return {"review_decision": decision}


async def prepare_revision(
    state: WorkflowState, deps: WorkflowDependencies
) -> dict[str, Any]:
    decision = state.get("review_decision") or {}
    revision_count = int(state.get("revision_count", 0)) + 1
    target = str(decision.get("revision_target") or RetryTarget.ANALYSIS.value)
    await _update_run(
        deps,
        state["workflow_id"],
        event_type=WorkflowEventType.RESUMED,
        node="prepare_revision",
        actor_id=decision.get("reviewer_id"),
        message="Reviewer requested a revision.",
        payload={"revision_count": revision_count, "target": target},
        status=WorkflowStatus.REVISING,
        revision_count=revision_count,
        interrupted_node=None,
        review_request=None,
    )
    return {
        "revision_count": revision_count,
        "retry_target": target,
        "review_decision": decision,
        "review_request": None,
        "review_report": None,
        "workflow_status": WorkflowStatus.REVISING.value,
        "errors": [],
        "failed_node": None,
    }


async def finalize_workflow(
    state: WorkflowState, deps: WorkflowDependencies
) -> dict[str, Any]:
    decision = state.get("review_decision") or {}
    report = dict(state.get("review_report") or build_review_report(state))
    if decision:
        report["human_review"] = {
            "decision": decision.get("decision"),
            "reviewer_id": decision.get("reviewer_id"),
            "decision_id": decision.get("decision_id"),
            "notes": decision.get("notes"),
            "decided_at": decision.get("decided_at") or _now_iso(),
            "automatic_verification_separate": True,
        }
        report["status"] = "human_reviewed"
    else:
        report["human_review"] = None
        report["status"] = "completed_no_findings"
    report["legal_action_performed"] = False
    await _update_run(
        deps,
        state["workflow_id"],
        event_type=WorkflowEventType.COMPLETED,
        node="finalize_workflow",
        actor_id=decision.get("reviewer_id"),
        message="Workflow completed after human review.",
        payload={"decision": decision.get("decision")},
        status=WorkflowStatus.COMPLETED,
        current_node="finalize_workflow",
        interrupted_node=None,
        review_request=None,
        review_report=json.dumps(report, default=str),
        completed_at=datetime.now(UTC),
    )
    return {
        "review_report": report,
        "review_request": None,
        "workflow_status": WorkflowStatus.COMPLETED.value,
    }


async def fail_workflow(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    errors = state.get("errors") or []
    first = errors[0] if errors else {}
    report = {
        "workflow_id": state["workflow_id"],
        "document_id": state["document_id"],
        "generated_at": _now_iso(),
        "status": "failed",
        "failed_node": state.get("failed_node"),
        "errors": errors,
        "legal_action_performed": False,
        "notice": "Workflow failed safely; no legal or contractual action was executed.",
    }
    await _update_run(
        deps,
        state["workflow_id"],
        event_type=WorkflowEventType.FAILED,
        node="fail_workflow",
        message=first.get("message"),
        payload=first,
        status=WorkflowStatus.FAILED,
        current_node="fail_workflow",
        error_code=first.get("code"),
        error_message=first.get("message"),
        review_report=json.dumps(report, default=str),
        completed_at=datetime.now(UTC),
        interrupted_node=None,
    )
    return {
        "workflow_status": WorkflowStatus.FAILED.value,
        "review_report": report,
        "review_request": None,
        "errors": errors,
        "failed_node": state.get("failed_node"),
    }
