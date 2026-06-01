import pytest

from agentstack.core.agent.citations import (
    build_context_block,
    extract_citations,
    validate_citations,
)
from agentstack.core.retrieval.hybrid import RetrievedChunk


def _chunks(*texts: str) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=f"c{i}", document_id="d", text=t, score=1.0 / (i + 1), payload={}
        )
        for i, t in enumerate(texts)
    ]


@pytest.mark.unit
def test_extract_returns_empty_when_no_markers():
    chunks = _chunks("foo", "bar")
    assert extract_citations("plain answer with no brackets", chunks) == []


@pytest.mark.unit
def test_extract_returns_empty_when_no_chunks():
    assert extract_citations("Some answer [1].", []) == []


@pytest.mark.unit
def test_extract_maps_marker_to_chunk_one_indexed():
    chunks = _chunks("Qdrant", "Celery")
    citations = extract_citations("Vector store: Qdrant [1]. Queue: Celery [2].", chunks)
    assert [c.index for c in citations] == [1, 2]
    assert citations[0].chunk_id == "c0"
    assert citations[1].chunk_id == "c1"


@pytest.mark.unit
def test_extract_deduplicates_repeated_markers_preserving_first_appearance_order():
    chunks = _chunks("a", "b", "c")
    citations = extract_citations("see [2], also [1], again [2], and [1].", chunks)
    assert [c.index for c in citations] == [2, 1]


@pytest.mark.unit
def test_extract_drops_out_of_range_markers():
    chunks = _chunks("only one chunk")
    citations = extract_citations("said [9] and [0] and [1].", chunks)
    assert [c.index for c in citations] == [1]


@pytest.mark.unit
def test_extract_truncates_long_previews_with_ellipsis():
    long_text = "x" * 500
    chunks = _chunks(long_text)
    citations = extract_citations("ref [1]", chunks)
    assert len(citations) == 1
    assert citations[0].preview.endswith("…")
    assert len(citations[0].preview) <= 241


@pytest.mark.unit
def test_build_context_block_uses_one_indexed_markers():
    block = build_context_block(_chunks("first", "second"))
    assert block.startswith("[1] first")
    assert "[2] second" in block


@pytest.mark.unit
def test_build_context_block_handles_empty_input():
    assert build_context_block([]) == "(no retrieved context)"


@pytest.mark.unit
def test_validate_drops_out_of_range():
    chunks = _chunks("a")
    citations = extract_citations("ref [1]", chunks)
    # forge an out-of-range citation to be sure validate filters
    bad = type(citations[0])(
        index=99,
        chunk_id="x",
        document_id=None,
        score=0.0,
        preview="",
    )
    out = validate_citations(citations + [bad], chunks)
    assert all(1 <= c.index <= 1 for c in out)
