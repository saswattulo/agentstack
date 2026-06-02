"""Phoenix / OpenTelemetry tracing setup.

We use raw `opentelemetry-api` directly. Attribute keys follow OpenInference
semantic conventions so Phoenix renders the trace tree as a familiar
agent / LLM / retriever stack.
"""

from __future__ import annotations

import json
from typing import Any

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


# ---- OpenInference attribute keys ----

SPAN_KIND = "openinference.span.kind"

LLM_PROVIDER = "llm.provider"
LLM_MODEL = "llm.model_name"
LLM_PROMPT_TOKENS = "llm.token_count.prompt"
LLM_COMPLETION_TOKENS = "llm.token_count.completion"
LLM_TOTAL_TOKENS = "llm.token_count.total"
LLM_PARAMS = "llm.invocation_parameters"

INPUT_VALUE = "input.value"
INPUT_MIME = "input.mime_type"
OUTPUT_VALUE = "output.value"
OUTPUT_MIME = "output.mime_type"

RETRIEVAL_QUERY = "retrieval.query"

SESSION_ID = "session.id"
USER_ID = "user.id"


# ---- helpers ----

_TRUNCATE = 2000


def truncate(value: Any) -> str:
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(s) > _TRUNCATE:
        return s[:_TRUNCATE] + f"…(+{len(s) - _TRUNCATE} chars)"
    return s


def set_attrs(span, **attrs: Any) -> None:
    """Filter None, stringify non-primitives, then set on the span."""
    clean: dict[str, Any] = {}
    for k, v in attrs.items():
        if v is None:
            continue
        if isinstance(v, (str, bool, int, float)):
            clean[k] = v
        else:
            clean[k] = truncate(v)
    span.set_attributes(clean)
