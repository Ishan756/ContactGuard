# Policy Retrieval & Risk Analysis Agents

Prompt 5 adds two sequential agents after clause extraction, and Prompt 6 adds an
independent critic that verifies their evidence before a finding can be treated as verified:

1. **Policy Retrieval Agent** — retrieves active company-policy passages for each extracted clause.
2. **Risk Analysis Agent** — compares clauses with retrieved evidence and persists review findings.
3. **Evidence Validation Agent (Critic)** — independently re-checks every finding against
   persisted contract and policy sources, requests bounded corrections, and records every
   attempt. Failed findings remain `unverified`/`needs_review`; they are never auto-approved.

Risk findings are **review aids, not legal advice**. ContractGuard does not claim that a
clause is illegal, unlawful, void, invalid, or unenforceable. Findings contain verbatim
contract and policy citations so a human reviewer can verify each one.

---

## Pipeline

```text
POST /documents/{id}/extract-clauses
  -> POST /documents/{id}/retrieve-policies
       -> POST /documents/{id}/analyze-risk  (runs validation automatically)
            -> GET /documents/{id}/findings
            -> POST /documents/{id}/validate-findings  (re-run validation)
                 -> GET /documents/{id}/validation-runs
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

The risk-analysis service rejects non-verbatim model quotes before persistence. The
Evidence Validation Agent then independently re-reads the database sources; it never trusts
the finding's self-assessment.

---

## Independent evidence validation and correction retries

The validator persists one `EvidenceValidationRun` per validation pass and one
`EvidenceValidationAttempt` for every check or correction attempt. It verifies:

- Contract quotes are verbatim substrings of the referenced persisted clause.
- Policy quotes are verbatim substrings of the referenced policy chunk, or of policy
  metadata when the requirement source is `policy:<id>:metadata`.
- The document, clause, retrieval-run, policy, policy-version, and page-number identifiers
  belong together and match the cited evidence.
- Policy deviation findings use a policy passage that was actually present in the referenced
  retrieval run.
- Missing-clause findings are not contradicted by an already-extracted clause.
- Missing-evidence findings are only accepted when the retrieval run has no evidence for
  that clause; evidence present means the finding is invalid.
- The explanation shares meaningful terms with its cited contract/policy evidence.
- Severity equals the configured rule/requirement priority, never model confidence.

Failures are classified into machine-readable categories such as
`contract_quote_not_found`, `policy_quote_not_found`, `policy_version_mismatch`,
`page_number_mismatch`, `unsupported_explanation`, `severity_mismatch`,
`retrieval_evidence_missing`, and `duplicate_finding`. Duplicate findings are merged before
persistence and flagged with a stable fingerprint if they still appear in stored data.

### Finding lifecycle

```text
pending -> verified
pending -> unverified -> (bounded correction retry) -> verified
pending -> unverified -> retries exhausted -> unverified / needs_review
pending -> missing_evidence   (valid retrieval gap; still requires human review)
pending -> inconclusive       (requirement/evidence cannot be conclusively checked)
```

`verified` means the **citations and provenance passed independent checks**. It does not
mean the contract is compliant or that legal review is complete. Missing evidence and
inconclusive findings are deliberately not marked verified. Human `review_status` remains
`needs_review`; validation never dismisses or approves a finding on a reviewer's behalf.

Retries are deterministic and bounded by `VALIDATION_MAX_RETRIES` (default `2`, hard limit
`5`). Contract/clause/explanation/severity failures route to the analysis correction step;
policy citation/retrieval failures route to the retrieval correction step. Each attempt has
an outcome, error categories, retry target, duration, and timestamps. Timeouts and retry
exhaustion stop the loop and leave the finding `unverified`.

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
  "validation_status": "verified",
  "validation_attempts": 1,
  "validation_error_categories": [],
  "contract_page_number": 1,
  "policy_page_number": 1,
  "last_validated_at": "2026-11-06T14:40:03Z",
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
  "validation_status": "verified",
  "validation_attempts": 1,
  "validation_error_categories": [],
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
| `/api/v1/documents/{id}/validate-findings` | POST | Re-run independent validation with bounded retries |
| `/api/v1/documents/{id}/validation-runs` | GET | List validation runs |
| `/api/v1/documents/{id}/validation-runs/{run_id}` | GET | Get a validation run, findings, and every attempt |

`analyze-risk` accepts optional `retrieval_run_id`, `enable_model_analysis`,
`enable_validation`, and `validation_max_retries` overrides. Validation runs automatically
unless `VALIDATION_ENABLE=false` or `enable_validation=false`; unresolved findings are still
persisted as unverified rather than hidden. `validate-findings` accepts optional
`analysis_run_id`, `finding_ids`, `max_retries`, and `enable_retries`.
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

VALIDATION_ENABLE=true
VALIDATION_MAX_RETRIES=2
VALIDATION_EXPLANATION_MIN_OVERLAP=2
VALIDATION_DUPLICATE_DETECTION=true
```

LLM provider configuration is shared with clause extraction. Use `LLM_PROVIDER=mock` for
offline tests and `LLM_PROVIDER=gemini` with a valid `GEMINI_API_KEY` for production.
