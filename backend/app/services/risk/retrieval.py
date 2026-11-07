import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.embeddings.base import EmbeddingProvider
from app.core.errors import AppException, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import (
    Clause,
    Document,
    DocumentStatus,
    ExtractionRunStatus,
    Policy,
    PolicyRetrievalEvidence,
    PolicyRetrievalRun,
)
from app.schemas.clause import ClauseCategory, normalize_category
from app.schemas.risk import PolicyCoverageStatus, PolicyRetrievalRequest
from app.services.vector.qdrant_service import QdrantVectorService, ScoredVectorMatch

logger = get_logger("contractguard.risk.retrieval")

_CATEGORY_QUERY_LABELS: dict[ClauseCategory, str] = {
    ClauseCategory.LIABILITY: "limitation of liability liability caps aggregate liability",
    ClauseCategory.INDEMNITY: "indemnity indemnification third party claims",
    ClauseCategory.TERMINATION: "termination notice period termination for convenience",
    ClauseCategory.RENEWAL: "renewal automatic renewal renewal term",
    ClauseCategory.PAYMENT: "payment terms invoices fees payment period",
    ClauseCategory.CONFIDENTIALITY: "confidentiality confidential information non-disclosure",
    ClauseCategory.INTELLECTUAL_PROPERTY: "intellectual property ownership licence assignment",
    ClauseCategory.DATA_PROTECTION: "data protection personal data privacy gdpr",
    ClauseCategory.WARRANTIES: "warranties representations warranties",
    ClauseCategory.GOVERNING_LAW: "governing law choice of law jurisdiction",
    ClauseCategory.DISPUTE_RESOLUTION: "dispute resolution arbitration courts",
    ClauseCategory.MISCELLANEOUS: "contract policy requirements",
}


@dataclass
class RetrievedEvidence:
    chunk_id: str
    source_identifier: str
    policy_id: str
    policy_name: str
    policy_version: str
    policy_status: str
    category: str | None
    section_heading: str | None
    page_number: int
    start_char_offset: int
    end_char_offset: int
    text: str
    similarity_score: float
    query: str
    rank: int = 0


@dataclass
class ClauseRetrieval:
    clause: Clause
    queries: list[str]
    evidence: list[RetrievedEvidence] = field(default_factory=list)
    coverage_status: PolicyCoverageStatus = PolicyCoverageStatus.MISSING
    coverage_note: str = ""


class PolicyRetrievalService:
    """Retrieves active policy evidence for extracted clauses with explicit coverage gaps."""

    def __init__(
        self,
        vector_service: QdrantVectorService,
        embedding_provider: EmbeddingProvider,
        settings: Settings,
    ) -> None:
        self.vector_service = vector_service
        self.embedding_provider = embedding_provider
        self.settings = settings
        self.collection_name = settings.qdrant_policy_collection

    async def _get_document(self, document_id: str, db: AsyncSession) -> Document:
        result = await db.execute(select(Document).where(Document.id == document_id))
        document = result.scalar_one_or_none()
        if not document:
            raise NotFoundError(f"Document with ID '{document_id}' not found.")
        if document.status != DocumentStatus.COMPLETED:
            raise ValidationError(
                f"Document '{document_id}' is in status '{document.status}' and cannot be used "
                "for policy retrieval. Only completed documents are supported."
            )
        return document

    def _build_queries(self, clause: Clause) -> list[str]:
        category, _ = normalize_category(clause.category)
        label = _CATEGORY_QUERY_LABELS.get(category, clause.category)
        meaning = f"{clause.normalized_summary}\n{clause.source_text}".strip()
        category_query = f"{label} company policy requirement"
        meaning_query = (
            f"Which company policy requirements apply to this contract clause?\n{meaning}"
        )[:2000]
        queries = [category_query]
        if meaning_query != category_query:
            queries.append(meaning_query)
        return queries

    async def _eligible_policies(
        self,
        request: PolicyRetrievalRequest,
        db: AsyncSession,
    ) -> tuple[dict[str, Policy], list[str]]:
        statuses = request.policy_statuses or self.settings.policy_retrieval_statuses
        stmt = select(Policy).where(Policy.status.in_(statuses))
        if request.policy_versions:
            stmt = stmt.where(Policy.version.in_(request.policy_versions))
        policies = list((await db.execute(stmt)).scalars().all())
        allowed = {policy.id: policy for policy in policies}
        versions = sorted({policy.version for policy in policies})
        return allowed, versions

    def _to_evidence(
        self, match: ScoredVectorMatch, policy: Policy, query: str
    ) -> RetrievedEvidence | None:
        payload = match.payload or {}
        chunk_id = payload.get("chunk_id")
        text = payload.get("text")
        if not chunk_id or not text:
            return None
        return RetrievedEvidence(
            chunk_id=str(chunk_id),
            source_identifier=str(payload.get("source_identifier", f"chunk:{match.id}")),
            policy_id=policy.id,
            policy_name=policy.name,
            policy_version=policy.version,
            policy_status=policy.status,
            category=payload.get("category"),
            section_heading=payload.get("section_heading"),
            page_number=int(payload.get("page_number", 1)),
            start_char_offset=int(payload.get("start_char_offset", 0)),
            end_char_offset=int(payload.get("end_char_offset", 0)),
            text=str(text),
            similarity_score=round(float(match.score), 6),
            query=query,
        )

    async def _search_clause(
        self,
        clause: Clause,
        allowed_policies: dict[str, Policy],
        warnings: list[str],
    ) -> ClauseRetrieval:
        queries = self._build_queries(clause)
        collected: dict[str, RetrievedEvidence] = {}

        for query in queries:
            try:
                vector = await self.embedding_provider.embed_text(query)
                matches = await self.vector_service.search(
                    collection_name=self.collection_name,
                    query_vector=vector,
                    limit=max(self.settings.policy_retrieval_limit * 2, 1),
                    min_score=self.settings.policy_retrieval_min_similarity,
                )
            except AppException:
                raise
            except Exception as exc:
                warnings.append(
                    f"Retrieval failed for clause {clause.id} with query {query!r}: {exc}"
                )
                logger.warning("Policy retrieval failed for clause %s: %s", clause.id, exc)
                continue

            for match in matches:
                policy_id = (match.payload or {}).get("policy_id")
                policy = allowed_policies.get(str(policy_id)) if policy_id else None
                if policy is None:
                    continue
                evidence = self._to_evidence(match, policy, query)
                if evidence is None:
                    continue
                existing = collected.get(evidence.chunk_id)
                if existing is None or evidence.similarity_score > existing.similarity_score:
                    collected[evidence.chunk_id] = evidence

        ordered = sorted(
            collected.values(),
            key=lambda item: (-item.similarity_score, item.source_identifier),
        )[: self.settings.policy_retrieval_limit]
        for index, item in enumerate(ordered, start=1):
            item.rank = index

        if ordered:
            coverage = PolicyCoverageStatus.COVERED
            note = ""
        else:
            coverage = PolicyCoverageStatus.MISSING
            note = (
                "No active policy evidence matched this clause. This is a retrieval gap, "
                "not a finding of compliance or non-compliance."
            )
        return ClauseRetrieval(
            clause=clause,
            queries=queries,
            evidence=ordered,
            coverage_status=coverage,
            coverage_note=note,
        )

    async def retrieve(
        self,
        document_id: str,
        db: AsyncSession,
        request: PolicyRetrievalRequest | None = None,
    ) -> tuple[PolicyRetrievalRun, list[ClauseRetrieval]]:
        request = request or PolicyRetrievalRequest()
        await self._get_document(document_id, db)

        clauses = list(
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
        if not clauses:
            raise ValidationError(
                f"Document '{document_id}' has no extracted clauses. Run clause extraction first."
            )

        allowed_policies, versions = await self._eligible_policies(request, db)
        statuses = request.policy_statuses or self.settings.policy_retrieval_statuses
        warnings: list[str] = []
        if not allowed_policies:
            warnings.append(
                "No policies matched the requested status/version filters; all clauses will "
                "be marked as missing policy coverage."
            )

        run = PolicyRetrievalRun(
            id=str(uuid.uuid4()),
            document_id=document_id,
            status=ExtractionRunStatus.RUNNING,
            embedding_provider=self.embedding_provider.model_name,
            embedding_model=self.embedding_provider.model_name,
            clauses_processed=0,
            evidence_count=0,
            missing_coverage_count=0,
            policy_statuses=json.dumps(statuses),
            policy_versions=json.dumps(versions),
            created_at=datetime.now(UTC),
        )
        db.add(run)
        await db.flush()

        results: list[ClauseRetrieval] = []
        try:
            for clause in clauses:
                result = await self._search_clause(clause, allowed_policies, warnings)
                results.append(result)
                for evidence in result.evidence:
                    db.add(
                        PolicyRetrievalEvidence(
                            retrieval_run_id=run.id,
                            document_id=document_id,
                            clause_id=clause.id,
                            policy_id=evidence.policy_id,
                            policy_name=evidence.policy_name,
                            policy_version=evidence.policy_version,
                            policy_status=evidence.policy_status,
                            chunk_id=evidence.chunk_id,
                            source_identifier=evidence.source_identifier,
                            category=evidence.category,
                            section_heading=evidence.section_heading,
                            page_number=evidence.page_number,
                            start_char_offset=evidence.start_char_offset,
                            end_char_offset=evidence.end_char_offset,
                            text=evidence.text,
                            similarity_score=evidence.similarity_score,
                            query=evidence.query,
                            rank=evidence.rank,
                        )
                    )

            run.clauses_processed = len(results)
            run.evidence_count = sum(len(result.evidence) for result in results)
            run.missing_coverage_count = sum(
                1 for result in results if result.coverage_status == PolicyCoverageStatus.MISSING
            )
            run.warnings = json.dumps(warnings) if warnings else None
            run.status = (
                ExtractionRunStatus.PARTIAL if warnings else ExtractionRunStatus.COMPLETED
            )
            run.completed_at = datetime.now(UTC)
            await db.commit()

            logger.info(
                "Policy retrieval completed for document %s: run=%s clauses=%s evidence=%s missing=%s",
                document_id,
                run.id,
                run.clauses_processed,
                run.evidence_count,
                run.missing_coverage_count,
            )
            return run, results
        except Exception as exc:
            run.status = ExtractionRunStatus.FAILED
            run.error_message = str(exc)
            run.warnings = json.dumps(warnings) if warnings else None
            run.completed_at = datetime.now(UTC)
            await db.commit()
            logger.exception("Policy retrieval failed for document %s", document_id)
            if isinstance(exc, AppException):
                raise
            raise AppException(
                f"Policy retrieval failed: {exc}", code="POLICY_RETRIEVAL_FAILED"
            ) from exc

    async def get_run(
        self, document_id: str, run_id: str, db: AsyncSession
    ) -> PolicyRetrievalRun:
        await self._get_document(document_id, db)
        stmt = select(PolicyRetrievalRun).where(
            PolicyRetrievalRun.id == run_id,
            PolicyRetrievalRun.document_id == document_id,
        )
        run = (await db.execute(stmt)).scalar_one_or_none()
        if not run:
            raise NotFoundError(
                f"Policy retrieval run '{run_id}' not found for document '{document_id}'."
            )
        return run

    async def get_latest_run(
        self, document_id: str, db: AsyncSession
    ) -> PolicyRetrievalRun:
        await self._get_document(document_id, db)
        stmt = (
            select(PolicyRetrievalRun)
            .where(
                PolicyRetrievalRun.document_id == document_id,
                PolicyRetrievalRun.status.in_(
                    [ExtractionRunStatus.COMPLETED, ExtractionRunStatus.PARTIAL]
                ),
            )
            .order_by(PolicyRetrievalRun.created_at.desc())
            .limit(1)
        )
        run = (await db.execute(stmt)).scalar_one_or_none()
        if not run:
            raise ValidationError(
                f"Document '{document_id}' has no completed policy retrieval run. "
                "Run policy retrieval first."
            )
        return run

    async def list_runs(
        self, document_id: str, db: AsyncSession, limit: int = 20, offset: int = 0
    ) -> tuple[list[PolicyRetrievalRun], int]:
        await self._get_document(document_id, db)
        count_stmt = select(func.count(PolicyRetrievalRun.id)).where(
            PolicyRetrievalRun.document_id == document_id
        )
        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = (
            select(PolicyRetrievalRun)
            .where(PolicyRetrievalRun.document_id == document_id)
            .order_by(PolicyRetrievalRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        runs = list((await db.execute(stmt)).scalars().all())
        return runs, total

    async def delete_runs_for_document(self, document_id: str, db: AsyncSession) -> None:
        await db.execute(
            delete(PolicyRetrievalRun).where(PolicyRetrievalRun.document_id == document_id)
        )
