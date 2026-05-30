"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("DEV_API_KEY", "test-dev-key")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
