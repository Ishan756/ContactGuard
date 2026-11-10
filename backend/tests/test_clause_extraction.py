import io
import time

import docx
import pytest
from httpx import AsyncClient

from app.api.v1.endpoints.clauses import get_clause_extraction_service
from app.core.config import Settings
from app.core.errors import ConfigurationError, ProviderTimeoutError
from app.core.llm.factory import create_llm_provider, get_llm_provider
from app.core.llm.gemini import GeminiLLMProvider
from app.core.llm.mock import MockLLMProvider
from app.main import app
from app.schemas.clause import ClauseCategory
from app.services.clause.service import CLAUSE_RESPONSE_SCHEMA, ClauseExtractionService

CONFIDENTIALITY_TEXT = (
    "Each party shall hold the other party's Confidential Information in strict confidence "
    "for a period of five (5) years and shall not disclose it to any third party."
)
LIABILITY_TEXT = (
    "In no event shall either party's aggregate liability exceed the total fees paid "
    "under this Agreement during the twelve (12) months preceding the claim."
)


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


async def reconstruct_document_text(auth_client: AsyncClient, document_id: str) -> str:
    response = await auth_client.get(
        f"/api/v1/documents/{document_id}/chunks?page=1&page_size=100"
    )
    assert response.status_code == 200
    return "\n\n".join(chunk["text"] for chunk in response.json()["chunks"])


def use_mock_provider(provider: MockLLMProvider) -> None:
    app.dependency_overrides[get_llm_provider] = lambda: provider


@pytest.mark.asyncio
async def test_valid_clause_extraction_with_exact_citation(auth_client: AsyncClient):
    document_id = await upload_contract(
        auth_client,
        [
            ("heading", "ARTICLE 1. CONFIDENTIALITY"),
            ("paragraph", CONFIDENTIALITY_TEXT),
            ("heading", "ARTICLE 2. LIMITATION OF LIABILITY"),
            ("paragraph", LIABILITY_TEXT),
        ],
    )

    provider = MockLLMProvider(
        [
            {
                "clauses": [
                    {
                        "category": "confidentiality",
                        "source_text": CONFIDENTIALITY_TEXT,
                        "summary": "Mutual confidentiality obligation lasting five years.",
                        "page_number": 1,
                        "section_heading": "ARTICLE 1. CONFIDENTIALITY",
                        "source_chunk_id": "exc:test:0",
                        "confidence": 0.94,
                    }
                ]
            }
        ]
    )
    use_mock_provider(provider)

    response = await auth_client.post(
        f"/api/v1/documents/{document_id}/extract-clauses"
    )
    assert response.status_code == 201, response.text

    payload = response.json()
    assert payload["run"]["status"] == "completed"
    assert payload["run"]["clauses_persisted"] == 1
    assert len(payload["clauses"]) == 1

    clause = payload["clauses"][0]
    assert clause["document_id"] == document_id
    assert clause["category"] == "confidentiality"
    assert clause["source_text"] == CONFIDENTIALITY_TEXT
    assert clause["normalized_summary"] == (
        "Mutual confidentiality obligation lasting five years."
    )
    assert clause["validation_status"] == "valid"
    assert clause["start_char_offset"] is not None
    assert clause["end_char_offset"] is not None
    assert clause["source_chunk_ids"]
    assert "risk_score" not in clause
    assert provider.calls and "untrusted" in provider.calls[0]["system_instruction"].lower()

    full_text = await reconstruct_document_text(auth_client, document_id)
    assert (
        full_text[clause["start_char_offset"] : clause["end_char_offset"]]
        == CONFIDENTIALITY_TEXT
    )

    list_response = await auth_client.get(
        f"/api/v1/documents/{document_id}/clauses?category=confidentiality"
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    single_response = await auth_client.get(
        f"/api/v1/documents/{document_id}/clauses/{clause['clause_id']}"
    )
    assert single_response.status_code == 200
    assert single_response.json()["source_text"] == CONFIDENTIALITY_TEXT


@pytest.mark.asyncio
async def test_malformed_model_response_is_handled_safely(auth_client: AsyncClient):
    document_id = await upload_contract(
        auth_client,
        [
            ("heading", "ARTICLE 1. CONFIDENTIALITY"),
            ("paragraph", CONFIDENTIALITY_TEXT),
        ],
    )

    provider = MockLLMProvider(["this is not valid JSON"])
    use_mock_provider(provider)

    response = await auth_client.post(
        f"/api/v1/documents/{document_id}/extract-clauses"
    )
    assert response.status_code == 201, response.text
    payload = response.json()

    assert payload["clauses"] == []
    assert payload["run"]["status"] == "partial"
    assert payload["run"]["candidates_rejected"] == 1
    assert payload["run"]["warnings"]


@pytest.mark.asyncio
async def test_missing_citation_is_rejected(auth_client: AsyncClient):
    document_id = await upload_contract(
        auth_client,
        [
            ("heading", "ARTICLE 1. CONFIDENTIALITY"),
            ("paragraph", CONFIDENTIALITY_TEXT),
        ],
    )

    provider = MockLLMProvider(
        [
            {
                "clauses": [
                    {
                        "category": "confidentiality",
                        "source_text": "This sentence does not exist anywhere in the contract.",
                        "summary": "Hallucinated confidentiality clause.",
                        "source_chunk_id": "exc:test:0",
                        "confidence": 0.8,
                    }
                ]
            }
        ]
    )
    use_mock_provider(provider)

    response = await auth_client.post(
        f"/api/v1/documents/{document_id}/extract-clauses"
    )
    assert response.status_code == 201, response.text
    payload = response.json()

    assert payload["clauses"] == []
    assert payload["run"]["candidates_rejected"] == 1
    assert any(
        "could not be located" in warning for warning in payload["run"]["warnings"]
    )


@pytest.mark.asyncio
async def test_incomplete_candidate_is_flagged_for_review(auth_client: AsyncClient):
    document_id = await upload_contract(
        auth_client,
        [
            ("heading", "ARTICLE 1. CONFIDENTIALITY"),
            ("paragraph", CONFIDENTIALITY_TEXT),
        ],
    )

    provider = MockLLMProvider(
        [
            {
                "clauses": [
                    {
                        "source_text": CONFIDENTIALITY_TEXT,
                        "source_chunk_id": "exc:test:0",
                    }
                ]
            }
        ]
    )
    use_mock_provider(provider)

    response = await auth_client.post(
        f"/api/v1/documents/{document_id}/extract-clauses"
    )
    assert response.status_code == 201, response.text
    payload = response.json()

    assert payload["run"]["status"] == "partial"
    assert payload["run"]["clauses_persisted"] == 1
    clause = payload["clauses"][0]
    assert clause["category"] == "miscellaneous"
    assert clause["validation_status"] == "needs_review"
    assert clause["normalized_summary"]
    assert "summary" in clause["validation_notes"].lower()


@pytest.mark.asyncio
async def test_duplicate_clause_candidates_are_merged(auth_client: AsyncClient):
    document_id = await upload_contract(
        auth_client,
        [
            ("heading", "ARTICLE 1. CONFIDENTIALITY"),
            ("paragraph", CONFIDENTIALITY_TEXT),
        ],
    )

    duplicate = {
        "category": "confidentiality",
        "source_text": CONFIDENTIALITY_TEXT,
        "summary": "Mutual confidentiality obligation.",
        "source_chunk_id": "exc:test:0",
        "confidence": 0.7,
    }
    provider = MockLLMProvider(
        [{"clauses": [duplicate, {**duplicate, "confidence": 0.9}]}]
    )
    use_mock_provider(provider)

    response = await auth_client.post(
        f"/api/v1/documents/{document_id}/extract-clauses"
    )
    assert response.status_code == 201, response.text
    payload = response.json()

    assert payload["run"]["candidates_received"] == 2
    assert payload["run"]["duplicates_merged"] == 1
    assert payload["run"]["clauses_persisted"] == 1
    assert len(payload["clauses"]) == 1
    assert payload["clauses"][0]["confidence"] == 0.9


@pytest.mark.asyncio
async def test_long_document_is_split_into_overlapping_chunks(auth_client: AsyncClient):
    long_text = " ".join(
        f"Clause sentence {index}: the parties agree to the stated obligation."
        for index in range(80)
    )
    document_id = await upload_contract(
        auth_client, [("paragraph", long_text)]
    )

    first_sentence = "Clause sentence 0: the parties agree to the stated obligation."
    provider = MockLLMProvider(
        [
            {
                "clauses": [
                    {
                        "category": "miscellaneous",
                        "source_text": first_sentence,
                        "summary": "General obligation of the parties.",
                        "source_chunk_id": "exc:long:0",
                        "confidence": 0.8,
                    }
                ]
            }
        ]
    )
    settings = Settings(
        _env_file=None,
        llm_provider="mock",
        clause_chunk_size=400,
        clause_chunk_overlap=80,
    )
    service = ClauseExtractionService(llm_provider=provider, settings=settings)
    app.dependency_overrides[get_clause_extraction_service] = lambda: service

    response = await auth_client.post(
        f"/api/v1/documents/{document_id}/extract-clauses"
    )
    assert response.status_code == 201, response.text
    payload = response.json()

    assert payload["run"]["total_chunks"] > 1
    assert len(provider.calls) == payload["run"]["total_chunks"]
    assert payload["run"]["clauses_persisted"] == 1
    assert payload["clauses"][0]["source_text"] == first_sentence


@pytest.mark.asyncio
async def test_provider_timeout_marks_run_failed(auth_client: AsyncClient):
    document_id = await upload_contract(
        auth_client,
        [
            ("heading", "ARTICLE 1. CONFIDENTIALITY"),
            ("paragraph", CONFIDENTIALITY_TEXT),
        ],
    )

    provider = MockLLMProvider([ProviderTimeoutError("simulated provider timeout")])
    use_mock_provider(provider)

    response = await auth_client.post(
        f"/api/v1/documents/{document_id}/extract-clauses"
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "LLM_TIMEOUT"

    runs_response = await auth_client.get(
        f"/api/v1/documents/{document_id}/extraction-runs"
    )
    assert runs_response.status_code == 200
    runs = runs_response.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert "timeout" in runs[0]["error_message"].lower()


@pytest.mark.asyncio
async def test_extraction_endpoint_reports_missing_credentials(auth_client: AsyncClient):
    document_id = await upload_contract(
        auth_client,
        [
            ("heading", "ARTICLE 1. CONFIDENTIALITY"),
            ("paragraph", CONFIDENTIALITY_TEXT),
        ],
    )

    def raise_configuration_error():
        raise ConfigurationError(
            "GEMINI_API_KEY is not configured. Set GEMINI_API_KEY or enable LLM_PROVIDER=mock."
        )

    app.dependency_overrides[get_llm_provider] = raise_configuration_error

    response = await auth_client.post(
        f"/api/v1/documents/{document_id}/extract-clauses"
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CONFIGURATION_ERROR"
    assert "GEMINI_API_KEY" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_gemini_provider_enforces_timeout(monkeypatch):
    provider = GeminiLLMProvider(
        api_key="fake-key",
        model_name="gemini-test",
        timeout_seconds=0.01,
        max_retries=0,
    )

    def slow_generate(*args, **kwargs):
        time.sleep(1.3)
        return {"clauses": []}

    monkeypatch.setattr(provider, "_generate_once", slow_generate)

    with pytest.raises(ProviderTimeoutError) as exc_info:
        await provider.generate_structured(system_instruction="system", user_prompt="user")

    assert exc_info.value.code == "LLM_TIMEOUT"


def test_missing_gemini_credentials_raise_configuration_error():
    settings = Settings(
        _env_file=None,
        llm_provider="gemini",
        gemini_api_key=None,
    )
    with pytest.raises(ConfigurationError) as exc_info:
        create_llm_provider(settings)

    assert "GEMINI_API_KEY" in str(exc_info.value)
    assert exc_info.value.code == "CONFIGURATION_ERROR"


def test_all_required_clause_categories_are_supported():
    required = {
        "liability",
        "indemnity",
        "termination",
        "renewal",
        "payment",
        "confidentiality",
        "intellectual_property",
        "data_protection",
        "warranties",
        "governing_law",
        "dispute_resolution",
        "miscellaneous",
    }
    assert {category.value for category in ClauseCategory} == required
    assert set(CLAUSE_RESPONSE_SCHEMA["properties"]["clauses"]["items"]["properties"]["category"]["enum"]) == required
