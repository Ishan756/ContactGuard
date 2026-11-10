"""Pure metric implementations for the ContractGuard evaluation benchmark.

All metrics are computed from supplied predictions and ground truth. No metric
value is hardcoded.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

_WHITESPACE = re.compile(r"\s+")
_LEGAL_CONCLUSION = re.compile(
    r"\b(illegal|unlawful|unenforceable|void|invalid|violates? (?:the )?law)\b",
    re.IGNORECASE,
)


def normalize_text(value: str | None) -> str:
    return _WHITESPACE.sub(" ", value or "").strip().casefold()


def finding_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("contract_id", "")),
        str(item.get("risk_category", "")),
        str(item.get("finding_type", "")),
        str(item.get("rule_id") or ""),
    )


def _safe_div(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


@dataclass
class ConfusionCounts:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    matched_severity_agreements: int = 0
    predictions_with_contract_quote: int = 0
    valid_contract_citations: int = 0
    predictions_with_policy_quote: int = 0
    valid_policy_citations: int = 0
    unsupported_claim_predictions: int = 0
    total_predictions: int = 0
    per_contract: dict[str, dict[str, int]] = field(default_factory=dict)


def compute_finding_metrics(
    predictions: Iterable[dict[str, Any]],
    ground_truth: Iterable[dict[str, Any]],
    contract_texts: dict[str, str],
    policy_texts: dict[str, str],
) -> dict[str, Any]:
    predictions = list(predictions)
    ground_truth = list(ground_truth)
    gt_by_key = {finding_key(item): item for item in ground_truth}
    predicted_keys = {finding_key(item) for item in predictions}

    counts = ConfusionCounts(total_predictions=len(predictions))
    for prediction in predictions:
        key = finding_key(prediction)
        contract_id = key[0]
        per_contract = counts.per_contract.setdefault(
            contract_id, {"tp": 0, "fp": 0, "fn": 0}
        )
        if key in gt_by_key:
            counts.true_positives += 1
            per_contract["tp"] += 1
            if str(prediction.get("severity")) == str(gt_by_key[key].get("severity")):
                counts.matched_severity_agreements += 1
        else:
            counts.false_positives += 1
            per_contract["fp"] += 1

        contract_quote = prediction.get("contract_quote")
        if contract_quote:
            counts.predictions_with_contract_quote += 1
            if normalize_text(contract_quote) in normalize_text(
                contract_texts.get(contract_id, "")
            ):
                counts.valid_contract_citations += 1

        policy_quote = prediction.get("policy_quote")
        if policy_quote:
            counts.predictions_with_policy_quote += 1
            policy_id = str(prediction.get("policy_id") or "")
            haystack = policy_texts.get(policy_id)
            if haystack is None:
                haystack = " ".join(policy_texts.values())
            if normalize_text(policy_quote) in normalize_text(haystack):
                counts.valid_policy_citations += 1

        if _LEGAL_CONCLUSION.search(str(prediction.get("explanation", ""))):
            counts.unsupported_claim_predictions += 1

    for key in gt_by_key:
        if key not in predicted_keys:
            counts.false_negatives += 1
            per_contract = counts.per_contract.setdefault(
                key[0], {"tp": 0, "fp": 0, "fn": 0}
            )
            per_contract["fn"] += 1

    precision = _safe_div(
        counts.true_positives, counts.true_positives + counts.false_positives
    )
    recall = _safe_div(
        counts.true_positives, counts.true_positives + counts.false_negatives
    )
    f1 = _safe_div(2 * precision * recall, precision + recall)

    return {
        "true_positives": counts.true_positives,
        "false_positives": counts.false_positives,
        "false_negatives": counts.false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "severity_agreement": _safe_div(
            counts.matched_severity_agreements, counts.true_positives
        ),
        "citation_validity": _safe_div(
            counts.valid_contract_citations + counts.valid_policy_citations,
            counts.predictions_with_contract_quote
            + counts.predictions_with_policy_quote,
        ),
        "contract_citation_validity": _safe_div(
            counts.valid_contract_citations, counts.predictions_with_contract_quote
        ),
        "policy_citation_validity": _safe_div(
            counts.valid_policy_citations, counts.predictions_with_policy_quote
        ),
        "unsupported_claim_rate": _safe_div(
            counts.unsupported_claim_predictions, counts.total_predictions
        ),
        "predictions": counts.total_predictions,
        "ground_truth": len(ground_truth),
        "per_contract": counts.per_contract,
    }


def compute_clause_extraction_metrics(
    extracted_by_contract: dict[str, list[dict[str, Any]]],
    ground_truth_by_contract: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    tp = fp = fn = 0
    per_contract: dict[str, dict[str, int]] = {}
    for contract_id, expected in ground_truth_by_contract.items():
        expected_categories = [str(item.get("category")) for item in expected]
        actual_categories = [
            str(item.get("category"))
            for item in extracted_by_contract.get(contract_id, [])
        ]
        expected_counts: dict[str, int] = {}
        actual_counts: dict[str, int] = {}
        for category in expected_categories:
            expected_counts[category] = expected_counts.get(category, 0) + 1
        for category in actual_categories:
            actual_counts[category] = actual_counts.get(category, 0) + 1
        contract_tp = sum(
            min(actual_counts.get(category, 0), expected_counts.get(category, 0))
            for category in expected_counts
        )
        contract_fp = sum(actual_counts.values()) - contract_tp
        contract_fn = sum(expected_counts.values()) - contract_tp
        tp += contract_tp
        fp += contract_fp
        fn += contract_fn
        per_contract[contract_id] = {"tp": contract_tp, "fp": contract_fp, "fn": contract_fn}

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": _safe_div(2 * precision * recall, precision + recall),
        "per_contract": per_contract,
    }


def metric_delta(
    multi_agent: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, float]:
    keys = (
        "precision",
        "recall",
        "f1",
        "severity_agreement",
        "citation_validity",
        "unsupported_claim_rate",
    )
    return {
        key: round(
            float(multi_agent.get(key, 0.0)) - float(baseline.get(key, 0.0)), 4
        )
        for key in keys
    }
