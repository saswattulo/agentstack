from fastapi import APIRouter

from agentstack import __version__
from agentstack.infra.db import get_engine
from agentstack.infra.redis import get_redis
from agentstack.infra.vectorstore import get_qdrant
from agentstack.schemas.common import HealthResponse

router = APIRouter(tags=["meta"])


@router.get("/", include_in_schema=False)
async def root():
    return {"name": "agentstack", "version": __version__, "docs": "/docs"}


@router.get("/health", response_model=HealthResponse)
@router.get("/livez", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get("/readyz", response_model=HealthResponse)
async def readyz() -> HealthResponse:
    services: dict[str, str] = {}

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        services["postgres"] = "ok"
    except Exception as e:
        services["postgres"] = f"error: {e.__class__.__name__}"

    try:
        await get_redis().ping()
        services["redis"] = "ok"
    except Exception as e:
        services["redis"] = f"error: {e.__class__.__name__}"

    try:
        await get_qdrant().get_collections()
        services["qdrant"] = "ok"
    except Exception as e:
        services["qdrant"] = f"error: {e.__class__.__name__}"

    overall = "ok" if all(v == "ok" for v in services.values()) else "degraded"
    return HealthResponse(status=overall, version=__version__, services=services)
