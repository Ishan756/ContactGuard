import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import (
    Clause,
    ClauseChange,
    ClauseChangeType,
    ComparisonStatus,
    ContractComparison,
    Document,
    FindingChange,
    FindingChangeType,
    RiskAnalysisRun,
    RiskFinding,
)
from app.schemas.clause import normalize_category
from app.schemas.comparison import ContractComparisonRequest
from app.services.risk.analysis import RiskAnalysisService

logger = get_logger("contractguard.comparison.service")

_WHITESPACE = re.compile(r"\s+")
_UNCHANGED_SIMILARITY = 0.99
_MATCH_THRESHOLD = 0.55


def _normalize(value: str | None) -> str:
    return _WHITESPACE.sub(" ", value or "").strip().casefold()


def _similarity(left: str | None, right: str | None) -> float:
    left_text = _normalize(left)
    right_text = _normalize(right)
    if not left_text or not right_text:
        return 0.0
    return round(SequenceMatcher(None, left_text, right_text).ratio(), 4)


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


@dataclass(frozen=True)
class ClauseMatch:
    base: Clause
    target: Clause
    similarity: float


@dataclass(frozen=True)
class FindingKey:
    risk_category: str
    finding_type: str
    rule_id: str


def _finding_key(finding: RiskFinding) -> FindingKey:
    return FindingKey(
        risk_category=finding.risk_category,
        finding_type=finding.finding_type,
        rule_id=finding.rule_id or "",
    )


class ContractComparisonService:
    """Deterministically compares two contract versions and their latest findings."""

    def __init__(
        self,
        settings: Settings,
        risk_analysis: RiskAnalysisService | None = None,
    ) -> None:
        self.settings = settings
        self.risk_analysis = risk_analysis

    async def _get_document(self, document_id: str, db: AsyncSession) -> Document:
        document = (
            await db.execute(select(Document).where(Document.id == document_id))
        ).scalar_one_or_none()
        if not document:
            raise NotFoundError(f"Document with ID '{document_id}' not found.")
        return document

    async def _clauses(self, document_id: str, db: AsyncSession) -> list[Clause]:
        return list(
            (
                await db.execute(
                    select(Clause)
                    .where(Clause.document_id == document_id)
                    .order_by(Clause.start_char_offset, Clause.id)
                )
            )
            .scalars()
            .all()
        )

    def _match_clauses(
        self, base_clauses: list[Clause], target_clauses: list[Clause]
    ) -> list[ClauseMatch]:
        candidates: list[tuple[float, str, str, Clause, Clause]] = []
        for base in base_clauses:
            for target in target_clauses:
                text_score = _similarity(base.source_text, target.source_text)
                heading_score = _similarity(base.section_heading, target.section_heading)
                category_bonus = 0.15 if base.category == target.category else 0.0
                score = max(text_score, (heading_score * 0.4) + (text_score * 0.6))
                score += category_bonus
                if (
                    score >= _MATCH_THRESHOLD
                    or text_score >= 0.6
                    or (base.category == target.category and heading_score >= 0.6)
                ):
                    candidates.append((score, base.id, target.id, base, target))

        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        used_base: set[str] = set()
        used_target: set[str] = set()
        matches: list[ClauseMatch] = []
        for _, base_id, target_id, base, target in candidates:
            if base_id in used_base or target_id in used_target:
                continue
            used_base.add(base_id)
            used_target.add(target_id)
            matches.append(
                ClauseMatch(
                    base=base,
                    target=target,
                    similarity=_similarity(base.source_text, target.source_text),
                )
            )
        return matches

    def _clause_change(self, match: ClauseMatch, comparison_id: str) -> ClauseChange:
        base_category = normalize_category(match.base.category)[0].value
        target_category = normalize_category(match.target.category)[0].value
        if base_category != target_category:
            change_type = ClauseChangeType.RECLASSIFIED
        elif match.similarity >= _UNCHANGED_SIMILARITY:
            change_type = ClauseChangeType.UNCHANGED
        else:
            change_type = ClauseChangeType.MODIFIED
        category = target_category
        summary = (
            f"{category.replace('_', ' ').title()} clause {change_type.value} "
            f"({match.similarity:.0%} text similarity)."
        )
        return ClauseChange(
            id=str(uuid.uuid4()),
            comparison_id=comparison_id,
            change_type=change_type.value,
            category=category,
            base_clause_id=match.base.id,
            target_clause_id=match.target.id,
            base_category=base_category,
            target_category=target_category,
            base_source_text=match.base.source_text,
            target_source_text=match.target.source_text,
            base_source_reference=f"clause:{match.base.id}",
            target_source_reference=f"clause:{match.target.id}",
            similarity=match.similarity,
            change_summary=summary,
        )

    def _clause_only_change(
        self, clause: Clause, comparison_id: str, change_type: ClauseChangeType
    ) -> ClauseChange:
        category = normalize_category(clause.category)[0].value
        is_base = change_type == ClauseChangeType.REMOVED
        return ClauseChange(
            id=str(uuid.uuid4()),
            comparison_id=comparison_id,
            change_type=change_type.value,
            category=category,
            base_clause_id=clause.id if is_base else None,
            target_clause_id=None if is_base else clause.id,
            base_category=category if is_base else None,
            target_category=None if is_base else category,
            base_source_text=clause.source_text if is_base else None,
            target_source_text=None if is_base else clause.source_text,
            base_source_reference=f"clause:{clause.id}" if is_base else None,
            target_source_reference=None if is_base else f"clause:{clause.id}",
            similarity=0.0,
            change_summary=(
                f"{category.replace('_', ' ').title()} clause {change_type.value} "
                f"in the {'earlier' if is_base else 'newer'} version."
            ),
        )

    async def _latest_analysis_run(
        self, document_id: str, db: AsyncSession
    ) -> RiskAnalysisRun | None:
        return (
            await db.execute(
                select(RiskAnalysisRun)
                .where(RiskAnalysisRun.document_id == document_id)
                .order_by(RiskAnalysisRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _findings_for_run(
        self, run_id: str | None, db: AsyncSession
    ) -> list[RiskFinding]:
        if not run_id:
            return []
        return list(
            (
                await db.execute(
                    select(RiskFinding)
                    .where(RiskFinding.analysis_run_id == run_id)
                    .order_by(RiskFinding.created_at, RiskFinding.id)
                )
            )
            .scalars()
            .all()
        )

    def _finding_changes(
        self,
        comparison_id: str,
        base_findings: list[RiskFinding],
        target_findings: list[RiskFinding],
    ) -> list[FindingChange]:
        base_by_key: dict[FindingKey, list[RiskFinding]] = {}
        target_by_key: dict[FindingKey, list[RiskFinding]] = {}
        for finding in base_findings:
            base_by_key.setdefault(_finding_key(finding), []).append(finding)
        for finding in target_findings:
            target_by_key.setdefault(_finding_key(finding), []).append(finding)

        changes: list[FindingChange] = []
        for key in sorted(
            set(base_by_key) | set(target_by_key),
            key=lambda item: (item.risk_category, item.finding_type, item.rule_id),
        ):
            base_items = list(base_by_key.get(key, []))
            target_items = list(target_by_key.get(key, []))
            paired = min(len(base_items), len(target_items))
            for index in range(paired):
                base = base_items[index]
                target = target_items[index]
                change_type = (
                    FindingChangeType.SEVERITY_CHANGED
                    if base.severity != target.severity
                    else FindingChangeType.PERSISTED
                )
                changes.append(
                    FindingChange(
                        id=str(uuid.uuid4()),
                        comparison_id=comparison_id,
                        change_type=change_type.value,
                        finding_type=target.finding_type,
                        risk_category=target.risk_category,
                        rule_id=target.rule_id,
                        base_finding_id=base.id,
                        target_finding_id=target.id,
                        base_severity=base.severity,
                        target_severity=target.severity,
                        base_validation_status=base.validation_status,
                        target_validation_status=target.validation_status,
                        contract_source_reference=target.contract_source_reference,
                        explanation=(
                            f"Finding {change_type.value.replace('_', ' ')} between versions."
                        ),
                    )
                )
            for base in base_items[paired:]:
                changes.append(
                    FindingChange(
                        id=str(uuid.uuid4()),
                        comparison_id=comparison_id,
                        change_type=FindingChangeType.RESOLVED.value,
                        finding_type=base.finding_type,
                        risk_category=base.risk_category,
                        rule_id=base.rule_id,
                        base_finding_id=base.id,
                        target_finding_id=None,
                        base_severity=base.severity,
                        target_severity=None,
                        base_validation_status=base.validation_status,
                        target_validation_status=None,
                        contract_source_reference=base.contract_source_reference,
                        explanation="Finding resolved or no longer raised in the newer version.",
                    )
                )
            for target in target_items[paired:]:
                changes.append(
                    FindingChange(
                        id=str(uuid.uuid4()),
                        comparison_id=comparison_id,
                        change_type=FindingChangeType.NEW.value,
                        finding_type=target.finding_type,
                        risk_category=target.risk_category,
                        rule_id=target.rule_id,
                        base_finding_id=None,
                        target_finding_id=target.id,
                        base_severity=None,
                        target_severity=target.severity,
                        base_validation_status=None,
                        target_validation_status=target.validation_status,
                        contract_source_reference=target.contract_source_reference,
                        explanation="Finding newly raised in the newer version.",
                    )
                )
        return changes

    async def compare(
        self,
        request: ContractComparisonRequest,
        reviewer_id: str,
        db: AsyncSession,
    ) -> ContractComparison:
        if request.base_document_id == request.target_document_id:
            raise ValidationError("Base and target documents must be different.")
        base_document = await self._get_document(request.base_document_id, db)
        target_document = await self._get_document(request.target_document_id, db)

        base_clauses = await self._clauses(base_document.id, db)
        target_clauses = await self._clauses(target_document.id, db)
        if not base_clauses:
            raise ValidationError(
                f"Base document '{base_document.id}' has no extracted clauses."
            )
        if not target_clauses:
            raise ValidationError(
                f"Target document '{target_document.id}' has no extracted clauses."
            )

        comparison = ContractComparison(
            id=str(uuid.uuid4()),
            base_document_id=base_document.id,
            target_document_id=target_document.id,
            created_by=reviewer_id,
            status=ComparisonStatus.RUNNING,
            reanalysis_requested=request.reanalyze_target,
            created_at=datetime.now(UTC),
        )
        db.add(comparison)
        await db.flush()

        warnings: list[str] = []
        try:
            matches = self._match_clauses(base_clauses, target_clauses)
            matched_base_ids = {match.base.id for match in matches}
            matched_target_ids = {match.target.id for match in matches}
            changes = [self._clause_change(match, comparison.id) for match in matches]
            changes.extend(
                self._clause_only_change(clause, comparison.id, ClauseChangeType.REMOVED)
                for clause in base_clauses
                if clause.id not in matched_base_ids
            )
            changes.extend(
                self._clause_only_change(clause, comparison.id, ClauseChangeType.ADDED)
                for clause in target_clauses
                if clause.id not in matched_target_ids
            )

            counts = {item.value: 0 for item in ClauseChangeType}
            for change in changes:
                counts[change.change_type] += 1
                db.add(change)
            comparison.clauses_added = counts[ClauseChangeType.ADDED.value]
            comparison.clauses_removed = counts[ClauseChangeType.REMOVED.value]
            comparison.clauses_modified = counts[ClauseChangeType.MODIFIED.value]
            comparison.clauses_unchanged = counts[ClauseChangeType.UNCHANGED.value]
            comparison.clauses_reclassified = counts[ClauseChangeType.RECLASSIFIED.value]

            affected_target_ids = [
                change.target_clause_id
                for change in changes
                if change.change_type
                in (
                    ClauseChangeType.MODIFIED.value,
                    ClauseChangeType.RECLASSIFIED.value,
                    ClauseChangeType.ADDED.value,
                )
                and change.target_clause_id
            ]
            comparison.affected_clause_ids = json.dumps(affected_target_ids)

            if request.reanalyze_target and affected_target_ids:
                if self.risk_analysis is None:
                    warnings.append("Affected-clause reanalysis is not configured.")
                else:
                    try:
                        await self.risk_analysis.analyze(
                            document_id=target_document.id,
                            db=db,
                            clause_ids=affected_target_ids,
                        )
                        comparison.reanalysis_performed = True
                    except Exception as exc:
                        warnings.append(
                            "Affected-clause reanalysis failed; comparison used the latest "
                            f"available analysis run: {exc}"
                        )
                        logger.warning(
                            "Affected-clause reanalysis failed for comparison %s: %s",
                            comparison.id,
                            exc,
                        )

            base_run = await self._latest_analysis_run(base_document.id, db)
            target_run = await self._latest_analysis_run(target_document.id, db)
            comparison.base_analysis_run_id = base_run.id if base_run else None
            comparison.target_analysis_run_id = target_run.id if target_run else None
            base_findings = await self._findings_for_run(
                base_run.id if base_run else None, db
            )
            target_findings = await self._findings_for_run(
                target_run.id if target_run else None, db
            )
            finding_changes = self._finding_changes(
                comparison.id, base_findings, target_findings
            )
            finding_counts = {item.value: 0 for item in FindingChangeType}
            for change in finding_changes:
                finding_counts[change.change_type] += 1
                db.add(change)
            comparison.findings_new = finding_counts[FindingChangeType.NEW.value]
            comparison.findings_resolved = finding_counts[FindingChangeType.RESOLVED.value]
            comparison.findings_persisted = finding_counts[
                FindingChangeType.PERSISTED.value
            ]
            comparison.findings_severity_changed = finding_counts[
                FindingChangeType.SEVERITY_CHANGED.value
            ]

            comparison.warnings = json.dumps(warnings) if warnings else None
            comparison.status = (
                ComparisonStatus.PARTIAL if warnings else ComparisonStatus.COMPLETED
            )
            comparison.completed_at = datetime.now(UTC)
            await db.commit()
            await db.refresh(comparison)
            logger.info(
                "Contract comparison completed: id=%s base=%s target=%s clauses=%s findings=%s",
                comparison.id,
                base_document.id,
                target_document.id,
                len(changes),
                len(finding_changes),
            )
            return await self.get(comparison.id, db)
        except Exception as exc:
            comparison.status = ComparisonStatus.FAILED
            comparison.error_message = str(exc)
            comparison.warnings = json.dumps(warnings) if warnings else None
            comparison.completed_at = datetime.now(UTC)
            await db.commit()
            logger.exception("Contract comparison failed for %s", comparison.id)
            raise

    async def get(self, comparison_id: str, db: AsyncSession) -> ContractComparison:
        comparison = (
            await db.execute(
                select(ContractComparison)
                .options(
                    selectinload(ContractComparison.clause_changes),
                    selectinload(ContractComparison.finding_changes),
                )
                .where(ContractComparison.id == comparison_id)
            )
        ).scalar_one_or_none()
        if not comparison:
            raise NotFoundError(f"Comparison '{comparison_id}' not found.")
        return comparison

    async def list(
        self,
        db: AsyncSession,
        document_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ContractComparison], int]:
        filters = []
        if document_id:
            filters.append(
                (ContractComparison.base_document_id == document_id)
                | (ContractComparison.target_document_id == document_id)
            )
        total = (
            await db.execute(
                select(func.count(ContractComparison.id)).where(*filters)
            )
        ).scalar() or 0
        comparisons = list(
            (
                await db.execute(
                    select(ContractComparison)
                    .options(
                        selectinload(ContractComparison.clause_changes),
                        selectinload(ContractComparison.finding_changes),
                    )
                    .where(*filters)
                    .order_by(ContractComparison.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return comparisons, total


__all__ = [
    "ContractComparisonService",
    "ClauseMatch",
    "FindingKey",
    "_parse_json_list",
]
