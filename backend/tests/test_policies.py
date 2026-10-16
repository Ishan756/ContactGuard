import io
import docx
import fitz
from httpx import AsyncClient
import pytest
from app.db.models import Policy
from app.services.vector.qdrant_service import QdrantVectorService, ScoredVectorMatch


class InMemoryVectorStore:
    """Mock in-memory vector store matching QdrantVectorService interface for isolated unit tests."""

    def __init__(self):
        self.collections: dict[str, int] = {}
        self.points: dict[str, list[dict]] = {}

    async def ensure_collection(self, collection_name: str, dimension: int):
        if collection_name in self.collections:
            if self.collections[collection_name] != dimension:
                from app.core.errors import ServiceUnavailableError
                raise ServiceUnavailableError(
                    f"Vector collection dimension mismatch: expected {dimension}, found {self.collections[collection_name]}."
                )
        self.collections[collection_name] = dimension
        if collection_name not in self.points:
            self.points[collection_name] = []

    async def upsert_points(self, collection_name: str, points: list):
        if collection_name not in self.points:
            self.points[collection_name] = []
        for p in points:
            self.points[collection_name].append({
                "id": str(p.id),
                "vector": p.vector,
                "payload": p.payload,
            })

    async def delete_by_policy_id(self, collection_name: str, policy_id: str):
        if collection_name in self.points:
            self.points[collection_name] = [
                pt for pt in self.points[collection_name]
                if pt["payload"].get("policy_id") != policy_id
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
        pts = self.points.get(collection_name, [])
        scored = []
        for pt in pts:
            payload = pt["payload"]
            if policy_id and payload.get("policy_id") != policy_id:
                continue
            if category and payload.get("category") != category:
                continue

            # Compute cosine similarity
            dot = sum(a * b for a, b in zip(query_vector, pt["vector"], strict=True))
            if dot >= min_score:
                scored.append(ScoredVectorMatch(id=pt["id"], score=dot, payload=payload))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:limit]


@pytest.fixture(autouse=True)
def mock_qdrant_service(monkeypatch):
    """Patch QdrantVectorService with hermetic in-memory store for unit test suite."""
    in_memory = InMemoryVectorStore()

    monkeypatch.setattr(
        QdrantVectorService,
        "ensure_collection",
        in_memory.ensure_collection,
    )
    monkeypatch.setattr(
        QdrantVectorService,
        "upsert_points",
        in_memory.upsert_points,
    )
    monkeypatch.setattr(
        QdrantVectorService,
        "delete_by_policy_id",
        in_memory.delete_by_policy_id,
    )
    monkeypatch.setattr(
        QdrantVectorService,
        "search",
        in_memory.search,
    )


@pytest.mark.asyncio
async def test_create_policy_and_retrieve_passages(async_client: AsyncClient):
    """Test policy creation, automatic vector indexing, and semantic retrieval."""
    policy_payload = {
        "name": "Standard Vendor Liability Policy",
        "version": "1.0.0",
        "category": "Liability",
        "description": "Rules on liability caps and waivers",
        "text_content": (
            "SECTION 1. LIABILITY CAPS.\n"
            "Company requires all vendor contracts to cap aggregate liability at 12 months of fees paid.\n\n"
            "SECTION 2. INDEMNITY COVERAGE.\n"
            "Vendor must indemnify Company against third-party intellectual property infringement claims."
        ),
    }

    create_resp = await async_client.post("/api/v1/policies", json=policy_payload)
    assert create_resp.status_code == 201
    policy_data = create_resp.json()
    assert policy_data["name"] == "Standard Vendor Liability Policy"
    assert policy_data["version"] == "1.0.0"
    assert policy_data["total_chunks"] >= 2
    policy_id = policy_data["id"]

    # 1. Search matching liability cap
    search_payload = {
        "query": "The vendor proposes an unlimited liability cap for any breaches.",
        "limit": 3,
    }
    search_resp = await async_client.post("/api/v1/policies/search", json=search_payload)
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total_results"] >= 1
    top_hit = search_data["results"][0]
    assert top_hit["policy_id"] == policy_id
    assert "liability" in top_hit["text"].lower()
    assert top_hit["similarity_score"] > 0.0
    assert "factual legal compliance" in top_hit["factual_confidence_note"].lower()

    # 2. Get policy by ID
    get_resp = await async_client.get(f"/api/v1/policies/{policy_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == policy_id


@pytest.mark.asyncio
async def test_prevent_duplicate_policy_ingestion(async_client: AsyncClient):
    """Test that creating a policy with identical name and version is rejected with 422."""
    policy_payload = {
        "name": "Duplicate Policy Test",
        "version": "2.1.0",
        "category": "Compliance",
        "text_content": "Company data must remain stored in US geographic regions.",
    }
    resp1 = await async_client.post("/api/v1/policies", json=policy_payload)
    assert resp1.status_code == 201

    resp2 = await async_client.post("/api/v1/policies", json=policy_payload)
    assert resp2.status_code == 422
    assert "already exists" in resp2.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_update_policy_clears_stale_vectors(async_client: AsyncClient):
    """Test updating policy text re-indexes and removes old stale vectors."""
    initial = {
        "name": "Mutable IP Policy",
        "version": "1.0.0",
        "category": "IP",
        "text_content": "Initial rule regarding patent rights transfer.",
    }
    create_resp = await async_client.post("/api/v1/policies", json=initial)
    policy_id = create_resp.json()["id"]

    # Update with new content
    update_payload = {
        "name": "Mutable IP Policy",
        "text_content": "Revised rule: All trade secrets and copyright remain with Company.",
    }
    put_resp = await async_client.put(f"/api/v1/policies/{policy_id}", json=update_payload)
    assert put_resp.status_code == 200

    # Search for trade secrets
    search_resp = await async_client.post(
        "/api/v1/policies/search",
        json={"query": "trade secrets and copyrights", "policy_id": policy_id},
    )
    assert search_resp.status_code == 200
    res = search_resp.json()["results"]
    assert len(res) >= 1
    assert "trade secrets" in res[0]["text"].lower()


@pytest.mark.asyncio
async def test_delete_policy_purges_vectors(async_client: AsyncClient):
    """Test that deleting a policy removes it from database and clears Qdrant vectors."""
    payload = {
        "name": "Ephemeral Policy",
        "version": "1.0.0",
        "text_content": "Temporary guidelines on corporate travel reimbursements.",
    }
    create_resp = await async_client.post("/api/v1/policies", json=payload)
    policy_id = create_resp.json()["id"]

    del_resp = await async_client.delete(f"/api/v1/policies/{policy_id}")
    assert del_resp.status_code == 204

    # Confirm 404 on get
    get_resp = await async_client.get(f"/api/v1/policies/{policy_id}")
    assert get_resp.status_code == 404

    # Confirm search returns 0 results for this policy_id
    search_resp = await async_client.post(
        "/api/v1/policies/search",
        json={"query": "corporate travel reimbursements", "policy_id": policy_id},
    )
    assert search_resp.status_code == 200
    assert search_resp.json()["total_results"] == 0


@pytest.mark.asyncio
async def test_empty_search_query_rejected(async_client: AsyncClient):
    """Test that empty or whitespace query string is rejected with validation error."""
    resp = await async_client.post("/api/v1/policies/search", json={"query": "   "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_policy_from_docx_file(async_client: AsyncClient):
    """Test uploading a company policy as a DOCX document, indexing sections into vector store."""
    doc = docx.Document()
    doc.add_heading("CORPORATE DATA RETENTION POLICY", level=0)
    doc.add_heading("SECTION 1. STORAGE LIMITS", level=1)
    doc.add_paragraph("Customer personal data must not be retained longer than seven (7) years.")

    file_stream = io.BytesIO()
    doc.save(file_stream)
    docx_bytes = file_stream.getvalue()

    files = {
        "file": (
            "data_retention_policy.docx",
            docx_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    data = {
        "name": "Corporate Data Retention",
        "version": "1.0.0",
        "category": "Compliance",
        "description": "Retention timelines for customer PII",
    }

    upload_resp = await async_client.post("/api/v1/policies/upload", data=data, files=files)
    assert upload_resp.status_code == 201
    pol_id = upload_resp.json()["id"]

    # Search against policy
    search_resp = await async_client.post(
        "/api/v1/policies/search",
        json={"query": "How long can we retain personal customer data?", "policy_id": pol_id},
    )
    assert search_resp.status_code == 200
    results = search_resp.json()["results"]
    assert len(results) >= 1
    assert "seven (7) years" in results[0]["text"]
