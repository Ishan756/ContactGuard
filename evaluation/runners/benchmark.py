"""Versioned, reproducible evaluation benchmark CLI.

Examples:
    python evaluation/runners/benchmark.py
    python evaluation/runners/benchmark.py --format both \
        --output evaluation/reports/latest.json \
        --csv-output evaluation/reports/latest.csv
    python evaluation/runners/benchmark.py --mode live
"""

import argparse
import asyncio
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = REPO_ROOT / "evaluation/benchmarks/v1/dataset.json"
DEFAULT_PROMPTS = REPO_ROOT / "evaluation/config/prompts.v1.json"
DEFAULT_MODEL_CONFIG = REPO_ROOT / "evaluation/config/model_config.v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "evaluation/reports/latest.json"
DEFAULT_CSV_OUTPUT = REPO_ROOT / "evaluation/reports/latest.csv"

sys.path.insert(0, str(REPO_ROOT))

from evaluation.metrics import (  # noqa: E402
    compute_clause_extraction_metrics,
    compute_finding_metrics,
    metric_delta,
)
from evaluation.runners.agents import (  # noqa: E402
    run_baseline,
    run_live_baseline,
    run_live_multi_agent,
    run_multi_agent,
)

LIMITATIONS = [
    "The dataset is synthetic and small; it is a regression benchmark, not a legal dataset.",
    "Metrics measure agreement with synthetic annotations, not legal correctness or enforceability.",
    "Mock mode is deterministic and intended for CI; it does not measure live model quality.",
    "Live mode is optional and depends on external model availability and credentials.",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _generated_at() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch and epoch.isdigit():
        return datetime.fromtimestamp(int(epoch), UTC).isoformat()
    return datetime.now(UTC).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return data


def _contract_maps(dataset: dict[str, Any]) -> tuple[dict[str, str], dict[str, str], dict[str, list[dict[str, Any]]]]:
    contract_texts = {
        str(item["contract_id"]): str(item.get("text", ""))
        for item in dataset.get("contracts", [])
    }
    policy_texts = {
        str(item["policy_id"]): str(item.get("text", ""))
        for item in dataset.get("policies", [])
    }
    ground_truth = {
        str(item["contract_id"]): list(item.get("ground_truth_findings", []))
        for item in dataset.get("contracts", [])
    }
    return contract_texts, policy_texts, ground_truth


def _ground_truth_list(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for contract in dataset.get("contracts", []):
        contract_id = str(contract["contract_id"])
        for finding in contract.get("ground_truth_findings", []):
            item = dict(finding)
            item["contract_id"] = contract_id
            items.append(item)
    return items


async def run_benchmark(
    dataset: dict[str, Any],
    mode: str = "mock",
    dataset_path: Path = DEFAULT_DATASET,
) -> dict[str, Any]:
    contract_texts, policy_texts, _ = _contract_maps(dataset)
    ground_truth = _ground_truth_list(dataset)

    if mode == "live":
        from app.core.config import get_settings
        from app.core.llm.factory import create_llm_provider

        provider = create_llm_provider(get_settings())
        baseline = await run_live_baseline(dataset, provider)
        multi_agent = await run_live_multi_agent(dataset, provider)
        model_names = {
            "baseline": provider.model_name,
            "multi_agent": provider.model_name,
        }
    else:
        baseline = run_baseline(dataset)
        multi_agent = run_multi_agent(dataset)
        model_names = {
            "baseline": "mock-single-llm-baseline",
            "multi_agent": "policy-rule-engine + deterministic-validator",
        }

    baseline_findings = compute_finding_metrics(
        baseline["predictions"], ground_truth, contract_texts, policy_texts
    )
    multi_agent_findings = compute_finding_metrics(
        multi_agent["predictions"], ground_truth, contract_texts, policy_texts
    )
    ground_truth_clauses = {
        str(item["contract_id"]): list(item.get("clauses", []))
        for item in dataset.get("contracts", [])
    }
    multi_agent_clauses = compute_clause_extraction_metrics(
        multi_agent["clauses"], ground_truth_clauses
    )
    baseline_clauses = compute_clause_extraction_metrics(
        baseline["clauses"], ground_truth_clauses
    )

    prompts = _load_json(DEFAULT_PROMPTS)
    model_config = _load_json(DEFAULT_MODEL_CONFIG)
    report = {
        "schema_version": "1.0.0",
        "dataset_version": dataset.get("version", "unknown"),
        "dataset_path": str(dataset_path.relative_to(REPO_ROOT)),
        "dataset_sha256": _sha256(dataset_path),
        "prompt_version": prompts.get("version", "unknown"),
        "prompt_sha256": _sha256(DEFAULT_PROMPTS),
        "model_config_version": model_config.get("version", "unknown"),
        "model_config_sha256": _sha256(DEFAULT_MODEL_CONFIG),
        "generated_at": _generated_at(),
        "git_commit": _git_commit(),
        "mode": mode,
        "benchmark": {
            "name": "single-llm-baseline-vs-multi-agent",
            "description": dataset.get("description", ""),
            "contracts": len(dataset.get("contracts", [])),
            "policies": len(dataset.get("policies", [])),
            "ground_truth_findings": len(ground_truth),
        },
        "agents": {
            "baseline": {
                "model": model_names["baseline"],
                "mode": "single_llm",
                "findings": baseline_findings,
                "clause_extraction": baseline_clauses,
                "predictions": baseline["predictions"],
            },
            "multi_agent": {
                "model": model_names["multi_agent"],
                "mode": "multi_agent",
                "findings": multi_agent_findings,
                "clause_extraction": multi_agent_clauses,
                "predictions": multi_agent["predictions"],
            },
        },
        "delta": {
            "findings": metric_delta(multi_agent_findings, baseline_findings),
            "clause_extraction_recall": round(
                float(multi_agent_clauses["recall"])
                - float(baseline_clauses["recall"]),
                4,
            ),
        },
        "limitations": LIMITATIONS,
        "notice": (
            "Benchmark results compare synthetic annotations. They do not establish legal "
            "correctness and must not be presented as legal advice."
        ),
    }
    return report


def write_json(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_csv(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for agent_name, agent in report["agents"].items():
        for metric, value in agent["findings"].items():
            if isinstance(value, (int, float)):
                rows.append(
                    {
                        "agent": agent_name,
                        "metric_group": "findings",
                        "metric": metric,
                        "value": value,
                    }
                )
        for metric, value in agent["clause_extraction"].items():
            if isinstance(value, (int, float)):
                rows.append(
                    {
                        "agent": agent_name,
                        "metric_group": "clause_extraction",
                        "metric": metric,
                        "value": value,
                    }
                )
    for metric, value in report["delta"]["findings"].items():
        rows.append(
            {
                "agent": "delta_multi_agent_minus_baseline",
                "metric_group": "findings",
                "metric": metric,
                "value": value,
            }
        )
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["agent", "metric_group", "metric", "value"]
        )
        writer.writeheader()
        writer.writerows(rows)


def _print_summary(report: dict[str, Any]) -> None:
    baseline = report["agents"]["baseline"]["findings"]
    multi = report["agents"]["multi_agent"]["findings"]
    print("=== ContractGuard Evaluation Benchmark ===")
    print(
        f"mode={report['mode']} dataset={report['dataset_version']} "
        f"contracts={report['benchmark']['contracts']} "
        f"ground_truth={report['benchmark']['ground_truth_findings']}"
    )
    print(f"{'metric':<28}{'baseline':>12}{'multi-agent':>14}{'delta':>10}")
    for metric in (
        "precision",
        "recall",
        "f1",
        "severity_agreement",
        "citation_validity",
        "unsupported_claim_rate",
    ):
        delta = report["delta"]["findings"][metric]
        print(
            f"{metric:<28}{baseline[metric]:>12.4f}{multi[metric]:>14.4f}{delta:>10.4f}"
        )
    print(
        f"clause_extraction_recall    "
        f"{report['agents']['baseline']['clause_extraction']['recall']:>12.4f}"
        f"{report['agents']['multi_agent']['clause_extraction']['recall']:>14.4f}"
        f"{report['delta']['clause_extraction_recall']:>10.4f}"
    )
    print(report["notice"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--format", choices=("json", "csv", "both"), default="both")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV_OUTPUT)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)

    dataset = _load_json(args.dataset)
    report = asyncio.run(run_benchmark(dataset, mode=args.mode, dataset_path=args.dataset))

    if not args.no_write:
        if args.format in ("json", "both"):
            write_json(report, args.output)
        if args.format in ("csv", "both"):
            write_csv(report, args.csv_output)

    if args.format in ("json", "both"):
        print(json.dumps(report, indent=2))
    if args.format in ("csv", "both"):
        _print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
