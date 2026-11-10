from evaluation.metrics import (
    compute_clause_extraction_metrics,
    compute_finding_metrics,
    metric_delta,
)


def test_finding_metrics_compute_confusion_citations_and_claims():
    predictions = [
        {
            "contract_id": "c1",
            "risk_category": "liability",
            "finding_type": "policy_deviation",
            "rule_id": "liability_unlimited",
            "severity": "critical",
            "contract_quote": "liability shall be unlimited",
            "policy_quote": "cap liability at twelve months",
            "policy_id": "p1",
            "explanation": "The clause deviates from the liability policy.",
        },
        {
            "contract_id": "c1",
            "risk_category": "payment",
            "finding_type": "policy_deviation",
            "rule_id": "payment_period_exceeds_policy",
            "severity": "low",
            "contract_quote": "invoices are payable in gold",
            "policy_quote": "invoices are free forever",
            "policy_id": "p2",
            "explanation": "This payment term is void.",
        },
    ]
    ground_truth = [
        {
            "contract_id": "c1",
            "risk_category": "liability",
            "finding_type": "policy_deviation",
            "rule_id": "liability_unlimited",
            "severity": "critical",
        },
        {
            "contract_id": "c1",
            "risk_category": "termination",
            "finding_type": "missing_clause",
            "rule_id": "required_category_missing:termination",
            "severity": "high",
        },
    ]
    metrics = compute_finding_metrics(
        predictions,
        ground_truth,
        contract_texts={"c1": "The liability shall be unlimited. Invoices are never payable."},
        policy_texts={
            "p1": "Company requires a cap liability at twelve months of fees.",
            "p2": "Invoices are due within thirty days.",
        },
    )

    assert metrics["true_positives"] == 1
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 1
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == 0.5
    assert metrics["severity_agreement"] == 1.0
    assert metrics["contract_citation_validity"] == 0.5
    assert metrics["policy_citation_validity"] == 0.5
    assert metrics["citation_validity"] == 0.5
    assert metrics["unsupported_claim_rate"] == 0.5
    assert metrics["predictions"] == 2
    assert metrics["ground_truth"] == 2


def test_clause_extraction_metrics_count_duplicates_and_misses():
    metrics = compute_clause_extraction_metrics(
        extracted_by_contract={
            "c1": [
                {"category": "liability"},
                {"category": "liability"},
                {"category": "payment"},
            ],
            "c2": [{"category": "termination"}],
        },
        ground_truth_by_contract={
            "c1": [
                {"category": "liability"},
                {"category": "liability"},
                {"category": "termination"},
            ],
            "c2": [{"category": "termination"}],
        },
    )

    assert metrics["true_positives"] == 3
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 1
    assert metrics["precision"] == 0.75
    assert metrics["recall"] == 0.75


def test_metric_delta_is_multi_agent_minus_baseline():
    delta = metric_delta(
        {"precision": 0.9, "recall": 0.8, "unsupported_claim_rate": 0.1},
        {"precision": 0.5, "recall": 0.4, "unsupported_claim_rate": 0.3},
    )
    assert delta["precision"] == 0.4
    assert delta["recall"] == 0.4
    assert delta["unsupported_claim_rate"] == -0.2
