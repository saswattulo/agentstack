from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from agentstack.config import settings
from agentstack.infra.logging import get_logger

logger = get_logger(__name__)

_async_client: AsyncQdrantClient | None = None
_sync_client: QdrantClient | None = None


def _client_kwargs() -> dict:
    kwargs: dict = {
        "host": settings.qdrant_host,
        "port": settings.qdrant_port,
        "grpc_port": settings.qdrant_grpc_port,
        "prefer_grpc": False,
        "https": False,
        "check_compatibility": False,
    }
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key
    return kwargs


def get_qdrant() -> AsyncQdrantClient:
    global _async_client
    if _async_client is None:
        _async_client = AsyncQdrantClient(**_client_kwargs())
    return _async_client


def get_qdrant_sync() -> QdrantClient:
    global _sync_client
    if _sync_client is None:
        _sync_client = QdrantClient(**_client_kwargs())
    return _sync_client


def collection_name(collection_id: str) -> str:
    return f"col_{collection_id.replace('-', '_')}"


async def ensure_collection(collection_id: str, vector_size: int | None = None) -> None:
    client = get_qdrant()
    name = collection_name(collection_id)
    size = vector_size or settings.embedding_dim
    try:
        await client.get_collection(name)
    except (UnexpectedResponse, ValueError):
        logger.info("creating qdrant collection", collection=name, vector_size=size)
        await client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )


def ensure_collection_sync(collection_id: str, vector_size: int | None = None) -> None:
    client = get_qdrant_sync()
    name = collection_name(collection_id)
    size = vector_size or settings.embedding_dim
    try:
        client.get_collection(name)
    except (UnexpectedResponse, ValueError):
        logger.info("creating qdrant collection (sync)", collection=name, vector_size=size)
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )


def upsert_points_sync(
    collection_id: str,
    points: list[PointStruct],
) -> None:
    client = get_qdrant_sync()
    name = collection_name(collection_id)
    client.upsert(collection_name=name, points=points, wait=True)


async def delete_collection(collection_id: str) -> None:
    client = get_qdrant()
    name = collection_name(collection_id)
    await client.delete_collection(name)
