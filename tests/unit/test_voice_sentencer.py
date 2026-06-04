"""Sentence-buffer unit tests."""

import pytest

from agentstack.core.voice.sentencer import SentenceBuffer


@pytest.mark.unit
def test_single_sentence_no_boundary_buffered():
    sb = SentenceBuffer()
    assert sb.feed("Hello") == []
    assert sb.feed(" world") == []
    assert sb.flush() == "Hello world"


@pytest.mark.unit
def test_period_emits_sentence_and_drops_whitespace():
    sb = SentenceBuffer()
    out = sb.feed("Qdrant is the vector store. ")
    assert out == ["Qdrant is the vector store."]
    assert sb.flush() is None


@pytest.mark.unit
def test_multiple_sentences_in_one_token():
    sb = SentenceBuffer()
    out = sb.feed("First. Second! Third? ")
    assert out == ["First.", "Second!", "Third?"]


@pytest.mark.unit
def test_sentences_split_across_tokens():
    sb = SentenceBuffer()
    out: list[str] = []
    for tok in ["Qdrant is ", "the store", ". Cosine ", "is used", "!"]:
        out.extend(sb.feed(tok))
    out.append(sb.flush() or "")
    out = [s for s in out if s]
    assert "Qdrant is the store." in out
    assert "Cosine is used!" in out


@pytest.mark.unit
def test_think_block_is_stripped():
    sb = SentenceBuffer()
    text = "<think>internal reasoning blah blah</think>Answer: Qdrant. Done!"
    out = sb.feed(text)
    out.append(sb.flush() or "")
    out = [s for s in out if s]
    assert "Answer: Qdrant." in out
    assert "Done!" in out
    assert all("reasoning" not in s for s in out)


@pytest.mark.unit
def test_think_block_spanning_two_tokens():
    sb = SentenceBuffer()
    out: list[str] = []
    out.extend(sb.feed("prefix <think>secret"))
    out.extend(sb.feed("still hidden</think>visible. Yes."))
    out.extend(sb.feed(" "))
    out.append(sb.flush() or "")
    out = [s for s in out if s]
    assert any("visible." in s for s in out)
    assert all("secret" not in s and "hidden" not in s for s in out)


@pytest.mark.unit
def test_force_flush_at_max_chars():
    sb = SentenceBuffer(max_chars=40)
    long_input = "word " * 50  # 250 chars of run-on
    out = sb.feed(long_input)
    # at least one chunk should have flushed under max_chars
    assert len(out) >= 1
    for chunk in out:
        assert len(chunk) <= 40


@pytest.mark.unit
def test_empty_input_returns_no_sentences():
    sb = SentenceBuffer()
    assert sb.feed("") == []
    assert sb.flush() is None
