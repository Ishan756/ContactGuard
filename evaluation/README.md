# ContractGuard — Evaluation Framework

The `evaluation/` module is dedicated to measuring the accuracy, precision, recall, and calibration of ContractGuard's contract risk assessments and agent outputs against standardized benchmark legal datasets.

## Directory Structure

```
evaluation/
|-- benchmarks/
|   |-- sample_contracts/      # Curated benchmark agreements (NDAs, MSAs, SLA)
|   +-- ground_truth.json      # Verified human-attorney labeled clause risks
|-- runners/
|   +-- eval_harness.py        # Automated test harness computing agent metrics
+-- README.md
```

## Metrics Tracked
- **Clause Extraction Recall**: Percentage of relevant risk clauses properly isolated.
- **Risk Severity Alignment**: Mean squared error between AI-assigned risk score (0-100) and attorney consensus.
- **Hallucination Rate**: Citations checked against actual document source text.
- **Latency & Token Efficiency**: Cost and response time per audit run.
