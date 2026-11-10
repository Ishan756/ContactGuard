import csv
import json
from pathlib import Path

import pytest

from evaluation.metrics import compute_finding_metrics
from evaluation.runners.agents import run_baseline, run_multi_agent
from evaluation.runners.benchmark import (
    DEFAULT_DATASET,
    run_benchmark,
    write_csv,
    write_json,
)


def _dataset() -> dict:
    return json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_benchmark_report_uses_computed_metrics_and_version_metadata():
    dataset = _dataset()
    report = await run_benchmark(dataset, mode="mock", dataset_path=DEFAULT_DATASET)

    assert report["mode"] == "mock"
    assert report["dataset_version"] == dataset["version"]
    assert report["dataset_sha256"]
    assert report["prompt_version"] == "v1"
    assert report["model_config_version"] == "v1"
    assert report["git_commit"]
    assert report["benchmark"]["ground_truth_findings"] == sum(
        len(contract["ground_truth_findings"]) for contract in dataset["contracts"]
    )
    assert set(report["agents"]) == {"baseline", "multi_agent"}
    assert report["limitations"]
    assert "not establish legal correctness" in report["notice"]

    contract_texts = {
        contract["contract_id"]: contract["text"] for contract in dataset["contracts"]
    }
    policy_texts = {policy["policy_id"]: policy["text"] for policy in dataset["policies"]}
    ground_truth = [
        {**finding, "contract_id": contract["contract_id"]}
        for contract in dataset["contracts"]
        for finding in contract["ground_truth_findings"]
    ]
    expected = compute_finding_metrics(
        run_multi_agent(dataset)["predictions"], ground_truth, contract_texts, policy_texts
    )
    assert report["agents"]["multi_agent"]["findings"] == expected

    baseline_expected = compute_finding_metrics(
        run_baseline(dataset)["predictions"], ground_truth, contract_texts, policy_texts
    )
    assert report["agents"]["baseline"]["findings"] == baseline_expected
    assert report["delta"]["findings"]["recall"] == pytest.approx(
        expected["recall"] - baseline_expected["recall"], abs=1e-4
    )


def test_benchmark_writes_json_and_long_form_csv(tmp_path: Path):
    report = {
        "agents": {
            "baseline": {
                "findings": {"precision": 0.5, "recall": 0.25, "per_contract": {}},
                "clause_extraction": {"recall": 1.0},
            },
            "multi_agent": {
                "findings": {"precision": 0.75, "recall": 0.5},
                "clause_extraction": {"recall": 1.0},
            },
        },
        "delta": {"findings": {"precision": 0.25, "recall": 0.25}},
    }
    json_path = tmp_path / "report.json"
    csv_path = tmp_path / "report.csv"
    write_json(report, json_path)
    write_csv(report, csv_path)

    assert json.loads(json_path.read_text(encoding="utf-8")) == report
    rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))
    assert {row["agent"] for row in rows} == {
        "baseline",
        "multi_agent",
        "delta_multi_agent_minus_baseline",
    }
    assert all(set(row) == {"agent", "metric_group", "metric", "value"} for row in rows)
    assert not any(row["metric"] == "per_contract" for row in rows)
