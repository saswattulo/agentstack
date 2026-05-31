"""Parse, validate, and render citations.

The synthesizer prompt instructs the LLM to attach `[1]`, `[2]`, ... markers to
every factual claim. These utilities map those markers back to the chunks they
reference and build the context block that goes into the prompt.
"""

from __future__ import annotations

import re

from agentstack.core.retrieval.hybrid import RetrievedChunk
from agentstack.schemas.query import Citation

_CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")
_PREVIEW_LIMIT = 240


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as the `[1] ...\\n\\n[2] ...` block for the LLM."""
    if not chunks:
        return "(no retrieved context)"
    parts: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        text = (chunk.text or "").strip()
        parts.append(f"[{idx}] {text}")
    return "\n\n".join(parts)


def extract_citations(answer: str, chunks: list[RetrievedChunk]) -> list[Citation]:
    """Parse [n] markers in `answer`, map to chunks (1-indexed), dedupe, preserve order."""
    if not answer or not chunks:
        return []

    seen: dict[int, Citation] = {}
    for match in _CITATION_MARKER_RE.finditer(answer):
        n = int(match.group(1))
        if n < 1 or n > len(chunks):
            continue
        if n in seen:
            continue
        chunk = chunks[n - 1]
        preview = (chunk.text or "").strip().replace("\n", " ")
        if len(preview) > _PREVIEW_LIMIT:
            preview = preview[:_PREVIEW_LIMIT].rstrip() + "…"
        seen[n] = Citation(
            index=n,
            chunk_id=chunk.chunk_id,
            document_id=_safe_uuid(chunk.document_id),
            score=float(chunk.score),
            preview=preview,
        )
    return list(seen.values())


def validate_citations(
    citations: list[Citation], chunks: list[RetrievedChunk]
) -> list[Citation]:
    """Drop citations whose `index` is out of range. Defensive — `extract_citations`
    already filters, but in case external code constructs them directly."""
    return [c for c in citations if 1 <= c.index <= len(chunks)]


def _safe_uuid(value: str | None):
    from uuid import UUID

    if not value:
        return None
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        return None
