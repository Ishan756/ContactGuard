from typing import Any

from pydantic import BaseModel, Field


class EvaluationBenchmarkSummary(BaseModel):
    name: str | None = None
    description: str | None = None
    contracts: int = 0
    policies: int = 0
    ground_truth_findings: int = 0


class EvaluationAgentSummary(BaseModel):
    model: str | None = None
    mode: str | None = None
    findings: dict[str, Any] = Field(default_factory=dict)
    clause_extraction: dict[str, Any] = Field(default_factory=dict)


class EvaluationSummaryResponse(BaseModel):
    available: bool
    reason: str | None = None
    schema_version: str | None = None
    dataset_version: str | None = None
    dataset_sha256: str | None = None
    prompt_version: str | None = None
    model_config_version: str | None = None
    generated_at: str | None = None
    git_commit: str | None = None
    mode: str | None = None
    benchmark: EvaluationBenchmarkSummary = Field(
        default_factory=EvaluationBenchmarkSummary
    )
    agents: dict[str, EvaluationAgentSummary] = Field(default_factory=dict)
    delta: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    notice: str | None = None
