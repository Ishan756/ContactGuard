from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.core.config import Settings
from app.services.workflow.nodes import (
    WorkflowDependencies,
    analyze_risk,
    extract_clauses,
    fail_workflow,
    finalize_workflow,
    human_review,
    make_node,
    persist_review_decision,
    prepare_retry,
    prepare_revision,
    retrieve_policies,
    review_report,
    validate_evidence,
)
from app.services.workflow.state import WorkflowState


def _failed(state: WorkflowState) -> bool:
    return bool(state.get("errors"))


def _route_after_extract(state: WorkflowState) -> str:
    return "fail_workflow" if _failed(state) else "retrieve_policies"


def _route_after_retrieve(state: WorkflowState) -> str:
    return "fail_workflow" if _failed(state) else "analyze_risk"


def _route_after_analyze(state: WorkflowState) -> str:
    return "fail_workflow" if _failed(state) else "validate_evidence"


def _route_after_validation(state: WorkflowState) -> str:
    if _failed(state):
        return "fail_workflow"
    target = str(state.get("retry_target", "none"))
    retry_count = int(state.get("retry_count", 0))
    max_retries = int(state.get("max_retries", 0))
    if target != "none" and retry_count < max_retries:
        return "prepare_retry"
    return "review_report"


def _route_after_retry(state: WorkflowState) -> str:
    if _failed(state):
        return "fail_workflow"
    target = str(state.get("retry_target", "analysis"))
    return "retrieve_policies" if target == "retrieval" else "analyze_risk"


def _route_after_human_review(state: WorkflowState) -> str:
    return "fail_workflow" if _failed(state) else "persist_review_decision"


def _route_after_report(state: WorkflowState) -> str:
    if _failed(state):
        return "fail_workflow"
    return "human_review" if state.get("review_required") else "finalize_workflow"


def _route_after_persist(state: WorkflowState) -> str:
    if _failed(state):
        return "fail_workflow"
    decision = str((state.get("review_decision") or {}).get("decision", ""))
    if decision == "request_revision":
        return "prepare_revision"
    return "finalize_workflow"


def _route_after_prepare_revision(state: WorkflowState) -> str:
    if _failed(state):
        return "fail_workflow"
    target = str(state.get("retry_target", "analysis"))
    return "retrieve_policies" if target == "retrieval" else "analyze_risk"


def build_workflow_graph(
    *,
    checkpointer: BaseCheckpointSaver,
    deps: WorkflowDependencies,
    settings: Settings,
):
    """Compile the ContractGuard LangGraph workflow with durable checkpoints."""
    graph = StateGraph(WorkflowState)

    def node(name: str, fn: Any):
        return make_node(name, lambda state: fn(state, deps), deps)

    graph.add_node("extract_clauses", node("extract_clauses", extract_clauses))
    graph.add_node("retrieve_policies", node("retrieve_policies", retrieve_policies))
    graph.add_node("analyze_risk", node("analyze_risk", analyze_risk))
    graph.add_node("validate_evidence", node("validate_evidence", validate_evidence))
    graph.add_node("prepare_retry", node("prepare_retry", prepare_retry))
    graph.add_node("review_report", node("review_report", review_report))
    graph.add_node("human_review", node("human_review", human_review))
    graph.add_node(
        "persist_review_decision",
        node("persist_review_decision", persist_review_decision),
    )
    graph.add_node("prepare_revision", node("prepare_revision", prepare_revision))
    graph.add_node("finalize_workflow", node("finalize_workflow", finalize_workflow))
    graph.add_node("fail_workflow", node("fail_workflow", fail_workflow))

    graph.add_edge(START, "extract_clauses")

    graph.add_conditional_edges(
        "extract_clauses",
        _route_after_extract,
        {
            "fail_workflow": "fail_workflow",
            "retrieve_policies": "retrieve_policies",
        },
    )
    graph.add_conditional_edges(
        "retrieve_policies",
        _route_after_retrieve,
        {"fail_workflow": "fail_workflow", "analyze_risk": "analyze_risk"},
    )
    graph.add_conditional_edges(
        "analyze_risk",
        _route_after_analyze,
        {"fail_workflow": "fail_workflow", "validate_evidence": "validate_evidence"},
    )
    graph.add_conditional_edges(
        "validate_evidence",
        _route_after_validation,
        {
            "fail_workflow": "fail_workflow",
            "prepare_retry": "prepare_retry",
            "review_report": "review_report",
        },
    )
    graph.add_conditional_edges(
        "prepare_retry",
        _route_after_retry,
        {
            "fail_workflow": "fail_workflow",
            "retrieve_policies": "retrieve_policies",
            "analyze_risk": "analyze_risk",
        },
    )
    graph.add_conditional_edges(
        "review_report",
        _route_after_report,
        {
            "fail_workflow": "fail_workflow",
            "human_review": "human_review",
            "finalize_workflow": "finalize_workflow",
        },
    )
    graph.add_conditional_edges(
        "human_review",
        _route_after_human_review,
        {
            "fail_workflow": "fail_workflow",
            "persist_review_decision": "persist_review_decision",
        },
    )
    graph.add_conditional_edges(
        "persist_review_decision",
        _route_after_persist,
        {
            "fail_workflow": "fail_workflow",
            "prepare_revision": "prepare_revision",
            "finalize_workflow": "finalize_workflow",
        },
    )
    graph.add_conditional_edges(
        "prepare_revision",
        _route_after_prepare_revision,
        {
            "fail_workflow": "fail_workflow",
            "retrieve_policies": "retrieve_policies",
            "analyze_risk": "analyze_risk",
        },
    )
    graph.add_edge("finalize_workflow", END)
    graph.add_edge("fail_workflow", END)

    return graph.compile(
        checkpointer=checkpointer,
        name="contractguard_risk_review",
    )
