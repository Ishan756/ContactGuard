# ContractGuard — Evaluation Benchmark

The `evaluation/` module contains isolated, versioned benchmark code and reports. It
compares a single-LLM baseline with ContractGuard's multi-agent workflow using synthetic
contracts and policy annotations.

**These metrics measure agreement with synthetic annotations. They do not measure legal
correctness, enforceability, or fitness for legal advice.**

## Directory Structure

```
evaluation/
|-- benchmarks/
|   +-- v1/
|       +-- dataset.json          # Versioned synthetic contracts, policies, annotations
|-- config/
|   |-- prompts.v1.json           # Versioned prompt text/version metadata
|   +-- model_config.v1.json      # Versioned model/evaluation configuration
|-- runners/
|   |-- agents.py                 # Deterministic baseline/multi-agent + optional live adapters
|   |-- benchmark.py              # Reproducible JSON/CSV benchmark CLI
|   |-- eval_harness.py           # Legacy accuracy harness scaffold
|   +-- eval_policy_retrieval.py  # Policy retrieval Recall@k / MRR benchmark
|-- reports/
|   |-- latest.json               # Generated report (metadata + computed metrics)
|   +-- latest.csv                # Long-form metric export
|-- tests/                        # Evaluation metric, agent, and report tests
+-- README.md
```

## Reproducible Benchmark

The default mock mode is deterministic and suitable for CI. It is not a substitute for
live model evaluation.

```bash
# From the repository root
python evaluation/runners/benchmark.py

# Explicit outputs
python evaluation/runners/benchmark.py \
  --dataset evaluation/benchmarks/v1/dataset.json \
  --format both \
  --output evaluation/reports/latest.json \
  --csv-output evaluation/reports/latest.csv

# Optional live model run (requires GEMINI_API_KEY and network access)
python evaluation/runners/benchmark.py --mode live --format json
```

The report records the dataset, prompt, and model-config versions and SHA-256 hashes, the
git commit, generation timestamp (or `SOURCE_DATE_EPOCH`), mode, benchmark size, per-agent
metrics, metric deltas, limitations, and a non-legal-advice notice. Report JSON is served
read-only by `GET /api/v1/evaluation/summary` and summarized on the frontend dashboard.

## Metrics

Metrics are computed from predicted findings and annotations; values are never hardcoded.

- **Finding precision / recall / F1** — deterministic finding-key matching on contract,
  category, finding type, and rule ID.
- **Severity agreement** — exact severity match among true-positive findings.
- **Citation validity** — contract and policy quotes checked verbatim against source text.
- **Unsupported legal claim rate** — explanations asserting illegality/voidness/
  unenforceability, which ContractGuard explicitly avoids.
- **Clause extraction precision / recall / F1** — category-level extraction comparison.
- **Metric delta** — multi-agent minus baseline for each finding metric.

The multi-agent mock path exercises the real backend `RiskRuleEngine`, missing-clause
generation, citation validation, and legal-claim sanitization. The baseline mock is a
single-pass heuristic with deliberate weaknesses (wrong severities, generic invalid policy
quotes, no missing-clause detection, a false-positive confidentiality concern, and an
unsupported legal conclusion). Live adapters call the configured `LLMProvider` but are
never run by tests or CI.

## Tests

```bash
# From the repository root; requires the backend dev environment
pytest evaluation/tests -q
```

## Policy Retrieval Benchmark

`evaluation/runners/eval_policy_retrieval.py` measures deterministic-embedding policy
retrieval with Recall@1/3/5 and MRR over synthetic policy passages:

```bash
python evaluation/runners/eval_policy_retrieval.py
```

## Limitations

- Three synthetic contracts and nine annotated findings are a smoke/regression benchmark,
  not a statistically meaningful legal dataset.
- The deterministic baseline and agents are simulations; mock-mode improvements do not
  demonstrate live-model quality.
- Legal correctness, enforceability, and jurisdiction-specific compliance are out of
  scope. Results must not be presented as legal advice.
