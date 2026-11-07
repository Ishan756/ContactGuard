import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppException, NotFoundError, ProviderTimeoutError
from app.core.logging import get_logger
from app.db.models import (
    Clause,
    Document,
    EvidenceValidationAttempt,
    EvidenceValidationRun,
    ExtractionRunStatus,
    Policy,
    PolicyChunk,
    PolicyRetrievalEvidence,
    PolicyRetrievalRun,
    RiskAnalysisRun,
    RiskFinding,
)
from app.schemas.clause import normalize_category
from app.schemas.risk import (
    FindingType,
    RetryTarget,
    RiskPriority,
    ValidationAttemptStage,
    ValidationErrorCategory,
    ValidationStatus,
)
from app.schemas.validation import ValidationFeedbackItem
from app.services.risk.fingerprint import finding_fingerprint

logger = get_logger("contractguard.risk.validation")

_WHITESPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9]+")
_CORRECTABLE_FIELDS = (
    "finding_type",
    "risk_category",
    "severity",
    "severity_basis",
    "rule_id",
    "contract_quote",
    "contract_source_reference",
    "contract_page_number",
    "policy_quote",
    "policy_source_reference",
    "policy_page_number",
    "policy_id",
    "policy_version",
    "explanation",
    "suggested_question",
)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
}


def _normalize_whitespace(value: str | None) -> str:
    return _WHITESPACE.sub(" ", value or "").strip()


def _contains(source: str | None, quote: str | None) -> bool:
    normalized_quote = _normalize_whitespace(quote).casefold()
    if not normalized_quote or source is None:
        return False
    return normalized_quote in _normalize_whitespace(source).casefold()


def _tokens(value: str | None) -> set[str]:
    return {
        token
        for token in _TOKEN.findall((value or "").casefold())
        if token not in _STOPWORDS and (len(token) >= 3 or token.isdigit())
    }


def _meaningful_overlap(explanation: str, citations: str) -> int:
    return len(_tokens(explanation) & _tokens(citations))


def expected_severity(finding: RiskFinding, settings: Settings) -> RiskPriority | None:
    """Return the configured severity for a finding, never a model-derived priority."""
    rule_id = finding.rule_id or ""
    rule_severities = {
        "liability_unlimited": settings.risk_severity_liability_unlimited,
        "liability_cap_exceeds_policy": settings.risk_severity_liability_cap,
        "termination_notice_shortfall": settings.risk_severity_termination_notice,
        "payment_period_exceeds_policy": settings.risk_severity_payment_period,
        "no_retrievable_policy_evidence": settings.risk_severity_missing_evidence,
    }
    if rule_id in rule_severities:
        return RiskPriority(rule_severities[rule_id])
    if rule_id.startswith("required_category_missing:"):
        category = rule_id.split(":", 1)[1]
        if category == "data_protection":
            return RiskPriority(settings.risk_severity_missing_data_protection)
        return RiskPriority(settings.risk_severity_missing_clause)

    try:
        finding_type = FindingType(finding.finding_type)
    except ValueError:
        return None
    if finding_type == FindingType.POSSIBLE_LEGAL_CONCERN:
        return RiskPriority(settings.risk_severity_possible_legal_concern)
    if finding_type == FindingType.POLICY_DEVIATION:
        return RiskPriority(settings.risk_severity_policy_deviation)
    if finding_type == FindingType.MISSING_CLAUSE:
        if finding.risk_category == "data_protection":
            return RiskPriority(settings.risk_severity_missing_data_protection)
        return RiskPriority(settings.risk_severity_missing_clause)
    if finding_type == FindingType.MISSING_EVIDENCE:
        return RiskPriority(settings.risk_severity_missing_evidence)
    return None


_RETRIEVAL_CATEGORIES = {
    ValidationErrorCategory.MISSING_POLICY_QUOTE,
    ValidationErrorCategory.POLICY_QUOTE_NOT_FOUND,
    ValidationErrorCategory.POLICY_SOURCE_MISMATCH,
    ValidationErrorCategory.POLICY_SOURCE_NOT_IN_RETRIEVAL,
    ValidationErrorCategory.POLICY_ID_MISMATCH,
    ValidationErrorCategory.POLICY_VERSION_MISMATCH,
    ValidationErrorCategory.RETRIEVAL_RUN_MISMATCH,
    ValidationErrorCategory.RETRIEVAL_EVIDENCE_MISSING,
    ValidationErrorCategory.EVIDENCE_PRESENT,
    ValidationErrorCategory.MISSING_EVIDENCE,
}
_ANALYSIS_CATEGORIES = {
    ValidationErrorCategory.MISSING_CONTRACT_QUOTE,
    ValidationErrorCategory.CONTRACT_QUOTE_NOT_FOUND,
    ValidationErrorCategory.CONTRACT_SOURCE_MISSING,
    ValidationErrorCategory.DOCUMENT_ID_MISMATCH,
    ValidationErrorCategory.CLAUSE_ID_MISMATCH,
    ValidationErrorCategory.UNSUPPORTED_EXPLANATION,
    ValidationErrorCategory.SEVERITY_MISMATCH,
    ValidationErrorCategory.MALFORMED_CITATION,
    ValidationErrorCategory.FINDING_CONTRADICTED_BY_DOCUMENT,
    ValidationErrorCategory.PAGE_NUMBER_MISMATCH,
    ValidationErrorCategory.UNEXPECTED_FINDING_TYPE,
}


def _retry_target_for(category: ValidationErrorCategory) -> RetryTarget:
    if category in _ANALYSIS_CATEGORIES:
        return RetryTarget.ANALYSIS
    if category in _RETRIEVAL_CATEGORIES:
        return RetryTarget.RETRIEVAL
    return RetryTarget.NONE


def _finding_error_categories(finding: RiskFinding) -> list[ValidationErrorCategory]:
    categories: list[ValidationErrorCategory] = []
    if not finding.validation_error_categories:
        return categories
    try:
        raw = json.loads(finding.validation_error_categories)
    except (TypeError, json.JSONDecodeError):
        return categories
    if not isinstance(raw, list):
        return categories
    for item in raw:
        try:
            categories.append(ValidationErrorCategory(str(item)))
        except ValueError:
            continue
    return categories


def retry_target_for_finding(finding: RiskFinding) -> RetryTarget:
    """Expose the validator's deterministic retry routing for orchestration."""
    return _overall_retry_target(_finding_error_categories(finding))


def _overall_retry_target(
    categories: list[ValidationErrorCategory],
) -> RetryTarget:
    if any(category in _ANALYSIS_CATEGORIES for category in categories):
        return RetryTarget.ANALYSIS
    if any(category in _RETRIEVAL_CATEGORIES for category in categories):
        return RetryTarget.RETRIEVAL
    return RetryTarget.NONE


@dataclass
class FindingValidationResult:
    status: ValidationStatus
    feedback: list[ValidationFeedbackItem] = field(default_factory=list)
    error_categories: list[ValidationErrorCategory] = field(default_factory=list)
    retry_target: RetryTarget = RetryTarget.NONE


@dataclass
class RetryCorrection:
    finding: RiskFinding
    changed: bool = True


class FindingRetryHandler(Protocol):
    async def retry(
        self,
        finding: RiskFinding,
        feedback: list[ValidationFeedbackItem],
        target: RetryTarget,
        db: AsyncSession,
    ) -> RiskFinding | RetryCorrection | None: ...


class DeterministicCorrectionHandler:
    """Applies safe, evidence-preserving corrections requested by the validator."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def retry(
        self,
        finding: RiskFinding,
        feedback: list[ValidationFeedbackItem],
        target: RetryTarget,
        db: AsyncSession,
    ) -> RiskFinding | RetryCorrection | None:
        categories = {item.category for item in feedback}
        changed = False

        if target in (RetryTarget.RETRIEVAL, RetryTarget.ANALYSIS) and finding.policy_id:
            policy = await db.get(Policy, finding.policy_id)
            if policy is not None and finding.policy_quote:
                chunks = list(
                    (
                        await db.execute(
                            select(PolicyChunk)
                            .where(PolicyChunk.policy_id == policy.id)
                            .order_by(PolicyChunk.chunk_index)
                        )
                    )
                    .scalars()
                    .all()
                )
                matching_chunk = next(
                    (chunk for chunk in chunks if _contains(chunk.text, finding.policy_quote)),
                    None,
                )
                if matching_chunk is not None:
                    if finding.policy_source_reference != matching_chunk.source_identifier:
                        finding.policy_source_reference = matching_chunk.source_identifier
                        changed = True
                    if finding.policy_page_number != matching_chunk.page_number:
                        finding.policy_page_number = matching_chunk.page_number
                        changed = True

        if target == RetryTarget.ANALYSIS or categories & _ANALYSIS_CATEGORIES:
            if finding.clause_id:
                clause = await db.get(Clause, finding.clause_id)
                if clause is not None:
                    expected_reference = f"clause:{clause.id}"
                    if finding.contract_source_reference != expected_reference:
                        finding.contract_source_reference = expected_reference
                        changed = True
                    if (
                        clause.page_number is not None
                        and finding.contract_page_number != clause.page_number
                    ):
                        finding.contract_page_number = clause.page_number
                        changed = True
            expected = expected_severity(finding, self.settings)
            if expected is not None:
                try:
                    actual = RiskPriority(finding.severity)
                except ValueError:
                    actual = None
                if actual != expected:
                    finding.severity = expected.value
                    changed = True

        return RetryCorrection(finding=finding, changed=True) if changed else None


class EvidenceValidator:
    """Independently verifies findings against persisted contract and policy sources."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _failure(
        self, category: ValidationErrorCategory, field_name: str, message: str
    ) -> ValidationFeedbackItem:
        return ValidationFeedbackItem(
            category=category,
            field=field_name,
            message=message,
            retry_target=_retry_target_for(category),
        )

    async def _load_policy_chunks(
        self, policy_id: str, db: AsyncSession
    ) -> list[PolicyChunk]:
        return list(
            (
                await db.execute(
                    select(PolicyChunk)
                    .where(PolicyChunk.policy_id == policy_id)
                    .order_by(PolicyChunk.chunk_index)
                )
            )
            .scalars()
            .all()
        )

    async def validate_finding(
        self, finding: RiskFinding, db: AsyncSession
    ) -> FindingValidationResult:
        failures: list[ValidationFeedbackItem] = []

        def add(category: ValidationErrorCategory, field_name: str, message: str) -> None:
            failures.append(self._failure(category, field_name, message))

        try:
            finding_type = FindingType(finding.finding_type)
        except ValueError:
            add(
                ValidationErrorCategory.UNEXPECTED_FINDING_TYPE,
                "finding_type",
                "The finding type is not recognized by the validator.",
            )
            return FindingValidationResult(
                status=ValidationStatus.UNVERIFIED,
                feedback=failures,
                error_categories=[item.category for item in failures],
                retry_target=RetryTarget.ANALYSIS,
            )

        document = await db.get(Document, finding.document_id)
        if document is None:
            add(
                ValidationErrorCategory.DOCUMENT_ID_MISMATCH,
                "document_id",
                "The referenced document does not exist.",
            )

        clause: Clause | None = None
        if finding.clause_id:
            clause = await db.get(Clause, finding.clause_id)
            if clause is None:
                add(
                    ValidationErrorCategory.CLAUSE_ID_MISMATCH,
                    "clause_id",
                    "The referenced contract clause does not exist.",
                )
            elif clause.document_id != finding.document_id:
                add(
                    ValidationErrorCategory.DOCUMENT_ID_MISMATCH,
                    "clause_id",
                    "The referenced clause belongs to a different document.",
                )
        elif finding_type != FindingType.MISSING_CLAUSE:
            add(
                ValidationErrorCategory.MALFORMED_CITATION,
                "clause_id",
                "This finding type requires a contract clause identifier.",
            )

        retrieval_run = await db.get(PolicyRetrievalRun, finding.retrieval_run_id)
        if retrieval_run is None:
            add(
                ValidationErrorCategory.RETRIEVAL_RUN_MISMATCH,
                "retrieval_run_id",
                "The referenced policy retrieval run does not exist.",
            )
        elif retrieval_run.document_id != finding.document_id:
            add(
                ValidationErrorCategory.RETRIEVAL_RUN_MISMATCH,
                "retrieval_run_id",
                "The referenced retrieval run belongs to a different document.",
            )

        evidence_rows: list[PolicyRetrievalEvidence] = []
        if retrieval_run is not None and finding.clause_id:
            evidence_rows = list(
                (
                    await db.execute(
                        select(PolicyRetrievalEvidence)
                        .where(
                            PolicyRetrievalEvidence.retrieval_run_id == retrieval_run.id,
                            PolicyRetrievalEvidence.clause_id == finding.clause_id,
                        )
                        .order_by(PolicyRetrievalEvidence.rank)
                    )
                )
                .scalars()
                .all()
            )

        requires_contract_quote = finding_type in (
            FindingType.POLICY_DEVIATION,
            FindingType.POSSIBLE_LEGAL_CONCERN,
        )
        if requires_contract_quote and not finding.contract_quote:
            add(
                ValidationErrorCategory.MISSING_CONTRACT_QUOTE,
                "contract_quote",
                "A policy deviation must include a verbatim contract quote.",
            )
        elif finding.contract_quote:
            if clause is None:
                add(
                    ValidationErrorCategory.CONTRACT_SOURCE_MISSING,
                    "contract_quote",
                    "The contract quote has no resolvable clause source.",
                )
            elif not _contains(clause.source_text, finding.contract_quote):
                add(
                    ValidationErrorCategory.CONTRACT_QUOTE_NOT_FOUND,
                    "contract_quote",
                    "The contract quote is not present verbatim in the referenced clause.",
                )
            if clause is not None:
                if not finding.contract_source_reference:
                    add(
                        ValidationErrorCategory.MALFORMED_CITATION,
                        "contract_source_reference",
                        "The contract quote has no source reference.",
                    )
                else:
                    expected_reference = f"clause:{clause.id}"
                    if finding.contract_source_reference != expected_reference:
                        add(
                            ValidationErrorCategory.MALFORMED_CITATION,
                            "contract_source_reference",
                            "The contract source reference does not point to the cited clause.",
                        )
            if (
                clause is not None
                and finding.contract_page_number is not None
                and clause.page_number is not None
                and finding.contract_page_number != clause.page_number
            ):
                add(
                    ValidationErrorCategory.PAGE_NUMBER_MISMATCH,
                    "contract_page_number",
                    "The contract page number does not match the cited clause page.",
                )

        validates_policy = finding_type in (
            FindingType.POLICY_DEVIATION,
            FindingType.POSSIBLE_LEGAL_CONCERN,
            FindingType.MISSING_CLAUSE,
        )
        policy: Policy | None = None
        referenced_chunk: PolicyChunk | None = None
        policy_source_text: str | None = None
        if validates_policy:
            if not finding.policy_quote and finding_type != FindingType.MISSING_CLAUSE:
                add(
                    ValidationErrorCategory.MISSING_POLICY_QUOTE,
                    "policy_quote",
                    "A policy-based finding must include a verbatim policy quote.",
                )
            if not finding.policy_id:
                add(
                    ValidationErrorCategory.POLICY_ID_MISMATCH,
                    "policy_id",
                    "A policy-based finding must reference a persisted policy.",
                )
            else:
                policy = await db.get(Policy, finding.policy_id)
                if policy is None:
                    add(
                        ValidationErrorCategory.POLICY_ID_MISMATCH,
                        "policy_id",
                        "The referenced policy does not exist.",
                    )
                else:
                    if (
                        not finding.policy_version
                        or finding.policy_version != policy.version
                    ):
                        add(
                            ValidationErrorCategory.POLICY_VERSION_MISMATCH,
                            "policy_version",
                            "The policy version does not match the referenced policy record.",
                        )
                    chunks = await self._load_policy_chunks(policy.id, db)
                    source_reference = finding.policy_source_reference or ""
                    if not source_reference and finding_type in (
                        FindingType.POLICY_DEVIATION,
                        FindingType.POSSIBLE_LEGAL_CONCERN,
                    ):
                        add(
                            ValidationErrorCategory.POLICY_SOURCE_MISMATCH,
                            "policy_source_reference",
                            "The policy quote has no source reference.",
                        )
                    if source_reference.startswith("policy:") and source_reference.endswith(
                        ":metadata"
                    ):
                        policy_source_text = policy.description or ""
                    elif source_reference:
                        referenced_chunk = next(
                            (
                                chunk
                                for chunk in chunks
                                if chunk.source_identifier == source_reference
                            ),
                            None,
                        )
                        policy_source_text = (
                            referenced_chunk.text if referenced_chunk is not None else None
                        )

                    if not chunks and not policy.description:
                        add(
                            ValidationErrorCategory.INCONCLUSIVE,
                            "policy_id",
                            "The referenced policy has no persisted source text, so its "
                            "requirement cannot be conclusively validated.",
                        )
                    elif finding.policy_quote:
                        if policy_source_text is not None:
                            quote_found = _contains(policy_source_text, finding.policy_quote)
                        else:
                            quote_found = any(
                                _contains(chunk.text, finding.policy_quote)
                                for chunk in chunks
                            ) or _contains(policy.description, finding.policy_quote)
                        if not quote_found:
                            add(
                                ValidationErrorCategory.POLICY_QUOTE_NOT_FOUND,
                                "policy_quote",
                                "The policy quote is not present verbatim in the referenced "
                                "policy source.",
                            )
                        elif policy_source_text is None and source_reference:
                            add(
                                ValidationErrorCategory.POLICY_SOURCE_MISMATCH,
                                "policy_source_reference",
                                "The policy source reference could not be resolved; the quote "
                                "exists elsewhere in the policy.",
                            )
                    elif finding_type == FindingType.MISSING_CLAUSE:
                        add(
                            ValidationErrorCategory.MISSING_POLICY_QUOTE,
                            "policy_quote",
                            "The required-clause finding has no verbatim policy requirement "
                            "quote, so the requirement is inconclusive.",
                        )

                    if (
                        referenced_chunk is not None
                        and finding.policy_page_number is not None
                        and finding.policy_page_number != referenced_chunk.page_number
                    ):
                        add(
                            ValidationErrorCategory.PAGE_NUMBER_MISMATCH,
                            "policy_page_number",
                            "The policy page number does not match the cited policy chunk.",
                        )

        if finding_type in (
            FindingType.POLICY_DEVIATION,
            FindingType.POSSIBLE_LEGAL_CONCERN,
        ):
            if retrieval_run is not None and finding.clause_id and not evidence_rows:
                add(
                    ValidationErrorCategory.RETRIEVAL_EVIDENCE_MISSING,
                    "retrieval_run_id",
                    "The referenced retrieval run contains no evidence for this clause.",
                )
            elif finding.policy_source_reference:
                matching_evidence = next(
                    (
                        row
                        for row in evidence_rows
                        if row.source_identifier == finding.policy_source_reference
                    ),
                    None,
                )
                if matching_evidence is None:
                    add(
                        ValidationErrorCategory.POLICY_SOURCE_NOT_IN_RETRIEVAL,
                        "policy_source_reference",
                        "The cited policy source was not retrieved in the referenced run.",
                    )
                else:
                    if finding.policy_id and matching_evidence.policy_id != finding.policy_id:
                        add(
                            ValidationErrorCategory.POLICY_ID_MISMATCH,
                            "policy_id",
                            "The retrieved evidence belongs to a different policy.",
                        )
                    if (
                        finding.policy_version
                        and matching_evidence.policy_version != finding.policy_version
                    ):
                        add(
                            ValidationErrorCategory.POLICY_VERSION_MISMATCH,
                            "policy_version",
                            "The retrieved evidence uses a different policy version.",
                        )
                    if finding.policy_quote and not _contains(
                        matching_evidence.text, finding.policy_quote
                    ):
                        add(
                            ValidationErrorCategory.POLICY_QUOTE_NOT_FOUND,
                            "policy_quote",
                            "The policy quote is not present verbatim in the retrieved "
                            "evidence.",
                        )

        if finding_type == FindingType.MISSING_EVIDENCE:
            if evidence_rows:
                add(
                    ValidationErrorCategory.EVIDENCE_PRESENT,
                    "retrieval_run_id",
                    "The finding claims missing evidence, but evidence exists for this clause.",
                )

        if finding_type == FindingType.MISSING_CLAUSE:
            category, recognized = normalize_category(finding.risk_category)
            if recognized:
                existing = (
                    await db.execute(
                        select(func.count(Clause.id)).where(
                            Clause.document_id == finding.document_id,
                            Clause.category == category.value,
                        )
                    )
                ).scalar() or 0
                if existing:
                    add(
                        ValidationErrorCategory.FINDING_CONTRADICTED_BY_DOCUMENT,
                        "risk_category",
                        "The document already contains a clause in the required category.",
                    )

        if finding_type in (FindingType.POLICY_DEVIATION, FindingType.MISSING_CLAUSE):
            citations = " ".join(
                item for item in (finding.contract_quote, finding.policy_quote) if item
            )
            if citations and (
                _meaningful_overlap(finding.explanation, citations)
                < self.settings.validation_explanation_min_overlap
            ):
                add(
                    ValidationErrorCategory.UNSUPPORTED_EXPLANATION,
                    "explanation",
                    "The explanation is not supported by meaningful terms from the cited "
                    "contract or policy evidence.",
                )

        expected = expected_severity(finding, self.settings)
        try:
            actual_severity = RiskPriority(finding.severity)
        except ValueError:
            actual_severity = None
            add(
                ValidationErrorCategory.MALFORMED_CITATION,
                "severity",
                "The finding severity is not a recognized configured priority.",
            )
        if expected is not None and actual_severity != expected:
            add(
                ValidationErrorCategory.SEVERITY_MISMATCH,
                "severity",
                f"Severity must be '{expected.value}' according to configured rules.",
            )

        categories = [item.category for item in failures]
        if not failures:
            status = (
                ValidationStatus.MISSING_EVIDENCE
                if finding_type == FindingType.MISSING_EVIDENCE
                else ValidationStatus.VERIFIED
            )
        elif ValidationErrorCategory.DUPLICATE_FINDING in categories:
            status = ValidationStatus.NEEDS_REVIEW
        elif ValidationErrorCategory.MISSING_EVIDENCE in categories:
            status = ValidationStatus.MISSING_EVIDENCE
        elif (
            ValidationErrorCategory.INCONCLUSIVE in categories
            or (
                finding_type == FindingType.MISSING_CLAUSE
                and ValidationErrorCategory.MISSING_POLICY_QUOTE in categories
            )
        ):
            status = ValidationStatus.INCONCLUSIVE
        else:
            status = ValidationStatus.UNVERIFIED

        return FindingValidationResult(
            status=status,
            feedback=failures,
            error_categories=categories,
            retry_target=_overall_retry_target(categories),
        )


class EvidenceValidationService:
    """Runs independent validation, bounded correction retries, and observability."""

    def __init__(
        self,
        settings: Settings,
        retry_handler: FindingRetryHandler | None = None,
    ) -> None:
        self.settings = settings
        self.validator = EvidenceValidator(settings)
        self.retry_handler = retry_handler or DeterministicCorrectionHandler(settings)

    async def _resolve_analysis_run(
        self, document_id: str, analysis_run_id: str | None, db: AsyncSession
    ) -> RiskAnalysisRun:
        if analysis_run_id:
            run = (
                await db.execute(
                    select(RiskAnalysisRun).where(
                        RiskAnalysisRun.id == analysis_run_id,
                        RiskAnalysisRun.document_id == document_id,
                    )
                )
            ).scalar_one_or_none()
            if run is None:
                raise NotFoundError(
                    f"Risk analysis run '{analysis_run_id}' not found for document "
                    f"'{document_id}'."
                )
            return run

        run = (
            await db.execute(
                select(RiskAnalysisRun)
                .where(RiskAnalysisRun.document_id == document_id)
                .order_by(RiskAnalysisRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            raise NotFoundError(
                f"Document '{document_id}' has no risk analysis run to validate."
            )
        return run

    async def _load_findings(
        self,
        run: RiskAnalysisRun,
        finding_ids: list[str] | None,
        db: AsyncSession,
    ) -> list[RiskFinding]:
        stmt = (
            select(RiskFinding)
            .where(
                RiskFinding.document_id == run.document_id,
                RiskFinding.analysis_run_id == run.id,
            )
            .order_by(RiskFinding.created_at, RiskFinding.id)
        )
        if finding_ids is not None:
            unique_ids = sorted(set(finding_ids))
            stmt = stmt.where(RiskFinding.id.in_(unique_ids))
        findings = list((await db.execute(stmt)).scalars().all())
        if finding_ids is not None:
            found_ids = {finding.id for finding in findings}
            missing = sorted(set(finding_ids) - found_ids)
            if missing:
                raise NotFoundError(
                    "Risk finding(s) not found in the selected analysis run: "
                    + ", ".join(missing)
                )
        return findings

    def _record_attempt(
        self,
        validation_run_id: str,
        finding_id: str,
        attempt_number: int,
        stage: ValidationAttemptStage,
        outcome: ValidationStatus,
        feedback: list[ValidationFeedbackItem],
        retry_target: RetryTarget,
        started_at: datetime,
        duration_ms: int,
        retry_error_category: ValidationErrorCategory | None = None,
    ) -> EvidenceValidationAttempt:
        return EvidenceValidationAttempt(
            id=str(uuid.uuid4()),
            validation_run_id=validation_run_id,
            finding_id=finding_id,
            attempt_number=attempt_number,
            stage=stage.value,
            outcome=outcome.value,
            retry_target=retry_target.value,
            error_categories=json.dumps([item.category.value for item in feedback]),
            feedback=json.dumps([item.model_dump(mode="json") for item in feedback]),
            retry_error_category=(
                retry_error_category.value if retry_error_category else None
            ),
            duration_ms=duration_ms,
            created_at=started_at,
            completed_at=datetime.now(UTC),
        )

    def _apply_result(
        self,
        finding: RiskFinding,
        result: FindingValidationResult,
        attempt_number: int,
    ) -> None:
        finding.validation_status = result.status.value
        finding.validation_attempts = attempt_number
        finding.validation_error_categories = (
            json.dumps([item.value for item in result.error_categories])
            if result.error_categories
            else None
        )
        finding.last_validated_at = datetime.now(UTC)

    async def validate_findings(
        self,
        document_id: str,
        db: AsyncSession,
        analysis_run_id: str | None = None,
        finding_ids: list[str] | None = None,
        max_retries: int | None = None,
        enable_retries: bool = True,
    ) -> tuple[EvidenceValidationRun, list[RiskFinding], list[EvidenceValidationAttempt]]:
        document = await db.get(Document, document_id)
        if document is None:
            raise NotFoundError(f"Document with ID '{document_id}' not found.")

        analysis_run = await self._resolve_analysis_run(document_id, analysis_run_id, db)
        findings = await self._load_findings(analysis_run, finding_ids, db)
        retry_limit = (
            self.settings.validation_max_retries if max_retries is None else max_retries
        )
        retry_limit = min(max(retry_limit, 0), 5)

        run = EvidenceValidationRun(
            id=str(uuid.uuid4()),
            document_id=document_id,
            analysis_run_id=analysis_run.id,
            retrieval_run_id=analysis_run.retrieval_run_id,
            status=ExtractionRunStatus.RUNNING,
            max_retries=retry_limit,
            findings_validated=len(findings),
            created_at=datetime.now(UTC),
        )
        db.add(run)
        await db.flush()

        attempts: list[EvidenceValidationAttempt] = []
        warnings: list[str] = []
        seen_fingerprints: dict[str, str] = {}
        retries_attempted = 0

        try:
            for finding in findings:
                fingerprint = finding_fingerprint(finding)
                finding.fingerprint = fingerprint
                if (
                    self.settings.validation_duplicate_detection
                    and fingerprint in seen_fingerprints
                ):
                    duplicate = self.validator._failure(
                        ValidationErrorCategory.DUPLICATE_FINDING,
                        "fingerprint",
                        "A finding with the same evidence fingerprint already exists in this run.",
                    )
                    result = FindingValidationResult(
                        status=ValidationStatus.NEEDS_REVIEW,
                        feedback=[duplicate],
                        error_categories=[ValidationErrorCategory.DUPLICATE_FINDING],
                        retry_target=RetryTarget.NONE,
                    )
                    started_at = datetime.now(UTC)
                    attempt = self._record_attempt(
                        run.id,
                        finding.id,
                        1,
                        ValidationAttemptStage.INITIAL,
                        result.status,
                        result.feedback,
                        result.retry_target,
                        started_at,
                        duration_ms=0,
                    )
                    attempts.append(attempt)
                    db.add(attempt)
                    self._apply_result(finding, result, 1)
                    warnings.append(
                        f"Duplicate finding '{finding.id}' was marked for review and not approved."
                    )
                    continue

                seen_fingerprints[fingerprint] = finding.id
                validations = 0
                final_result: FindingValidationResult | None = None
                while validations <= retry_limit:
                    validations += 1
                    stage = (
                        ValidationAttemptStage.INITIAL
                        if validations == 1
                        else ValidationAttemptStage.RETRY
                    )
                    started_at = datetime.now(UTC)
                    start_clock = time.perf_counter()
                    result = await self.validator.validate_finding(finding, db)
                    duration_ms = int((time.perf_counter() - start_clock) * 1000)
                    final_result = result
                    attempt = self._record_attempt(
                        run.id,
                        finding.id,
                        validations,
                        stage,
                        result.status,
                        result.feedback,
                        result.retry_target,
                        started_at,
                        duration_ms,
                    )
                    attempts.append(attempt)
                    db.add(attempt)
                    self._apply_result(finding, result, validations)

                    if result.status != ValidationStatus.UNVERIFIED:
                        break
                    if not enable_retries or retries_attempted >= retry_limit:
                        break
                    if result.retry_target == RetryTarget.NONE:
                        break

                    retries_attempted += 1
                    retry_started_at = datetime.now(UTC)
                    retry_clock = time.perf_counter()
                    try:
                        correction = await self.retry_handler.retry(
                            finding, result.feedback, result.retry_target, db
                        )
                    except (ProviderTimeoutError, TimeoutError):
                        retry_duration_ms = int(
                            (time.perf_counter() - retry_clock) * 1000
                        )
                        retry_feedback = self.validator._failure(
                            ValidationErrorCategory.RETRY_TIMEOUT,
                            "retry",
                            "The correction step timed out; the finding remains unverified.",
                        )
                        retry_attempt = self._record_attempt(
                            run.id,
                            finding.id,
                            validations,
                            ValidationAttemptStage.RETRY,
                            ValidationStatus.UNVERIFIED,
                            [retry_feedback],
                            result.retry_target,
                            retry_started_at,
                            retry_duration_ms,
                            retry_error_category=ValidationErrorCategory.RETRY_TIMEOUT,
                        )
                        attempts.append(retry_attempt)
                        db.add(retry_attempt)
                        warnings.append(
                            f"Correction timed out for finding '{finding.id}'; "
                            "the finding remains unverified."
                        )
                        continue
                    except Exception as exc:
                        retry_duration_ms = int(
                            (time.perf_counter() - retry_clock) * 1000
                        )
                        retry_feedback = self.validator._failure(
                            ValidationErrorCategory.RETRY_FAILED,
                            "retry",
                            "The correction step failed; the finding remains unverified.",
                        )
                        retry_attempt = self._record_attempt(
                            run.id,
                            finding.id,
                            validations,
                            ValidationAttemptStage.RETRY,
                            ValidationStatus.UNVERIFIED,
                            [retry_feedback],
                            result.retry_target,
                            retry_started_at,
                            retry_duration_ms,
                            retry_error_category=ValidationErrorCategory.RETRY_FAILED,
                        )
                        attempts.append(retry_attempt)
                        db.add(retry_attempt)
                        warnings.append(
                            f"Correction failed for finding '{finding.id}'; "
                            "the finding remains unverified."
                        )
                        logger.warning(
                            "Validation correction failed for finding %s (%s)",
                            finding.id,
                            type(exc).__name__,
                        )
                        break

                    if correction is None:
                        break
                    corrected_finding = (
                        correction.finding
                        if isinstance(correction, RetryCorrection)
                        else correction
                    )
                    if not isinstance(correction, RetryCorrection) or correction.changed:
                        if corrected_finding is not finding:
                            for attribute in _CORRECTABLE_FIELDS:
                                setattr(
                                    finding,
                                    attribute,
                                    getattr(corrected_finding, attribute),
                                )

                if final_result is not None and final_result.status == ValidationStatus.UNVERIFIED:
                    warnings.append(
                        f"Finding '{finding.id}' remains unverified after "
                        f"{finding.validation_attempts} validation attempt(s)."
                    )

            run.findings_validated = len(findings)
            run.verified_count = sum(
                1
                for finding in findings
                if finding.validation_status == ValidationStatus.VERIFIED.value
            )
            run.unverified_count = sum(
                1
                for finding in findings
                if finding.validation_status == ValidationStatus.UNVERIFIED.value
            )
            run.needs_review_count = sum(
                1
                for finding in findings
                if finding.validation_status == ValidationStatus.NEEDS_REVIEW.value
            )
            run.missing_evidence_count = sum(
                1
                for finding in findings
                if finding.validation_status == ValidationStatus.MISSING_EVIDENCE.value
            )
            run.inconclusive_count = sum(
                1
                for finding in findings
                if finding.validation_status == ValidationStatus.INCONCLUSIVE.value
            )
            run.retries_attempted = retries_attempted
            run.warnings = json.dumps(warnings) if warnings else None
            run.status = (
                ExtractionRunStatus.PARTIAL
                if warnings
                or run.verified_count != run.findings_validated
                else ExtractionRunStatus.COMPLETED
            )
            run.completed_at = datetime.now(UTC)
            await db.commit()

            logger.info(
                "Evidence validation completed for document %s: run=%s findings=%s "
                "verified=%s unverified=%s retries=%s",
                document_id,
                run.id,
                run.findings_validated,
                run.verified_count,
                run.unverified_count,
                run.retries_attempted,
            )
            return run, findings, attempts
        except AppException:
            run.status = ExtractionRunStatus.FAILED
            run.error_message = "Evidence validation failed."
            run.completed_at = datetime.now(UTC)
            await db.commit()
            raise
        except Exception as exc:
            run.status = ExtractionRunStatus.FAILED
            run.error_message = "Evidence validation failed."
            run.warnings = json.dumps(warnings) if warnings else None
            run.completed_at = datetime.now(UTC)
            await db.commit()
            logger.exception(
                "Evidence validation failed for document %s (%s)",
                document_id,
                type(exc).__name__,
            )
            raise AppException(
                f"Evidence validation failed ({type(exc).__name__}).",
                code="EVIDENCE_VALIDATION_FAILED",
            ) from exc

    async def list_runs(
        self, document_id: str, db: AsyncSession, limit: int = 20, offset: int = 0
    ) -> tuple[list[EvidenceValidationRun], int]:
        total = (
            await db.execute(
                select(func.count(EvidenceValidationRun.id)).where(
                    EvidenceValidationRun.document_id == document_id
                )
            )
        ).scalar() or 0
        runs = list(
            (
                await db.execute(
                    select(EvidenceValidationRun)
                    .where(EvidenceValidationRun.document_id == document_id)
                    .order_by(EvidenceValidationRun.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return runs, total

    async def get_run(
        self, document_id: str, validation_run_id: str, db: AsyncSession
    ) -> EvidenceValidationRun:
        run = (
            await db.execute(
                select(EvidenceValidationRun).where(
                    EvidenceValidationRun.id == validation_run_id,
                    EvidenceValidationRun.document_id == document_id,
                )
            )
        ).scalar_one_or_none()
        if run is None:
            raise NotFoundError(
                f"Validation run '{validation_run_id}' not found for document "
                f"'{document_id}'."
            )
        return run

    async def get_attempts(
        self, validation_run_id: str, db: AsyncSession
    ) -> list[EvidenceValidationAttempt]:
        return list(
            (
                await db.execute(
                    select(EvidenceValidationAttempt)
                    .where(EvidenceValidationAttempt.validation_run_id == validation_run_id)
                    .order_by(
                        EvidenceValidationAttempt.created_at,
                        EvidenceValidationAttempt.attempt_number,
                    )
                )
            )
            .scalars()
            .all()
        )

    async def get_run_findings(
        self, run: EvidenceValidationRun, db: AsyncSession
    ) -> list[RiskFinding]:
        return list(
            (
                await db.execute(
                    select(RiskFinding)
                    .where(RiskFinding.analysis_run_id == run.analysis_run_id)
                    .order_by(RiskFinding.created_at, RiskFinding.id)
                )
            )
            .scalars()
            .all()
        )

    async def validate(
        self, document_id: str, request, db: AsyncSession
    ) -> tuple[EvidenceValidationRun, list[RiskFinding], list[EvidenceValidationAttempt]]:
        return await self.validate_findings(
            document_id=document_id,
            db=db,
            analysis_run_id=request.analysis_run_id,
            finding_ids=request.finding_ids,
            max_retries=request.max_retries,
            enable_retries=request.enable_retries,
        )
