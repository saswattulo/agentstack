from celery import Celery

from agentstack.config import settings
from agentstack.infra.logging import configure_logging

configure_logging()

celery_app = Celery(
    "agentstack",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
    include=["agentstack.workers.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue="default",
    task_routes={
        "agentstack.workers.tasks.ingest_document_task": {"queue": "ingest"},
        "agentstack.workers.tasks.eval_query_task": {"queue": "eval"},
    },
    broker_connection_retry_on_startup=True,
)
