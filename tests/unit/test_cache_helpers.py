"""Unit tests for the cache helpers that don't need Redis."""

import json

import numpy as np
import pytest

from agentstack.core.retrieval.cache import (
    EXACT_PREFIX,
    LRU_PREFIX,
    VECIDX_PREFIX,
    CachedAnswer,
    _cosine,
    _decode_payload,
    _decode_vec,
    _encode_vec,
    cache_key,
)


@pytest.mark.unit
def test_cache_key_is_normalized():
    a = cache_key(" What is X?", "c1")
    b = cache_key("what is x?", "c1")
    assert a == b


@pytest.mark.unit
def test_cache_key_changes_with_collection():
    a = cache_key("what is x?", "c1")
    b = cache_key("what is x?", "c2")
    assert a != b


@pytest.mark.unit
def test_cache_key_handles_none_collection():
    k = cache_key("hi", None)
    assert len(k) == 64  # sha256 hex


@pytest.mark.unit
def test_key_prefixes_are_distinct():
    assert EXACT_PREFIX != VECIDX_PREFIX != LRU_PREFIX


@pytest.mark.unit
def test_vec_encode_decode_roundtrip():
    vec = [0.1, 0.2, 0.3, 0.4]
    enc = _encode_vec(vec)
    dec = _decode_vec(enc)
    assert len(dec) == 4
    np.testing.assert_allclose(dec, vec, atol=1e-6)


@pytest.mark.unit
def test_cosine_self_is_one():
    v = np.asarray([1.0, 2.0, 3.0])
    assert _cosine(v, v) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.unit
def test_cosine_orthogonal_is_zero():
    a = np.asarray([1.0, 0.0])
    b = np.asarray([0.0, 1.0])
    assert _cosine(a, b) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.unit
def test_cosine_handles_zero_vector_safely():
    a = np.asarray([0.0, 0.0, 0.0])
    b = np.asarray([1.0, 2.0, 3.0])
    assert _cosine(a, b) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.unit
def test_decode_payload_roundtrips_a_cached_answer():
    ca = CachedAnswer(
        answer="Qdrant is the vector store.",
        citations=[{"index": 1, "chunk_id": "c1", "preview": "qdrant"}],
        model="qwen/qwen3-32b",
        intent="factual",
    )
    raw = json.dumps(
        {"answer": ca.answer, "citations": ca.citations, "model": ca.model, "intent": ca.intent}
    )
    back = _decode_payload(raw)
    assert back is not None
    assert back.answer == ca.answer
    assert back.citations == ca.citations
    assert back.model == ca.model
    assert back.intent == ca.intent


@pytest.mark.unit
def test_decode_payload_returns_none_on_garbage():
    assert _decode_payload("not json") is None
