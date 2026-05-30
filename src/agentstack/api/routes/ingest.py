from pathlib import Path
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, File, UploadFile, status
from sqlalchemy import select

from agentstack.api.deps import CurrentUserDep, DbSession
from agentstack.api.errors import NotFoundError, PayloadTooLargeError, ValidationError
from agentstack.config import settings
from agentstack.models.collection import Collection
from agentstack.models.document import Document, DocumentStatus
from agentstack.schemas.document import DocumentRead, IngestUrlRequest
from agentstack.workers.tasks import ingest_document_task

router = APIRouter(prefix="/api/v1/collections", tags=["ingest"])

INGEST_DIR = Path("/tmp/agentstack/uploads")
INGEST_DIR.mkdir(parents=True, exist_ok=True)


ALLOWED_MIME = {
    "application/pdf": "pdf",
    "text/plain": "text",
    "text/markdown": "markdown",
    "text/x-markdown": "markdown",
}


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


@router.post(
    "/{collection_id}/ingest",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_file(
    collection_id: UUID,
    current: CurrentUserDep,
    db: DbSession,
    file: UploadFile = File(...),
) -> DocumentRead:
    await _get_owned_collection(db, collection_id, current.id)

    if file.content_type not in ALLOWED_MIME and not (file.filename or "").endswith(
        (".pdf", ".md", ".txt", ".markdown")
    ):
        raise ValidationError(
            f"Unsupported content type: {file.content_type}",
            details={"filename": file.filename, "content_type": file.content_type},
        )

    storage_id = uuid4()
    filename = file.filename or f"upload-{storage_id}"
    storage_path = INGEST_DIR / f"{storage_id}__{filename}"

    max_bytes = settings.ingest_max_file_mb * 1024 * 1024
    size = 0
    async with aiofiles.open(storage_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                await out.close()
                storage_path.unlink(missing_ok=True)
                raise PayloadTooLargeError(
                    f"File exceeds {settings.ingest_max_file_mb} MB limit"
                )
            await out.write(chunk)

    source_type = _infer_source_type(filename, file.content_type)
    document = Document(
        collection_id=collection_id,
        source_type=source_type,
        source_uri=str(storage_path),
        filename=filename,
        mime_type=file.content_type,
        size_bytes=size,
        status=DocumentStatus.PENDING,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    ingest_document_task.delay(str(document.id))

    return DocumentRead.model_validate(document)


@router.post(
    "/{collection_id}/ingest-url",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_url(
    collection_id: UUID,
    payload: IngestUrlRequest,
    current: CurrentUserDep,
    db: DbSession,
) -> DocumentRead:
    await _get_owned_collection(db, collection_id, current.id)

    document = Document(
        collection_id=collection_id,
        source_type="url",
        source_uri=str(payload.url),
        filename=None,
        mime_type=None,
        size_bytes=None,
        status=DocumentStatus.PENDING,
        extra=payload.metadata or {},
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    ingest_document_task.delay(str(document.id))

    return DocumentRead.model_validate(document)


def _infer_source_type(filename: str, content_type: str | None) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf") or content_type == "application/pdf":
        return "pdf"
    if lower.endswith((".md", ".markdown")):
        return "markdown"
    return "text"
