import json
from pathlib import Path

from evaluation.runners.agents import (
    extract_clauses,
    run_baseline,
    run_multi_agent,
)

DATASET_PATH = Path(__file__).resolve().parents[1] / "benchmarks/v1/dataset.json"


def _dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def test_section_extraction_assigns_categories():
    dataset = _dataset()
    contract = next(item for item in dataset["contracts"] if item["contract_id"] == "acme-msa-v1")
    clauses = extract_clauses(contract)
    assert [clause["category"] for clause in clauses] == [
        "liability",
        "termination",
        "payment",
        "confidentiality",
    ]


def test_mock_agents_are_deterministic():
    dataset = _dataset()
    assert run_baseline(dataset) == run_baseline(dataset)
    assert run_multi_agent(dataset) == run_multi_agent(dataset)


def test_multi_agent_matches_annotations_without_legal_conclusions():
    dataset = _dataset()
    result = run_multi_agent(dataset)
    predictions = result["predictions"]

    ground_truth_keys = {
        (
            contract["contract_id"],
            finding["risk_category"],
            finding["finding_type"],
            finding["rule_id"],
        )
        for contract in dataset["contracts"]
        for finding in contract["ground_truth_findings"]
    }
    predicted_keys = {
        (
            finding["contract_id"],
            finding["risk_category"],
            finding["finding_type"],
            finding["rule_id"],
        )
        for finding in predictions
    }

    assert ground_truth_keys == predicted_keys
    assert all(finding["source"] == "multi_agent" for finding in predictions)
    assert all("unlawful" not in finding["explanation"].casefold() for finding in predictions)


def test_baseline_has_known_weaknesses_for_comparison():
    dataset = _dataset()
    predictions = run_baseline(dataset)["predictions"]

    finding_types = {finding["finding_type"] for finding in predictions}
    assert "missing_clause" not in finding_types
    assert any("unlawful" in finding["explanation"].casefold() for finding in predictions)
    assert any(finding["policy_id"] is None for finding in predictions)
