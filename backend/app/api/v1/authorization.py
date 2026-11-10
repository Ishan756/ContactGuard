from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import ReviewerPrincipal
from app.db.models import Document


async def require_document_access(
    document_id: str,
    db: AsyncSession,
    principal: ReviewerPrincipal,
) -> Document:
    """Load a document and enforce reviewer ownership (admins may access all)."""
    document = (
        await db.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        raise NotFoundError(f"Document with ID '{document_id}' not found.")
    if not principal.can_access_owned(document.owner_reviewer_id):
        raise ForbiddenError("You are not authorized to access this document.")
    return document
