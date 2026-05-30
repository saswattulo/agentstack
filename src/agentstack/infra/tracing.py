"""Phoenix / OpenTelemetry tracing setup.

Week 3 will instrument LLM + retrieval calls via OpenInference. For now this
just registers a tracer provider pointing at the Phoenix collector so traces
emitted by feature code show up in the UI.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from agentstack.config import settings
from agentstack.infra.logging import get_logger

logger = get_logger(__name__)

_initialized = False


def configure_tracing() -> None:
    global _initialized
    if _initialized:
        return

    endpoint = settings.phoenix_collector_endpoint.rstrip("/") + "/v1/traces"

    resource = Resource.create(
        {
            SERVICE_NAME: settings.phoenix_project_name,
            "deployment.environment": settings.app_env,
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    _initialized = True
    logger.info("tracing configured", endpoint=endpoint)


def get_tracer(name: str = "agentstack") -> trace.Tracer:
    return trace.get_tracer(name)
