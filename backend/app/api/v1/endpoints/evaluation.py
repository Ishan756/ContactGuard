import json
from pathlib import Path

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.evaluation import (
    EvaluationAgentSummary,
    EvaluationBenchmarkSummary,
    EvaluationSummaryResponse,
)

router = APIRouter(prefix="/evaluation", tags=["Evaluation Benchmark"])

REPO_ROOT = Path(__file__).resolve().parents[5]


def resolve_report_path(settings: Settings) -> Path:
    if settings.evaluation_report_path:
        return Path(settings.evaluation_report_path).expanduser().resolve()
    return REPO_ROOT / "evaluation/reports/latest.json"


def _unavailable(reason: str) -> EvaluationSummaryResponse:
    return EvaluationSummaryResponse(available=False, reason=reason)


@router.get(
    "/summary",
    response_model=EvaluationSummaryResponse,
    summary="Latest versioned evaluation benchmark summary",
    description=(
        "Returns the most recent reproducible benchmark report comparing the single-LLM "
        "baseline with the multi-agent workflow. Results measure agreement with synthetic "
        "annotations, not legal correctness."
    ),
)
async def get_evaluation_summary(
    settings: Settings = Depends(get_settings),
) -> EvaluationSummaryResponse:
    path = resolve_report_path(settings)
    if not path.exists():
        return _unavailable(
            "No evaluation report has been generated yet. Run the benchmark CLI to create one."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _unavailable(f"Evaluation report could not be read: {type(exc).__name__}.")
    if not isinstance(payload, dict):
        return _unavailable("Evaluation report is malformed.")

    agents = payload.get("agents")
    agent_summaries: dict[str, EvaluationAgentSummary] = {}
    if isinstance(agents, dict):
        for name, agent in agents.items():
            if not isinstance(agent, dict):
                continue
            agent_summaries[str(name)] = EvaluationAgentSummary(
                model=str(agent["model"]) if agent.get("model") else None,
                mode=str(agent["mode"]) if agent.get("mode") else None,
                findings=agent.get("findings") if isinstance(agent.get("findings"), dict) else {},
                clause_extraction=(
                    agent.get("clause_extraction")
                    if isinstance(agent.get("clause_extraction"), dict)
                    else {}
                ),
            )

    benchmark = payload.get("benchmark")
    return EvaluationSummaryResponse(
        available=True,
        schema_version=payload.get("schema_version"),
        dataset_version=payload.get("dataset_version"),
        dataset_sha256=payload.get("dataset_sha256"),
        prompt_version=payload.get("prompt_version"),
        model_config_version=payload.get("model_config_version"),
        generated_at=payload.get("generated_at"),
        git_commit=payload.get("git_commit"),
        mode=payload.get("mode"),
        benchmark=(
            EvaluationBenchmarkSummary.model_validate(benchmark)
            if isinstance(benchmark, dict)
            else EvaluationBenchmarkSummary()
        ),
        agents=agent_summaries,
        delta=payload.get("delta") if isinstance(payload.get("delta"), dict) else {},
        limitations=[
            str(item) for item in payload.get("limitations", []) if isinstance(item, str)
        ],
        notice=str(payload["notice"]) if payload.get("notice") else None,
    )
