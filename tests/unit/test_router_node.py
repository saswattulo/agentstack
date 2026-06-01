"""Router node unit tests with a mocked chat client."""

from unittest.mock import AsyncMock, patch

import pytest

from agentstack.core.agent.nodes import AgentState, router_node


def _resp(text: str) -> dict:
    return {
        "model": "test-model",
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 1},
    }


@pytest.mark.unit
async def test_router_picks_factual_when_llm_says_so():
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value=_resp("factual"))
    with patch("agentstack.core.agent.nodes.get_chat_client", return_value=mock_client):
        state: AgentState = {"question": "what is the capital of France?"}
        out = await router_node(state)
    assert out["intent"] == "factual"
    mock_client.complete.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("analytical", "analytical"),
        ("comparison", "comparison"),
        ("web", "web"),
        ("code", "code"),
        ("conversational", "conversational"),
        ("  factual\n", "factual"),  # whitespace
        ("Intent: web", "web"),  # trailing label
    ],
)
async def test_router_maps_label_variations(raw, expected):
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value=_resp(raw))
    with patch("agentstack.core.agent.nodes.get_chat_client", return_value=mock_client):
        out = await router_node({"question": "q"})
    assert out["intent"] == expected


@pytest.mark.unit
async def test_router_defaults_to_factual_on_garbage():
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value=_resp("aufzgnpw"))
    with patch("agentstack.core.agent.nodes.get_chat_client", return_value=mock_client):
        out = await router_node({"question": "q"})
    assert out["intent"] == "factual"


@pytest.mark.unit
async def test_router_handles_empty_response():
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(return_value=_resp(""))
    with patch("agentstack.core.agent.nodes.get_chat_client", return_value=mock_client):
        out = await router_node({"question": "q"})
    assert out["intent"] == "factual"
