"""Custom LLM-judge metrics + local citation accuracy.

We implement faithfulness and answer relevancy ourselves (against our Groq
client + local sentence-transformer) instead of pulling in `ragas` →
`langchain-community` → vertexai's full dependency tree.

The metric definitions follow RAGAS's published heuristics:

- **Faithfulness**: extract atomic claims from the answer, judge each against
  the retrieved context, score = supported / total.
- **Answer relevancy**: generate N candidate questions that the answer would
  fit; embed the original question + the candidates; score = mean cosine
  similarity. Higher = answer is on-topic.
- **Citation accuracy**: kept from Week 1 — purely lexical, no LLM call.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import numpy as np

from agentstack.infra.llm import get_chat_client
from agentstack.infra.logging import get_logger

logger = get_logger(__name__)


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
    context_precision: float | None = None  # not implemented; needs ground truth
    context_recall: float | None = None     # not implemented; needs ground truth
    citation_accuracy: float | None = None
    extra: dict | None = None


_CLAIM_PROMPT = (
    "Extract every factual claim in the ANSWER below as a JSON array of short "
    "strings. Each item must be a single self-contained claim. If there are no "
    "claims, return [].\n\n"
    "ANSWER:\n{answer}\n\n"
    "Return JSON only. Example: [\"X is Y\", \"A causes B\"]"
)

_VERDICT_PROMPT = (
    "Given the CONTEXT and a list of CLAIMS, return a JSON array of booleans "
    "indicating whether each claim is directly supported by the CONTEXT.\n\n"
    "CONTEXT:\n{context}\n\n"
    "CLAIMS (JSON):\n{claims}\n\n"
    "Return JSON only. Example: [true, false, true]"
)

_QGEN_PROMPT = (
    "Generate exactly {n} concise standalone questions that the ANSWER below "
    "would be a good response to. Return a JSON array of strings.\n\n"
    "ANSWER:\n{answer}\n\n"
    "Return JSON only. Example: [\"What is X?\", \"How does Y work?\"]"
)


def _strip_think(text: str) -> str:
    """qwen3 emits <think>...</think>; strip it before JSON parsing."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json_array(text: str) -> list | None:
    text = _strip_think(text)
    match = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        out = json.loads(match.group(0))
        return out if isinstance(out, list) else None
    except json.JSONDecodeError:
        return None


async def faithfulness(answer: str, contexts: list[str]) -> float | None:
    """Fraction of answer claims directly supported by the retrieved context."""
    answer = (answer or "").strip()
    if not answer or not contexts:
        return None
    client = get_chat_client()

    claims_resp = await client.complete(
        messages=[{"role": "user", "content": _CLAIM_PROMPT.format(answer=answer)}],
        temperature=0.0,
        max_tokens=1500,
    )
    claims = _extract_json_array(
        claims_resp["choices"][0]["message"]["content"] or ""
    )
    if not claims:
        return None

    context_block = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(contexts))
    verdict_resp = await client.complete(
        messages=[
            {
                "role": "user",
                "content": _VERDICT_PROMPT.format(
                    context=context_block, claims=json.dumps(claims)
                ),
            }
        ],
        temperature=0.0,
        max_tokens=1500,
    )
    verdicts = _extract_json_array(
        verdict_resp["choices"][0]["message"]["content"] or ""
    )
    if not verdicts:
        return None

    bools = [bool(v) for v in verdicts][: len(claims)]
    if not bools:
        return None
    return sum(bools) / len(bools)


async def answer_relevancy(question: str, answer: str, n: int = 3) -> float | None:
    """Mean cosine sim between original question and `n` regenerated questions."""
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        return None

    client = get_chat_client()
    resp = await client.complete(
        messages=[{"role": "user", "content": _QGEN_PROMPT.format(n=n, answer=answer)}],
        temperature=0.0,
        max_tokens=1500,
    )
    generated = _extract_json_array(resp["choices"][0]["message"]["content"] or "")
    if not generated:
        return None

    from agentstack.core.ingestion.embedder import get_embedder

    embedder = get_embedder()
    vectors = embedder.embed([question] + [str(q) for q in generated])
    if len(vectors) < 2:
        return None
    qv = np.asarray(vectors[0])
    sims: list[float] = []
    for v in vectors[1:]:
        gv = np.asarray(v)
        denom = float((np.linalg.norm(qv) * np.linalg.norm(gv)) + 1e-12)
        sims.append(float(np.dot(qv, gv) / denom))
    return float(np.mean(sims)) if sims else None


async def run_ragas_metrics(payload: EvalInput) -> EvalScores:
    """Run faithfulness + answer relevancy.

    Each metric is independent and best-effort: if one fails (e.g. the judge
    returns un-parseable JSON), it stays None instead of failing the whole eval.
    """
    scores = EvalScores()
    try:
        scores.faithfulness = await faithfulness(payload.answer, payload.contexts)
    except Exception:
        logger.exception("faithfulness failed")
    try:
        scores.answer_relevancy = await answer_relevancy(payload.question, payload.answer)
    except Exception:
        logger.exception("answer_relevancy failed")
    return scores


def citation_accuracy(answer: str, contexts: list[str], citations: list[dict]) -> float:
    """Fraction of cited spans that actually appear in the cited context chunk.

    Lightweight, doesn't need an LLM:
      1. Extract [n] tokens from the answer.
      2. Take the surrounding sentence as the claim.
      3. Lookup contexts[n-1]; mark accurate if any 4+ char keyword from the
         claim appears in the context.
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
