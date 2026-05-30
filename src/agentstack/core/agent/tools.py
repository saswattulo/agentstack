"""Tools exposed to the agent. Each tool gets a JSON schema for LLM tool-use."""

from __future__ import annotations

from typing import Any

from tavily import TavilyClient

from agentstack.config import settings
from agentstack.infra.logging import get_logger

logger = get_logger(__name__)


def tool_schemas() -> list[dict[str, Any]]:
    return [WEB_SEARCH_SCHEMA, CODE_EXEC_SCHEMA]


WEB_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the public web for recent information not in the corpus.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
    },
}


CODE_EXEC_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "code_exec",
        "description": "Execute a short Python snippet in a sandboxed environment.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source to execute."}
            },
            "required": ["code"],
        },
    },
}


def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    if not settings.tavily_api_key:
        return {"error": "TAVILY_API_KEY not configured", "results": []}
    client = TavilyClient(api_key=settings.tavily_api_key)
    resp = client.search(query=query, max_results=max_results, include_raw_content=False)
    return {
        "query": query,
        "results": [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "snippet": r.get("content"),
                "score": r.get("score"),
            }
            for r in resp.get("results", [])
        ],
    }


def code_exec(code: str) -> dict[str, Any]:
    """Disabled by default — see CLAUDE.md. Sandboxing is a stretch goal."""
    logger.info("code_exec invoked (stub)", code_len=len(code))
    return {
        "ok": False,
        "error": "Code execution is disabled in this build. Enable a sandbox first.",
    }


TOOL_REGISTRY = {
    "web_search": web_search,
    "code_exec": code_exec,
}
