import hashlib
import re

_WHITESPACE = re.compile(r"\s+")


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE.sub(" ", value).strip().casefold()


def finding_fingerprint(finding) -> str:
    """Return a stable duplicate-detection fingerprint for a risk finding."""
    parts = [
        finding.document_id,
        finding.clause_id or "",
        finding.finding_type,
        finding.risk_category,
        finding.rule_id or "",
        finding.policy_id or "",
        finding.policy_version or "",
        _normalize(finding.contract_quote),
        _normalize(finding.policy_quote),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
