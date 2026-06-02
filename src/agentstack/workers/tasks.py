"""Celery tasks. Workers run sync — we use the sync SQLAlchemy engine + sync Qdrant client."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from qdrant_client.http.models import PointStruct
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agentstack.config import settings
from agentstack.core.ingestion.chunker import get_chunker
from agentstack.core.ingestion.embedder import get_embedder
from agentstack.core.ingestion.parser import parse_document
from agentstack.infra.logging import get_logger
from agentstack.infra.metrics import (
    CHUNKS_CREATED,
    DOCUMENTS_INGESTED,
    INGESTION_FAILURES,
)
from agentstack.infra.vectorstore import (
    collection_name,
    ensure_collection_sync,
    get_qdrant_sync,
)
from agentstack.models.chunk import ChunkMetadata
from agentstack.models.collection import Collection
from agentstack.models.document import Document, DocumentStatus
from agentstack.workers.celery_app import celery_app

logger = get_logger(__name__)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.sync_sqlalchemy_url,
            pool_pre_ping=True,
            pool_size=4,
            max_overflow=4,
        )
    return _engine


def _update_status(
    session: Session,
    doc: Document,
    *,
    status: DocumentStatus | None = None,
    progress: int | None = None,
    error: str | None = None,
    chunk_count: int | None = None,
) -> None:
    if status is not None:
        doc.status = status
    if progress is not None:
        doc.progress = progress
    if error is not None:
        doc.error_message = error
    if chunk_count is not None:
        doc.chunk_count = chunk_count
    doc.updated_at = datetime.now(timezone.utc)
    session.commit()


@celery_app.task(
    name="agentstack.workers.tasks.ingest_document_task",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def ingest_document_task(self, document_id: str) -> dict:
    log = logger.bind(task="ingest_document", document_id=document_id)
    log.info("ingestion started")

    engine = _get_engine()
    with Session(engine, expire_on_commit=False) as session:
        doc = session.get(Document, UUID(document_id))
        if doc is None:
            log.error("document not found")
            return {"document_id": document_id, "status": "not_found"}

        collection = session.get(Collection, doc.collection_id)
        if collection is None:
            log.error("collection not found")
            _update_status(session, doc, status=DocumentStatus.FAILED, error="Collection missing")
            INGESTION_FAILURES.labels(
                collection_id=str(doc.collection_id), stage="lookup"
            ).inc()
            return {"document_id": document_id, "status": "failed"}

        try:
            _update_status(session, doc, status=DocumentStatus.PARSING, progress=10)
            parsed = parse_document(doc.source_type, doc.source_uri)

            _update_status(session, doc, status=DocumentStatus.CHUNKING, progress=30)
            chunker = get_chunker(
                collection.chunking_strategy,
                collection.chunk_size,
                collection.chunk_overlap,
            )
            chunks = chunker.split(parsed.text)
            if not chunks:
                _update_status(
                    session,
                    doc,
                    status=DocumentStatus.FAILED,
                    error="No chunks produced from document",
                )
                INGESTION_FAILURES.labels(
                    collection_id=str(doc.collection_id), stage="chunking"
                ).inc()
                return {"document_id": document_id, "status": "failed"}

            _update_status(session, doc, status=DocumentStatus.EMBEDDING, progress=55)
            embedder = get_embedder()
            vectors = embedder.embed([c.text for c in chunks])

            _update_status(
                session,
                doc,
                status=DocumentStatus.INDEXING,
                progress=80,
            )
            ensure_collection_sync(str(doc.collection_id), embedder.dim)
            qdrant = get_qdrant_sync()

            points: list[PointStruct] = []
            chunk_rows: list[ChunkMetadata] = []
            for chunk, vec in zip(chunks, vectors, strict=True):
                seed = f"{doc.id}__{chunk.index}"
                qdrant_id = _uuid_from_str(seed)
                payload = {
                    "document_id": str(doc.id),
                    "collection_id": str(doc.collection_id),
                    "chunk_index": chunk.index,
                    "text": chunk.text,
                    "source_type": doc.source_type,
                    "source_uri": doc.source_uri,
                    "filename": doc.filename,
                    **parsed.metadata,
                }
                points.append(
                    PointStruct(
                        id=qdrant_id,
                        vector=vec,
                        payload=payload,
                    )
                )
                chunk_rows.append(
                    ChunkMetadata(
                        document_id=doc.id,
                        collection_id=doc.collection_id,
                        qdrant_point_id=qdrant_id,
                        chunk_index=chunk.index,
                        content_preview=chunk.text[:240],
                        token_count=len(chunk.text.split()),
                    )
                )

            qdrant.upsert(
                collection_name=collection_name(str(doc.collection_id)),
                points=points,
                wait=True,
            )

            session.add_all(chunk_rows)
            _update_status(
                session,
                doc,
                status=DocumentStatus.COMPLETED,
                progress=100,
                chunk_count=len(chunks),
            )

            DOCUMENTS_INGESTED.labels(
                collection_id=str(doc.collection_id),
                source_type=doc.source_type,
            ).inc()
            CHUNKS_CREATED.labels(collection_id=str(doc.collection_id)).inc(len(chunks))

            from agentstack.core.retrieval.cache import invalidate_collection_sync

            invalidate_collection_sync(str(doc.collection_id))

            if doc.source_type in {"pdf", "markdown", "text"}:
                try:
                    Path(doc.source_uri).unlink(missing_ok=True)
                except OSError:
                    pass

            log.info("ingestion complete", chunks=len(chunks))
            return {"document_id": document_id, "status": "completed", "chunks": len(chunks)}

        except Exception as exc:
            log.exception("ingestion failed")
            _update_status(
                session,
                doc,
                status=DocumentStatus.FAILED,
                error=f"{exc.__class__.__name__}: {exc}",
            )
            INGESTION_FAILURES.labels(
                collection_id=str(doc.collection_id), stage="exception"
            ).inc()
            raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc


@celery_app.task(
    name="agentstack.workers.tasks.eval_query_task",
    bind=True,
    max_retries=1,
    default_retry_delay=15,
)
def eval_query_task(self, query_log_id: str) -> dict:
    """Run faithfulness + answer relevancy + citation accuracy on a stored query.

    Async metric pipeline is wrapped in asyncio.run so the Celery worker stays
    sync. Failures are logged + swallowed: an eval flake should never crash the
    worker or block downstream tasks.
    """
    import asyncio
    from uuid import UUID

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from agentstack.core.eval.runner import evaluate_and_persist

    async def _run() -> dict:
        engine = create_async_engine(settings.sqlalchemy_url, pool_pre_ping=True)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as session:
                scores = await evaluate_and_persist(UUID(query_log_id), session)
                return {
                    "query_log_id": query_log_id,
                    "status": "ok",
                    "faithfulness": scores.faithfulness,
                    "answer_relevancy": scores.answer_relevancy,
                    "citation_accuracy": scores.citation_accuracy,
                }
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("eval_query_task failed", query_log_id=query_log_id)
        return {"query_log_id": query_log_id, "status": "error", "error": str(exc)}


def _uuid_from_str(name: str) -> str:
    import hashlib
    import uuid

    return str(uuid.UUID(hashlib.md5(name.encode()).hexdigest()))
