import pytest

from agentstack.core.ingestion.chunker import RecursiveChunker


@pytest.mark.unit
def test_recursive_chunker_returns_empty_for_blank():
    chunker = RecursiveChunker(chunk_size=100, chunk_overlap=10)
    assert chunker.split("") == []
    assert chunker.split("   \n  ") == []


@pytest.mark.unit
def test_recursive_chunker_respects_size_bound():
    text = "Sentence. " * 100  # ~1000 chars
    chunker = RecursiveChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.split(text)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= 220, f"chunk overran budget: {len(c.text)}"


@pytest.mark.unit
def test_recursive_chunker_indexes_in_order():
    text = "\n\n".join([f"para-{i}" for i in range(8)])
    chunks = RecursiveChunker(chunk_size=20, chunk_overlap=5).split(text)
    indices = [c.index for c in chunks]
    assert indices == sorted(indices)
    assert indices == list(range(len(chunks)))


@pytest.mark.unit
def test_recursive_chunker_handles_single_short_text():
    chunks = RecursiveChunker(chunk_size=512, chunk_overlap=64).split("hello world")
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
