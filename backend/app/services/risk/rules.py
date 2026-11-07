import re
from dataclasses import dataclass

from app.core.config import Settings
from app.db.models import Clause
from app.schemas.clause import ClauseCategory, normalize_category
from app.schemas.risk import FindingType, RiskPriority, SeverityBasis
from app.services.risk.retrieval import ClauseRetrieval, RetrievedEvidence

_MONTHS_PATTERN = re.compile(
    r"\((\d+)\)\s*(?:months?|mos?)\b|(\d+)\s*(?:months?|mos?)\b", re.IGNORECASE
)
_DAYS_PATTERN = re.compile(
    r"\((\d+)\)\s*(?:business\s+)?days?\b|"
    r"(?:net\s*)?(\d+)\s*(?:business\s+)?days?\b",
    re.IGNORECASE,
)
_UNLIMITED_PATTERNS = [
    re.compile(r"\bunlimited liability\b", re.IGNORECASE),
    re.compile(r"\buncapped liability\b", re.IGNORECASE),
    re.compile(r"\bliability (?:shall|will) not be limited\b", re.IGNORECASE),
    re.compile(r"\bliability\b.{0,80}\bunlimited\b", re.IGNORECASE),
    re.compile(r"\bunlimited\b.{0,80}\bliability\b", re.IGNORECASE),
    re.compile(r"\bno (?:cap|limitation) on liability\b", re.IGNORECASE),
    re.compile(r"\bwithout (?:any )?limitation of liability\b", re.IGNORECASE),
]


def _matched_number(match: re.Match[str]) -> int:
    return int(match.group(1) or match.group(2))
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.;!?])\s+|\n+")
_ILLEGAL_PATTERNS = re.compile(
    r"\b(illegal|unlawful|unenforceable|void|invalid|violates? (?:the )?law)\b",
    re.IGNORECASE,
)


@dataclass
class RuleFinding:
    rule_id: str
    finding_type: FindingType
    risk_category: str
    severity: RiskPriority
    severity_basis: SeverityBasis
    explanation: str
    suggested_question: str
    contract_quote: str | None = None
    contract_source_reference: str | None = None
    policy_evidence: RetrievedEvidence | None = None
    policy_quote: str | None = None
    policy_source_reference: str | None = None
    policy_id: str | None = None
    policy_version: str | None = None


def _window_contains(text: str, index: int, keyword: str, radius: int = 160) -> bool:
    start = max(0, index - radius)
    end = min(len(text), index + radius)
    return keyword in text[start:end].lower()


def extract_liability_months(text: str) -> int | None:
    for match in _MONTHS_PATTERN.finditer(text):
        if _window_contains(text, match.start(), "liabilit") or _window_contains(
            text, match.start(), "cap"
        ):
            value = _matched_number(match)
            if 0 < value <= 120:
                return value
    return None


def extract_termination_notice_days(text: str) -> int | None:
    for match in _DAYS_PATTERN.finditer(text):
        if _window_contains(text, match.start(), "terminat") and _window_contains(
            text, match.start(), "notice"
        ):
            value = _matched_number(match)
            if 0 < value <= 730:
                return value
    return None


def extract_payment_days(text: str) -> int | None:
    for match in _DAYS_PATTERN.finditer(text):
        if any(
            _window_contains(text, match.start(), keyword)
            for keyword in ("payment", "invoice", "pay ", "fees")
        ):
            value = _matched_number(match)
            if 0 < value <= 730:
                return value
    return None


def _sentence_containing(text: str, value: int) -> str:
    for sentence in _SENTENCE_BOUNDARY.split(text):
        if str(value) in sentence:
            return sentence.strip()
    return text.strip()


def sanitize_legal_claims(value: str) -> str:
    """Replace unverified legal conclusions with a review-safe statement."""
    if not value:
        return value
    return _ILLEGAL_PATTERNS.sub(
        "may raise a legal concern requiring qualified human review", value
    )


class RiskRuleEngine:
    """Deterministic policy comparison rules with severity sourced from configuration."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _evidence_with_months(
        self, evidence: list[RetrievedEvidence]
    ) -> tuple[RetrievedEvidence, int] | None:
        for item in evidence:
            months = extract_liability_months(item.text)
            if months is not None:
                return item, months
        return None

    def _evidence_with_termination_days(
        self, evidence: list[RetrievedEvidence]
    ) -> tuple[RetrievedEvidence, int] | None:
        for item in evidence:
            days = extract_termination_notice_days(item.text)
            if days is not None:
                return item, days
        return None

    def _evidence_with_payment_days(
        self, evidence: list[RetrievedEvidence]
    ) -> tuple[RetrievedEvidence, int] | None:
        for item in evidence:
            days = extract_payment_days(item.text)
            if days is not None:
                return item, days
        return None

    def _first_evidence(self, evidence: list[RetrievedEvidence]) -> RetrievedEvidence:
        return evidence[0]

    def _liability_rules(self, clause: Clause, retrieval: ClauseRetrieval) -> list[RuleFinding]:
        text = clause.source_text
        evidence = retrieval.evidence
        if not evidence:
            return []

        contract_months = extract_liability_months(text)
        policy_match = self._evidence_with_months(evidence)
        unlimited = any(pattern.search(text) for pattern in _UNLIMITED_PATTERNS)

        if unlimited:
            policy_item = policy_match[0] if policy_match else self._first_evidence(evidence)
            policy_months = policy_match[1] if policy_match else None
            requirement = (
                f"a cap of {policy_months} months of fees"
                if policy_months is not None
                else "a contractual liability cap"
            )
            return [
                RuleFinding(
                    rule_id="liability_unlimited",
                    finding_type=FindingType.POLICY_DEVIATION,
                    risk_category=ClauseCategory.LIABILITY.value,
                    severity=RiskPriority(self.settings.risk_severity_liability_unlimited),
                    severity_basis=SeverityBasis.POLICY_RULE,
                    explanation=(
                        "The contract contains unlimited liability while the active policy requires "
                        f"{requirement}. This requires human review against the policy."
                    ),
                    suggested_question=(
                        "Can liability be capped in line with the active policy before signature?"
                    ),
                    contract_quote=text,
                    contract_source_reference=f"clause:{clause.id}",
                    policy_evidence=policy_item,
                    policy_quote=policy_item.text,
                )
            ]

        if contract_months is not None and policy_match is not None:
            policy_item, policy_months = policy_match
            if contract_months > policy_months:
                return [
                    RuleFinding(
                        rule_id="liability_cap_exceeds_policy",
                        finding_type=FindingType.POLICY_DEVIATION,
                        risk_category=ClauseCategory.LIABILITY.value,
                        severity=RiskPriority(self.settings.risk_severity_liability_cap),
                        severity_basis=SeverityBasis.POLICY_RULE,
                        explanation=(
                            f"The contract caps liability at {contract_months} months of fees, "
                            f"while the active policy requires a cap of no more than "
                            f"{policy_months} months."
                        ),
                        suggested_question=(
                            f"Can the liability cap be reduced from {contract_months} to "
                            f"{policy_months} months?"
                        ),
                        contract_quote=_sentence_containing(text, contract_months),
                        contract_source_reference=f"clause:{clause.id}",
                        policy_evidence=policy_item,
                        policy_quote=_sentence_containing(policy_item.text, policy_months),
                    )
                ]
        return []

    def _termination_rules(
        self, clause: Clause, retrieval: ClauseRetrieval
    ) -> list[RuleFinding]:
        text = clause.source_text
        if not retrieval.evidence:
            return []
        contract_days = extract_termination_notice_days(text)
        policy_match = self._evidence_with_termination_days(retrieval.evidence)
        if contract_days is None or policy_match is None:
            return []
        policy_item, policy_days = policy_match
        if contract_days >= policy_days:
            return []
        return [
            RuleFinding(
                rule_id="termination_notice_shortfall",
                finding_type=FindingType.POLICY_DEVIATION,
                risk_category=ClauseCategory.TERMINATION.value,
                severity=RiskPriority(self.settings.risk_severity_termination_notice),
                severity_basis=SeverityBasis.POLICY_RULE,
                explanation=(
                    f"The contract permits termination on {contract_days} days' notice, while "
                    f"the active policy requires at least {policy_days} days' notice."
                ),
                suggested_question=(
                    f"Can the termination notice period be increased from {contract_days} to "
                    f"{policy_days} days?"
                ),
                contract_quote=_sentence_containing(text, contract_days),
                contract_source_reference=f"clause:{clause.id}",
                policy_evidence=policy_item,
                policy_quote=_sentence_containing(policy_item.text, policy_days),
            )
        ]

    def _payment_rules(self, clause: Clause, retrieval: ClauseRetrieval) -> list[RuleFinding]:
        text = clause.source_text
        if not retrieval.evidence:
            return []
        contract_days = extract_payment_days(text)
        policy_match = self._evidence_with_payment_days(retrieval.evidence)
        if contract_days is None or policy_match is None:
            return []
        policy_item, policy_days = policy_match
        if contract_days <= policy_days:
            return []
        return [
            RuleFinding(
                rule_id="payment_period_exceeds_policy",
                finding_type=FindingType.POLICY_DEVIATION,
                risk_category=ClauseCategory.PAYMENT.value,
                severity=RiskPriority(self.settings.risk_severity_payment_period),
                severity_basis=SeverityBasis.POLICY_RULE,
                explanation=(
                    f"The contract allows {contract_days} days to pay, while the active policy "
                    f"requires payment within {policy_days} days."
                ),
                suggested_question=(
                    f"Can the payment period be shortened from {contract_days} to "
                    f"{policy_days} days?"
                ),
                contract_quote=_sentence_containing(text, contract_days),
                contract_source_reference=f"clause:{clause.id}",
                policy_evidence=policy_item,
                policy_quote=_sentence_containing(policy_item.text, policy_days),
            )
        ]

    def _missing_evidence_finding(
        self, clause: Clause, retrieval: ClauseRetrieval
    ) -> RuleFinding:
        category, _ = normalize_category(clause.category)
        return RuleFinding(
            rule_id="no_retrievable_policy_evidence",
            finding_type=FindingType.MISSING_EVIDENCE,
            risk_category=category.value,
            severity=RiskPriority(self.settings.risk_severity_missing_evidence),
            severity_basis=SeverityBasis.RETRIEVAL_GAP,
            explanation=(
                "No active policy evidence was retrieved for this clause. Absence of evidence "
                "is not evidence of compliance; a human reviewer should confirm coverage."
            ),
            suggested_question=(
                "Which active policy governs this clause, and why was no matching policy text retrieved?"
            ),
            contract_quote=clause.source_text,
            contract_source_reference=f"clause:{clause.id}",
        )

    def evaluate_clause(
        self, clause: Clause, retrieval: ClauseRetrieval
    ) -> list[RuleFinding]:
        category, _ = normalize_category(clause.category)
        findings: list[RuleFinding] = []

        if category == ClauseCategory.LIABILITY:
            findings.extend(self._liability_rules(clause, retrieval))
        elif category == ClauseCategory.TERMINATION:
            findings.extend(self._termination_rules(clause, retrieval))
        elif category == ClauseCategory.PAYMENT:
            findings.extend(self._payment_rules(clause, retrieval))

        if not findings and not retrieval.evidence:
            findings.append(self._missing_evidence_finding(clause, retrieval))
        return findings

    def missing_clause_finding(
        self,
        category: ClauseCategory,
        policy_name: str,
        policy_id: str,
        policy_version: str,
        policy_quote: str | None,
        policy_source_reference: str | None,
    ) -> RuleFinding:
        if category == ClauseCategory.DATA_PROTECTION:
            severity = RiskPriority(self.settings.risk_severity_missing_data_protection)
        else:
            severity = RiskPriority(self.settings.risk_severity_missing_clause)
        return RuleFinding(
            rule_id=f"required_category_missing:{category.value}",
            finding_type=FindingType.MISSING_CLAUSE,
            risk_category=category.value,
            severity=severity,
            severity_basis=SeverityBasis.CONFIGURED_REQUIREMENT,
            explanation=(
                f"The active policy '{policy_name}' requires {category.value.replace('_', ' ')} "
                "coverage, but no such clause was extracted from the contract."
            ),
            suggested_question=(
                f"Should the contract include a {category.value.replace('_', ' ')} clause "
                f"required by the active policy '{policy_name}'?"
            ),
            policy_quote=policy_quote,
            policy_source_reference=policy_source_reference,
            policy_id=policy_id,
            policy_version=policy_version,
        )
