"""RAGAS metrics + custom citation accuracy. Week 3 work."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class EvalInput:
    question: str
    answer: str
    contexts: list[str]
    citations: list[dict]


@dataclass
class EvalScores:
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None
    citation_accuracy: float | None = None
    extra: dict | None = None


async def run_ragas_metrics(payload: EvalInput) -> EvalScores:
    """Run RAGAS-backed metrics.

    TODO(week-3): wire ragas.metrics with our Groq-backed LLM judge.
    """
    return EvalScores()


def citation_accuracy(answer: str, contexts: list[str], citations: list[dict]) -> float:
    """Fraction of cited spans that actually appear in the cited context chunk.

    Lightweight, doesn't need an LLM. Algorithm:
      1. Extract [n] tokens from the answer.
      2. For each, take the surrounding sentence as the "claim".
      3. Lookup contexts[n-1]. Mark accurate if claim noun-phrases substring-match.
      4. Return (accurate / total) or 0.0 if no citations.
    """
    matches = re.findall(r"\[(\d+)\]", answer)
    if not matches:
        return 0.0
    total = 0
    hits = 0
    for token in matches:
        idx = int(token) - 1
        if idx < 0 or idx >= len(contexts):
            total += 1
            continue
        sentence_end = answer.find(f"[{token}]")
        sentence_start = max(answer.rfind(".", 0, sentence_end), 0)
        claim = answer[sentence_start:sentence_end].strip(" .")
        keywords = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", claim)][:5]
        ctx_lower = contexts[idx].lower()
        if any(k in ctx_lower for k in keywords):
            hits += 1
        total += 1
    return hits / total if total else 0.0
