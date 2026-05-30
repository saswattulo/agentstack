from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from agentstack.api.deps import CurrentUserDep, DbSession
from agentstack.api.errors import NotFoundError
from agentstack.models.collection import Collection
from agentstack.models.document import Document
from agentstack.schemas.common import Pagination
from agentstack.schemas.document import DocumentRead

router = APIRouter(prefix="/api/v1", tags=["documents"])


async def _get_owned_document(
    db: DbSession, document_id: UUID, user_id: UUID
) -> Document:
    result = await db.execute(
        select(Document)
        .join(Collection, Document.collection_id == Collection.id)
        .where(Document.id == document_id, Collection.owner_id == user_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise NotFoundError("Document not found")
    return doc


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID, current: CurrentUserDep, db: DbSession
) -> DocumentRead:
    doc = await _get_owned_document(db, document_id, current.id)
    return DocumentRead.model_validate(doc)


@router.get("/collections/{collection_id}/documents", response_model=Pagination[DocumentRead])
async def list_documents(
    collection_id: UUID,
    current: CurrentUserDep,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Pagination[DocumentRead]:
    owns = await db.scalar(
        select(func.count())
        .select_from(Collection)
        .where(Collection.id == collection_id, Collection.owner_id == current.id)
    )
    if not owns:
        raise NotFoundError("Collection not found")

    total = (
        await db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.collection_id == collection_id)
        )
    ) or 0
    result = await db.execute(
        select(Document)
        .where(Document.collection_id == collection_id)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [DocumentRead.model_validate(d) for d in result.scalars().all()]
    return Pagination[DocumentRead](items=items, total=total, limit=limit, offset=offset)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID, current: CurrentUserDep, db: DbSession
) -> None:
    doc = await _get_owned_document(db, document_id, current.id)
    await db.delete(doc)
    await db.commit()
