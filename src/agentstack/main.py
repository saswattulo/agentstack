from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from agentstack import __version__
from agentstack.api.errors import AppError
from agentstack.api.middleware.auth import AuthMiddleware
from agentstack.api.middleware.rate_limit import RateLimitMiddleware
from agentstack.api.middleware.request_id import RequestIDMiddleware
from agentstack.api.routes import (
    auth,
    collections,
    conversations,
    documents,
    eval as eval_routes,
    health,
    ingest,
    query,
)
from agentstack.config import settings
from agentstack.infra.db import dispose_engine
from agentstack.infra.logging import configure_logging, get_logger
from agentstack.infra.redis import close_redis
from agentstack.infra.tracing import configure_tracing
from agentstack.services.bootstrap import ensure_dev_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger = get_logger(__name__)
    try:
        configure_tracing()
    except Exception:
        logger.warning("tracing init failed; continuing without traces")
    try:
        await ensure_dev_user()
    except Exception:
        logger.exception("dev user bootstrap failed (may be pre-migration startup)")
    logger.info("agentstack starting", version=__version__, env=settings.app_env)
    yield
    logger.info("agentstack shutting down")
    await close_redis()
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentStack",
        version=__version__,
        description="Multi-agent RAG platform.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "dev" else [],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware, enabled=False)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RequestIDMiddleware)

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/health", "/livez", "/readyz"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(collections.router)
    app.include_router(ingest.router)
    app.include_router(documents.router)
    app.include_router(conversations.router)
    app.include_router(query.router)
    app.include_router(eval_routes.router)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.message,
                "code": exc.code,
                "request_id": getattr(request.state, "request_id", None),
                "details": exc.details,
            },
        )

    return app


app = create_app()
