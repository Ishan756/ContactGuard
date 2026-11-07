# Policy Retrieval & Risk Analysis Agents

Prompt 5 adds two sequential agents after clause extraction:

1. **Policy Retrieval Agent** — retrieves active company-policy passages for each extracted clause.
2. **Risk Analysis Agent** — compares clauses with retrieved evidence and persists review findings.

Risk findings are **review aids, not legal advice**. ContractGuard does not claim that a
clause is illegal, unlawful, void, invalid, or unenforceable. Findings contain verbatim
contract and policy citations so a human reviewer can verify each one.

---

## Pipeline

```text
POST /documents/{id}/extract-clauses
  -> POST /documents/{id}/retrieve-policies
       -> POST /documents/{id}/analyze-risk
            -> GET /documents/{id}/findings
```

The retrieval agent embeds deterministic category + meaning queries and searches the
`company_policies` Qdrant collection. Qdrant payloads do not contain policy lifecycle
status, so the service post-filters matches through PostgreSQL:

- Policy status must be in `POLICY_RETRIEVAL_STATUSES` (default `["active"]`).
- Optional request `policy_versions` limits evidence to specific versions.
- Draft and archived policies are excluded by default.
- Two queries are merged and de-duplicated by `chunk_id`, keeping the highest similarity.
- A clause with no evidence is explicitly marked `coverage_status: "missing"` with a note
  that a retrieval gap is **not** evidence of compliance.

Similarity scores measure semantic closeness only. They are not compliance scores.

---

## Deterministic risk rules

Deterministic rules run before any model analysis. Their severity comes from configuration:

| Rule ID | Trigger | Default severity |
|---|---|---|
| `liability_unlimited` | Contract contains unlimited/uncapped liability | `critical` |
| `liability_cap_exceeds_policy` | Contract liability cap exceeds policy cap | `high` |
| `termination_notice_shortfall` | Contract notice period is shorter than policy | `high` |
| `payment_period_exceeds_policy` | Contract payment period is longer than policy | `medium` |
| `required_category_missing:<category>` | Active policy requires a category absent from the contract | `high` |
| `no_retrievable_policy_evidence` | No active policy evidence matched a clause | `informational` |

Deterministic findings use `severity_basis: "policy_rule"` or
`"configured_requirement"`, `analysis_model: "policy-rule-engine"`, and no `confidence`.

Missing-clause requirements are inferred from the active policy corpus (for example a
policy with category `data_protection` or text about personal data / privacy) and can be
extended with `RISK_REQUIRED_CLAUSE_CATEGORIES`.

---

## Model-assisted analysis

The model is called **only** when:

- `RISK_ANALYSIS_ENABLE_MODEL=true` (or the request overrides it),
- no deterministic rule fired for the clause, and
- at least one policy evidence passage was retrieved.

The model must return a policy `policy_chunk_id`, an exact contract quote, and an exact
policy quote. The service rejects any finding whose quote is not verbatim or whose chunk
ID was not supplied. Model findings use `severity_basis: "model_analysis"`; severity still
comes from configuration (`RISK_SEVERITY_POLICY_DEVIATION` or
`RISK_SEVERITY_POSSIBLE_LEGAL_CONCERN`), never from model confidence or model-provided
severity.

Unverified legal conclusions are sanitized. For example, model text saying a clause is
"illegal and unenforceable" is replaced with "may raise a legal concern requiring qualified
human review".

There is no critic loop yet. Model output is citation-validated, not independently
re-reviewed by another model.

---

## Example findings

### Rule-based finding

```json
{
  "finding_id": "b5b3b99f-5d29-4f3e-93ec-9d8805f9ec1d",
  "clause_id": "15c9a4aa-1f0d-5f54-9f7a-cd84d3a83992",
  "clause_category": "liability",
  "finding_type": "policy_deviation",
  "risk_category": "liability",
  "severity": "critical",
  "severity_basis": "policy_rule",
  "rule_id": "liability_unlimited",
  "contract_quote": "The vendor's aggregate liability under this Agreement shall be unlimited.",
  "contract_source_reference": "clause:15c9a4aa-1f0d-5f54-9f7a-cd84d3a83992",
  "policy_quote": "Company requires all vendor contracts to cap aggregate liability at twelve (12) months of fees paid.",
  "policy_source_reference": "pol:ac72...:p1:c0",
  "policy_id": "ac72...",
  "policy_version": "1.0.0",
  "explanation": "The contract contains unlimited liability while the active policy requires a cap of 12 months of fees.",
  "confidence": null,
  "review_status": "needs_review",
  "analysis_model": "policy-rule-engine"
}
```

### Model-assisted finding

```json
{
  "finding_id": "9f0e8c0a-3c47-4f11-9f1a-09ce1f4a0f4e",
  "clause_id": "a2d1...",
  "clause_category": "confidentiality",
  "finding_type": "policy_deviation",
  "risk_category": "confidentiality",
  "severity": "medium",
  "severity_basis": "model_analysis",
  "rule_id": null,
  "contract_quote": "The vendor may disclose Confidential Information to subcontractors without prior written approval from the Company.",
  "policy_quote": "Confidential Information may only be disclosed to subcontractors with prior written approval from the Company.",
  "policy_source_reference": "pol:ab31...:p1:c0",
  "policy_id": "ab31...",
  "policy_version": "1.0.0",
  "explanation": "The contract allows disclosure without prior approval while the policy requires prior written approval.",
  "confidence": 0.87,
  "review_status": "needs_review",
  "analysis_model": "gemini-1.5-pro"
}
```

---

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/documents/{id}/retrieve-policies` | POST | Retrieve active policy evidence per clause |
| `/api/v1/documents/{id}/retrieval-runs` | GET | List retrieval runs |
| `/api/v1/documents/{id}/analyze-risk` | POST | Run rules + optional model analysis |
| `/api/v1/documents/{id}/analysis-runs` | GET | List analysis runs |
| `/api/v1/documents/{id}/findings` | GET | List findings (defaults to latest analysis run) |
| `/api/v1/documents/{id}/findings/{finding_id}` | GET | Get one finding with citations |

`analyze-risk` accepts an optional `retrieval_run_id` and `enable_model_analysis` override.
The retrieval request accepts optional `policy_versions` and `policy_statuses` filters.
`findings` accepts `analysis_run_id`, `severity`, and `category` filters.

---

## Configuration

```dotenv
POLICY_RETRIEVAL_LIMIT=5
POLICY_RETRIEVAL_MIN_SIMILARITY=0.0
POLICY_RETRIEVAL_STATUSES=["active"]

RISK_ANALYSIS_ENABLE_MODEL=true
RISK_SEVERITY_LIABILITY_UNLIMITED=critical
RISK_SEVERITY_LIABILITY_CAP=high
RISK_SEVERITY_TERMINATION_NOTICE=high
RISK_SEVERITY_PAYMENT_PERIOD=medium
RISK_SEVERITY_POLICY_DEVIATION=medium
RISK_SEVERITY_MISSING_DATA_PROTECTION=high
RISK_SEVERITY_MISSING_CLAUSE=high
RISK_SEVERITY_MISSING_EVIDENCE=informational
RISK_SEVERITY_POSSIBLE_LEGAL_CONCERN=informational
RISK_REQUIRED_CLAUSE_CATEGORIES=[]
```

LLM provider configuration is shared with clause extraction. Use `LLM_PROVIDER=mock` for
offline tests and `LLM_PROVIDER=gemini` with a valid `GEMINI_API_KEY` for production.
