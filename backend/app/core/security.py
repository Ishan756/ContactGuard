from dataclasses import dataclass
from enum import StrEnum
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError


class ReviewerRole(StrEnum):
    REVIEWER = "reviewer"
    ADMIN = "admin"


@dataclass(frozen=True)
class ReviewerPrincipal:
    reviewer_id: str
    role: ReviewerRole = ReviewerRole.REVIEWER

    @property
    def is_admin(self) -> bool:
        return self.role == ReviewerRole.ADMIN

    def can_access_owned(self, owner_reviewer_id: str | None) -> bool:
        """Admins may access all tenant resources; reviewers only their own."""
        return self.is_admin or owner_reviewer_id == self.reviewer_id


def _matches(candidate: str | None, expected: str) -> bool:
    if not candidate or not expected:
        return False
    return compare_digest(candidate, expected)


async def require_reviewer(
    x_reviewer_id: Annotated[str | None, Header(alias="X-Reviewer-ID")] = None,
    x_workflow_key: Annotated[str | None, Header(alias="X-Workflow-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> ReviewerPrincipal:
    """Authenticate a reviewer using a role-scoped API key and stable reviewer identity."""
    reviewer_id = (x_reviewer_id or "").strip()
    if not reviewer_id:
        raise UnauthorizedError("A reviewer identity is required in X-Reviewer-ID.")
    if len(reviewer_id) > 120 or any(ord(char) < 32 for char in reviewer_id):
        raise UnauthorizedError("Reviewer identity is invalid.")

    if _matches(x_workflow_key, settings.admin_api_key):
        return ReviewerPrincipal(reviewer_id=reviewer_id, role=ReviewerRole.ADMIN)
    if _matches(x_workflow_key, settings.workflow_review_api_key):
        return ReviewerPrincipal(reviewer_id=reviewer_id, role=ReviewerRole.REVIEWER)
    raise UnauthorizedError("A valid X-Workflow-Key is required.")


async def require_admin(
    principal: ReviewerPrincipal = Depends(require_reviewer),
) -> ReviewerPrincipal:
    """Restrict an endpoint to administrative reviewers."""
    if not principal.is_admin:
        raise ForbiddenError("Administrative reviewer privileges are required.")
    return principal
