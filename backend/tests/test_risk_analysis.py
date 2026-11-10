import io
import re

import docx
import pytest
from httpx import AsyncClient

from app.core.llm.factory import get_llm_provider
from app.core.llm.mock import MockLLMProvider
from app.main import app
from app.services.vector.qdrant_service import QdrantVectorService, ScoredVectorMatch
from tests.conftest import ADMIN_AUTH_HEADERS

LIABILITY_UNLIMITED = (
    "The vendor's aggregate liability under this Agreement shall be unlimited "
    "for any breach or indemnity obligation."
)
LIABILITY_POLICY = (
    "Company requires all vendor contracts to cap aggregate liability at twelve (12) "
    "months of fees paid under the agreement."
)
TERMINATION_SHORT = (
    "Company may terminate this Agreement for convenience with ten (10) days' "
    "prior written notice to the vendor."
)
TERMINATION_POLICY = (
    "Vendor agreements must provide at least thirty (30) days' prior written notice "
    "before termination for convenience."
)
PAYMENT_LONG = (
    "Customer shall pay all undisputed invoices within ninety (90) days of receipt."
)
PAYMENT_POLICY = (
    "All vendor invoices must be paid within thirty (30) days of receipt."
)
CONFIDENTIALITY_TEXT = (
    "The vendor may disclose Confidential Information to subcontractors without "
    "prior written approval from the Company."
)
CONFIDENTIALITY_POLICY = (
    "Confidential Information may only be disclosed to subcontractors with prior "
    "written approval from the Company."
)
DATA_PROTECTION_POLICY = (
    "All vendor contracts must include data protection obligations for personal data, "
    "including prompt notice of any data breach."
)


class InMemoryVectorStore:
    def __init__(self):
        self.collections: dict[str, int] = {}
        self.points: dict[str, list[dict]] = {}

    async def ensure_collection(self, collection_name: str, dimension: int):
        if collection_name in self.collections:
            if self.collections[collection_name] != dimension:
                from app.core.errors import ServiceUnavailableError

                raise ServiceUnavailableError("Vector collection dimension mismatch.")
        self.collections[collection_name] = dimension
        self.points.setdefault(collection_name, [])

    async def upsert_points(self, collection_name: str, points: list):
        self.points.setdefault(collection_name, [])
        for point in points:
            self.points[collection_name].append(
                {"id": str(point.id), "vector": point.vector, "payload": point.payload}
            )

    async def delete_by_policy_id(self, collection_name: str, policy_id: str):
        if collection_name in self.points:
            self.points[collection_name] = [
                point
                for point in self.points[collection_name]
                if point["payload"].get("policy_id") != policy_id
            ]

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        policy_id: str | None = None,
        category: str | None = None,
        min_score: float = 0.0,
    ) -> list[ScoredVectorMatch]:
        scored = []
        for point in self.points.get(collection_name, []):
            payload = point["payload"]
            if policy_id and payload.get("policy_id") != policy_id:
                continue
            if category and payload.get("category") != category:
                continue
            dot = sum(
                a * b for a, b in zip(query_vector, point["vector"], strict=True)
            )
            if dot >= min_score:
                scored.append(
                    ScoredVectorMatch(id=point["id"], score=dot, payload=payload)
                )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]


@pytest.fixture(autouse=True)
def mock_qdrant_service(monkeypatch):
    in_memory = InMemoryVectorStore()
    monkeypatch.setattr(QdrantVectorService, "ensure_collection", in_memory.ensure_collection)
    monkeypatch.setattr(QdrantVectorService, "upsert_points", in_memory.upsert_points)
    monkeypatch.setattr(
        QdrantVectorService, "delete_by_policy_id", in_memory.delete_by_policy_id
    )
    monkeypatch.setattr(QdrantVectorService, "search", in_memory.search)


def create_contract_docx(paragraphs: list[tuple[str, str]]) -> bytes:
    document = docx.Document()
    document.add_heading("MASTER SERVICES AGREEMENT", level=0)
    for style, text in paragraphs:
        if style == "heading":
            document.add_heading(text, level=1)
        else:
            document.add_paragraph(text)
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


async def upload_contract(
    auth_client: AsyncClient, paragraphs: list[tuple[str, str]]
) -> str:
    files = {
        "file": (
            "synthetic_contract.docx",
            create_contract_docx(paragraphs),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    response = await auth_client.post("/api/v1/documents", files=files)
    assert response.status_code == 201, response.text
    return response.json()["document"]["id"]


async def create_policy(
    auth_client: AsyncClient,
    name: str,
    text: str,
    category: str = "Legal",
    version: str = "1.0.0",
) -> str:
    response = await auth_client.post(
        "/api/v1/policies",
        json={"name": name, "version": version, "category": category, "text_content": text},
        headers=ADMIN_AUTH_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def clause_candidate(category: str, text: str, summary: str) -> dict:
    return {
        "category": category,
        "source_text": text,
        "summary": summary,
        "source_chunk_id": "exc:test:0",
        "confidence": 0.9,
    }


async def extract_clauses(
    auth_client: AsyncClient, document_id: str, candidates: list[dict]
) -> dict:
    provider = MockLLMProvider([{"clauses": candidates}], model_name="mock-extractor")
    app.dependency_overrides[get_llm_provider] = lambda: provider
    response = await auth_client.post(
        f"/api/v1/documents/{document_id}/extract-clauses"
    )
    assert response.status_code == 201, response.text
    return response.json()


async def retrieve_policies(
    auth_client: AsyncClient, document_id: str, body: dict | None = None
) -> dict:
    response = await auth_client.post(
        f"/api/v1/documents/{document_id}/retrieve-policies", json=body
    )
    assert response.status_code == 201, response.text
    return response.json()


async def analyze_risk(
    auth_client: AsyncClient, document_id: str, body: dict | None = None
) -> dict:
    response = await auth_client.post(
        f"/api/v1/documents/{document_id}/analyze-risk", json=body
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_unlimited_liability_is_critical_policy_deviation(
    auth_client: AsyncClient,
):
    policy_id = await create_policy(
        auth_client, "Vendor Liability Policy", LIABILITY_POLICY, category="liability"
    )
    document_id = await upload_contract(
        auth_client,
        [
            ("heading", "1. LIMITATION OF LIABILITY"),
            ("paragraph", LIABILITY_UNLIMITED),
        ],
    )
    await extract_clauses(
        auth_client,
        document_id,
        [clause_candidate("liability", LIABILITY_UNLIMITED, "Unlimited vendor liability.")],
    )

    retrieval = await retrieve_policies(auth_client, document_id)
    assert retrieval["run"]["status"] == "completed"
    assert retrieval["clauses"][0]["coverage_status"] == "covered"
    evidence = retrieval["clauses"][0]["evidence"][0]
    assert evidence["policy_id"] == policy_id
    assert evidence["policy_version"] == "1.0.0"
    assert evidence["policy_status"] == "active"

    analysis = await analyze_risk(auth_client, document_id)
    assert analysis["run"]["status"] == "completed"
    finding = next(
        item for item in analysis["findings"] if item["rule_id"] == "liability_unlimited"
    )
    assert finding["finding_type"] == "policy_deviation"
    assert finding["severity"] == "critical"
    assert finding["severity_basis"] == "policy_rule"
    assert finding["analysis_model"] == "policy-rule-engine"
    assert finding["confidence"] is None
    assert finding["contract_quote"] == LIABILITY_UNLIMITED
    assert finding["policy_quote"] == LIABILITY_POLICY
    assert finding["policy_id"] == policy_id
    assert finding["policy_source_reference"] == evidence["source_identifier"]

    listed = await auth_client.get(f"/api/v1/documents/{document_id}/findings")
    assert listed.status_code == 200
    assert listed.json()["total"] == len(analysis["findings"])

    detail = await auth_client.get(
        f"/api/v1/documents/{document_id}/findings/{finding['finding_id']}"
    )
    assert detail.status_code == 200
    assert detail.json()["explanation"] == finding["explanation"]

    runs = await auth_client.get(f"/api/v1/documents/{document_id}/analysis-runs")
    assert runs.status_code == 200
    assert runs.json()["total"] == 1


@pytest.mark.asyncio
async def test_termination_notice_shortfall(auth_client: AsyncClient):
    await create_policy(
        auth_client,
        "Termination Notice Policy",
        TERMINATION_POLICY,
        category="termination",
    )
    document_id = await upload_contract(
        auth_client,
        [("heading", "2. TERMINATION"), ("paragraph", TERMINATION_SHORT)],
    )
    await extract_clauses(
        auth_client,
        document_id,
        [clause_candidate("termination", TERMINATION_SHORT, "Short termination notice.")],
    )
    await retrieve_policies(auth_client, document_id)
    analysis = await analyze_risk(auth_client, document_id)

    finding = next(
        item
        for item in analysis["findings"]
        if item["rule_id"] == "termination_notice_shortfall"
    )
    assert finding["severity"] == "high"
    assert finding["risk_category"] == "termination"
    assert "10" in finding["explanation"]
    assert "30" in finding["explanation"]


@pytest.mark.asyncio
async def test_payment_period_deviation(auth_client: AsyncClient):
    await create_policy(
        auth_client, "Payment Terms Policy", PAYMENT_POLICY, category="payment"
    )
    document_id = await upload_contract(
        auth_client,
        [("heading", "3. PAYMENT TERMS"), ("paragraph", PAYMENT_LONG)],
    )
    await extract_clauses(
        auth_client,
        document_id,
        [clause_candidate("payment", PAYMENT_LONG, "Ninety-day payment terms.")],
    )
    await retrieve_policies(auth_client, document_id)
    analysis = await analyze_risk(auth_client, document_id)

    finding = next(
        item
        for item in analysis["findings"]
        if item["rule_id"] == "payment_period_exceeds_policy"
    )
    assert finding["severity"] == "medium"
    assert finding["risk_category"] == "payment"
    assert "90" in finding["explanation"]
    assert "30" in finding["explanation"]


@pytest.mark.asyncio
async def test_missing_data_protection_clause_is_flagged(auth_client: AsyncClient):
    await create_policy(
        auth_client,
        "Data Protection Policy",
        DATA_PROTECTION_POLICY,
        category="data_protection",
    )
    document_id = await upload_contract(
        auth_client,
        [("heading", "4. LIABILITY"), ("paragraph", LIABILITY_UNLIMITED)],
    )
    await extract_clauses(
        auth_client,
        document_id,
        [clause_candidate("liability", LIABILITY_UNLIMITED, "Liability clause.")],
    )
    await retrieve_policies(auth_client, document_id)
    analysis = await analyze_risk(auth_client, document_id)

    missing = [
        item for item in analysis["findings"] if item["finding_type"] == "missing_clause"
    ]
    assert len(missing) == 1
    finding = missing[0]
    assert finding["risk_category"] == "data_protection"
    assert finding["severity"] == "high"
    assert finding["severity_basis"] == "configured_requirement"
    assert finding["clause_id"] is None
    assert finding["policy_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_missing_policy_evidence_is_explicit(auth_client: AsyncClient):
    document_id = await upload_contract(
        auth_client,
        [
            ("heading", "5. INDEMNITY"),
            (
                "paragraph",
                "The vendor shall indemnify the Company against all third-party claims.",
            ),
        ],
    )
    await extract_clauses(
        auth_client,
        document_id,
        [
            clause_candidate(
                "indemnity",
                "The vendor shall indemnify the Company against all third-party claims.",
                "Vendor indemnity.",
            )
        ],
    )
    retrieval = await retrieve_policies(auth_client, document_id)
    assert retrieval["run"]["missing_coverage_count"] == 1
    assert retrieval["clauses"][0]["coverage_status"] == "missing"
    assert "not a finding of compliance" in retrieval["clauses"][0]["coverage_note"]

    analysis = await analyze_risk(auth_client, document_id)
    finding = next(
        item
        for item in analysis["findings"]
        if item["finding_type"] == "missing_evidence"
    )
    assert finding["severity"] == "informational"
    assert finding["severity_basis"] == "retrieval_gap"
    assert finding["policy_quote"] is None


@pytest.mark.asyncio
async def test_archived_policy_is_excluded_from_retrieval(auth_client: AsyncClient):
    policy_id = await create_policy(
        auth_client, "Archived Liability Policy", LIABILITY_POLICY, category="liability"
    )
    update = await auth_client.put(
        f"/api/v1/policies/{policy_id}",
        json={"status": "archived"},
        headers=ADMIN_AUTH_HEADERS,
    )
    assert update.status_code == 200, update.text

    document_id = await upload_contract(
        auth_client,
        [("heading", "6. LIABILITY"), ("paragraph", LIABILITY_UNLIMITED)],
    )
    await extract_clauses(
        auth_client,
        document_id,
        [clause_candidate("liability", LIABILITY_UNLIMITED, "Liability clause.")],
    )
    retrieval = await retrieve_policies(auth_client, document_id)
    assert retrieval["run"]["missing_coverage_count"] == 1
    assert retrieval["clauses"][0]["evidence"] == []


@pytest.mark.asyncio
async def test_version_filter_limits_policy_evidence(auth_client: AsyncClient):
    old_id = await create_policy(
        auth_client,
        "Liability Policy",
        LIABILITY_POLICY,
        category="liability",
        version="1.0.0",
    )
    await create_policy(
        auth_client,
        "Liability Policy",
        LIABILITY_POLICY,
        category="liability",
        version="2.0.0",
    )
    document_id = await upload_contract(
        auth_client,
        [("heading", "7. LIABILITY"), ("paragraph", LIABILITY_UNLIMITED)],
    )
    await extract_clauses(
        auth_client,
        document_id,
        [clause_candidate("liability", LIABILITY_UNLIMITED, "Liability clause.")],
    )
    retrieval = await retrieve_policies(
        auth_client, document_id, {"policy_versions": ["1.0.0"]}
    )
    assert retrieval["run"]["policy_versions"] == ["1.0.0"]
    evidence = retrieval["clauses"][0]["evidence"]
    assert evidence
    assert all(item["policy_id"] == old_id for item in evidence)
    assert all(item["policy_version"] == "1.0.0" for item in evidence)


@pytest.mark.asyncio
async def test_model_generated_deviation_requires_verbatim_citations(
    auth_client: AsyncClient,
):
    await create_policy(
        auth_client,
        "Confidentiality Policy",
        CONFIDENTIALITY_POLICY,
        category="confidentiality",
    )
    document_id = await upload_contract(
        auth_client,
        [("heading", "8. CONFIDENTIALITY"), ("paragraph", CONFIDENTIALITY_TEXT)],
    )
    await extract_clauses(
        auth_client,
        document_id,
        [
            clause_candidate(
                "confidentiality",
                CONFIDENTIALITY_TEXT,
                "Subcontractor disclosure without approval.",
            )
        ],
    )

    def model_response(**kwargs):
        match = re.search(r'chunk_id="([^"]+)"', kwargs["user_prompt"])
        assert match is not None
        return {
            "findings": [
                {
                    "policy_chunk_id": match.group(1),
                    "finding_type": "policy_deviation",
                    "contract_quote": CONFIDENTIALITY_TEXT,
                    "policy_quote": CONFIDENTIALITY_POLICY,
                    "explanation": "The contract allows disclosure without prior approval.",
                    "suggested_question": "Can prior written approval be required?",
                    "confidence": 0.87,
                }
            ]
        }

    provider = MockLLMProvider([model_response], model_name="mock-risk-analyzer")
    # Replace the extraction call with a fresh provider sequence after extraction.
    await retrieve_policies(auth_client, document_id)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    analysis = await analyze_risk(auth_client, document_id)

    finding = next(
        item for item in analysis["findings"] if item["severity_basis"] == "model_analysis"
    )
    assert finding["finding_type"] == "policy_deviation"
    assert finding["severity"] == "medium"
    assert finding["analysis_model"] == "mock-risk-analyzer"
    assert finding["confidence"] == 0.87
    assert finding["contract_quote"] == CONFIDENTIALITY_TEXT
    assert finding["policy_quote"] == CONFIDENTIALITY_POLICY
    assert finding["policy_source_reference"]
    assert provider.calls and "untrusted" in provider.calls[0]["system_instruction"].lower()


@pytest.mark.asyncio
async def test_illegal_claim_is_sanitized(auth_client: AsyncClient):
    await create_policy(
        auth_client,
        "Confidentiality Policy",
        CONFIDENTIALITY_POLICY,
        category="confidentiality",
    )
    document_id = await upload_contract(
        auth_client,
        [("heading", "9. CONFIDENTIALITY"), ("paragraph", CONFIDENTIALITY_TEXT)],
    )
    await extract_clauses(
        auth_client,
        document_id,
        [
            clause_candidate(
                "confidentiality",
                CONFIDENTIALITY_TEXT,
                "Subcontractor disclosure without approval.",
            )
        ],
    )

    def model_response(**kwargs):
        match = re.search(r'chunk_id="([^"]+)"', kwargs["user_prompt"])
        return {
            "findings": [
                {
                    "policy_chunk_id": match.group(1),
                    "finding_type": "possible_legal_concern",
                    "contract_quote": CONFIDENTIALITY_TEXT,
                    "policy_quote": CONFIDENTIALITY_POLICY,
                    "explanation": "This clause is illegal and unenforceable.",
                    "suggested_question": "Is this illegal?",
                }
            ]
        }

    provider = MockLLMProvider([model_response], model_name="mock-risk-analyzer")
    await retrieve_policies(auth_client, document_id)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    analysis = await analyze_risk(auth_client, document_id)

    finding = next(
        item
        for item in analysis["findings"]
        if item["finding_type"] == "possible_legal_concern"
    )
    assert finding["severity"] == "informational"
    assert finding["severity_basis"] == "model_analysis"
    assert "illegal" not in finding["explanation"].lower()
    assert "unenforceable" not in finding["explanation"].lower()
    assert "qualified human review" in finding["explanation"].lower()
