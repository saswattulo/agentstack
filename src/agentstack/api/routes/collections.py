from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from agentstack.api.deps import CurrentUserDep, DbSession
from agentstack.api.errors import ConflictError, NotFoundError
from agentstack.config import settings
from agentstack.infra.metrics import COLLECTIONS_TOTAL
from agentstack.infra.vectorstore import delete_collection as drop_qdrant_collection
from agentstack.infra.vectorstore import ensure_collection
from agentstack.models.collection import Collection
from agentstack.schemas.collection import (
    CollectionCreate,
    CollectionRead,
    CollectionUpdate,
)
from agentstack.schemas.common import Pagination

router = APIRouter(prefix="/api/v1/collections", tags=["collections"])


async def _get_owned_collection(
    db: DbSession, collection_id: UUID, user_id: UUID
) -> Collection:
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id, Collection.owner_id == user_id
        )
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise NotFoundError("Collection not found")
    return collection


@router.post("", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
async def create_collection(
    payload: CollectionCreate, current: CurrentUserDep, db: DbSession
) -> CollectionRead:
    collection = Collection(
        owner_id=current.id,
        name=payload.name,
        description=payload.description,
        embedding_model=settings.embedding_model,
        embedding_dim=settings.embedding_dim,
        chunking_strategy=payload.chunking_strategy,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
    )
    db.add(collection)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ConflictError(f"You already have a collection named '{payload.name}'") from e

    await db.refresh(collection)
    await ensure_collection(str(collection.id), settings.embedding_dim)

    count = await db.scalar(select(func.count()).select_from(Collection))
    COLLECTIONS_TOTAL.set(count or 0)
    return CollectionRead.model_validate(collection)


@router.get("", response_model=Pagination[CollectionRead])
async def list_collections(
    current: CurrentUserDep,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Pagination[CollectionRead]:
    total = (
        await db.scalar(
            select(func.count())
            .select_from(Collection)
            .where(Collection.owner_id == current.id)
        )
    ) or 0
    result = await db.execute(
        select(Collection)
        .where(Collection.owner_id == current.id)
        .order_by(Collection.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [CollectionRead.model_validate(c) for c in result.scalars().all()]
    return Pagination[CollectionRead](items=items, total=total, limit=limit, offset=offset)


@router.get("/{collection_id}", response_model=CollectionRead)
async def get_collection(
    collection_id: UUID, current: CurrentUserDep, db: DbSession
) -> CollectionRead:
    collection = await _get_owned_collection(db, collection_id, current.id)
    return CollectionRead.model_validate(collection)


@router.patch("/{collection_id}", response_model=CollectionRead)
async def update_collection(
    collection_id: UUID,
    payload: CollectionUpdate,
    current: CurrentUserDep,
    db: DbSession,
) -> CollectionRead:
    collection = await _get_owned_collection(db, collection_id, current.id)
    if payload.description is not None:
        collection.description = payload.description
    await db.commit()
    await db.refresh(collection)
    return CollectionRead.model_validate(collection)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: UUID, current: CurrentUserDep, db: DbSession
) -> None:
    collection = await _get_owned_collection(db, collection_id, current.id)
    await db.delete(collection)
    await db.commit()
    try:
        await drop_qdrant_collection(str(collection_id))
    except Exception:
        pass

    count = await db.scalar(select(func.count()).select_from(Collection))
    COLLECTIONS_TOTAL.set(count or 0)
