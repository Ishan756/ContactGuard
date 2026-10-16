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
- **Policy Retrieval Quality**: Recall@k and Mean Reciprocal Rank (MRR) measuring retrieval accuracy against enterprise policy rules.

## Policy Knowledge Base Retrieval Benchmark

The benchmark runner is located at `evaluation/runners/eval_policy_retrieval.py`. It measures how effectively the embedding model and vector search rank ground-truth policy passages for individual target clauses across Liability, Intellectual Property, and Termination categories.

### Baseline Benchmark Results

Evaluated over synthetic enterprise policies and target clauses:

| Metric | Score | Baseline Target |
| :--- | :--- | :--- |
| **Recall@1** | 0.3333 | - |
| **Recall@3** | 0.6667 | >= 0.60 |
| **Recall@5** | 0.8333 | >= 0.80 |
| **MRR (Mean Reciprocal Rank)** | 0.5056 | >= 0.50 |

### Reproducing the Measurements

Run the evaluation runner directly using Python:
```bash
python evaluation/runners/eval_policy_retrieval.py
```

Or verify with pytest:
```bash
pytest evaluation/runners/eval_policy_retrieval.py -v
```
