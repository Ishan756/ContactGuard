from dataclasses import dataclass
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import UnauthorizedError


@dataclass(frozen=True)
class ReviewerPrincipal:
    reviewer_id: str


async def require_reviewer(
    x_reviewer_id: Annotated[str | None, Header(alias="X-Reviewer-ID")] = None,
    x_workflow_key: Annotated[str | None, Header(alias="X-Workflow-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> ReviewerPrincipal:
    """Authenticate a reviewer using an API key and stable reviewer identity."""
    reviewer_id = (x_reviewer_id or "").strip()
    if not reviewer_id:
        raise UnauthorizedError("A reviewer identity is required in X-Reviewer-ID.")
    if len(reviewer_id) > 120:
        raise UnauthorizedError("Reviewer identity is too long.")
    if not x_workflow_key or not compare_digest(
        x_workflow_key, settings.workflow_review_api_key
    ):
        raise UnauthorizedError("A valid X-Workflow-Key is required.")
    return ReviewerPrincipal(reviewer_id=reviewer_id)
