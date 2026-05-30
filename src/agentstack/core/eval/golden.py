"""Golden dataset management for regression testing.

Week 3 — load/save Q&A pairs with expected citations from tests/fixtures/golden.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GoldenItem:
    question: str
    expected_answer: str
    expected_chunk_ids: list[str]
    notes: str | None = None


def load_golden(path: str | Path) -> list[GoldenItem]:
    raw = json.loads(Path(path).read_text())
    return [GoldenItem(**item) for item in raw]


def save_golden(items: list[GoldenItem], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps([item.__dict__ for item in items], indent=2, ensure_ascii=False)
    )
