"""Unit tests for eval metric helpers (parsing + relevancy with mocked LLM)."""

from unittest.mock import AsyncMock, patch

import pytest

from agentstack.core.eval.metrics import (
    _extract_json_array,
    _strip_think,
    answer_relevancy,
    citation_accuracy,
    faithfulness,
)


@pytest.mark.unit
def test_strip_think_removes_reasoning_block():
    raw = '<think>\nlots of reasoning across\nmultiple lines\n</think>\n["claim"]'
    out = _strip_think(raw)
    assert "reasoning" not in out
    assert '["claim"]' in out


@pytest.mark.unit
def test_strip_think_is_noop_when_no_think():
    raw = '["plain answer"]'
    assert _strip_think(raw).strip() == raw


@pytest.mark.unit
def test_extract_json_array_finds_array_after_think():
    raw = '<think>chain of thought</think>\n```json\n["a", "b"]\n```'
    assert _extract_json_array(raw) == ["a", "b"]


@pytest.mark.unit
def test_extract_json_array_returns_none_on_garbage():
    assert _extract_json_array("nothing here") is None
    assert _extract_json_array("[broken") is None


@pytest.mark.unit
def test_extract_json_array_rejects_non_array_json():
    assert _extract_json_array('{"not": "array"}') is None


def _resp(text: str) -> dict:
    return {
        "model": "test",
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


@pytest.mark.unit
async def test_faithfulness_returns_fraction_supported():
    """2 claims, judge says supported=[true, false] → 0.5."""
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(
        side_effect=[
            _resp('["Claim A", "Claim B"]'),
            _resp("[true, false]"),
        ]
    )
    with patch("agentstack.core.eval.metrics.get_chat_client", return_value=mock_client):
        score = await faithfulness("answer", ["context"])
    assert score == 0.5
    assert mock_client.complete.await_count == 2


@pytest.mark.unit
async def test_faithfulness_returns_one_when_all_supported():
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(
        side_effect=[
            _resp('["A", "B", "C"]'),
            _resp("[true, true, true]"),
        ]
    )
    with patch("agentstack.core.eval.metrics.get_chat_client", return_value=mock_client):
        score = await faithfulness("answer", ["ctx"])
    assert score == 1.0


@pytest.mark.unit
async def test_faithfulness_returns_none_when_no_contexts():
    score = await faithfulness("answer", [])
    assert score is None


@pytest.mark.unit
async def test_faithfulness_returns_none_when_claims_unparseable():
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value=_resp("garbage"))
    with patch("agentstack.core.eval.metrics.get_chat_client", return_value=mock_client):
        score = await faithfulness("answer", ["ctx"])
    assert score is None


@pytest.mark.unit
def test_citation_accuracy_returns_zero_when_no_markers():
    assert citation_accuracy("nothing cited here", ["ctx"], []) == 0.0


@pytest.mark.unit
def test_citation_accuracy_hits_when_keyword_present():
    answer = "Vector store is Qdrant [1]."
    contexts = ["Qdrant is the chosen vector store in AgentStack."]
    assert citation_accuracy(answer, contexts, []) == 1.0


@pytest.mark.unit
def test_citation_accuracy_misses_when_keyword_absent():
    answer = "MongoDB rocks [1]."
    contexts = ["Kittens love yarn."]
    assert citation_accuracy(answer, contexts, []) == 0.0
