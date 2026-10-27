# ADR 012 — Evaluation: custom LLM judge on full chunk text, scored asynchronously

- **Status:** Accepted
- **Date:** 2026-10-25 (records the Week 3 design plus the Week 6 corrections)

## Context

Every fresh answer should get quality scores that are persisted and trendable, without adding latency to the query path. The obvious off-the-shelf choice is RAGAS. Two constraints pushed against it:

- **Groq only, no OpenAI SDK** (ADR-005). RAGAS's default judges and embeddings assume OpenAI, and its `ragas` → `langchain-community` → vertexai dependency tree is heavy for three metrics.
- **qwen3 emits `<think>…</think>` blocks**, and the judge prompts need control over JSON-only output and parsing.

## Decision

Implement the metrics in `core/eval/metrics.py`, following RAGAS's published definitions, and run them in a Celery task after every non-cached query.

| Metric | How | LLM calls |
|---|---|---|
| Faithfulness | Extract atomic claims from the answer → judge each against the cited chunks → supported / total | 2 |
| Answer relevancy | Generate 3 questions the answer would fit → mean cosine (local embedder) against the real question | 1 |
| Citation accuracy | For each `[n]`, does a 4+ char keyword from its sentence appear in chunk *n*? Lexical, no LLM | 0 |

- `query_service` enqueues `eval_query_task` after writing the `QueryLog`. Cache hits skip it (that answer was already scored when first generated).
- `GET /api/v1/eval/results/{query_id}` returns `{"status": "pending"}` until the row exists, so polling clients don't see spurious 404s.
- Each metric fails independently: an unparseable judge reply or a provider error leaves that score `null` and does not fail the task.
- The judge is the same `get_chat_client()` as synthesis, fallback included.

## Week 6 corrections

Benchmarking (`docs/benchmarks.md`) showed the production metrics under-reporting quality:

1. **Judge context.** The runner fed the judge `chunk_metadata.content_preview` (capped at 240 chars). Claims supported later in a ~512-char chunk were marked unsupported. Faithfulness read 0.716 on previews vs 0.986 on full text. The runner now fetches full chunk text from Qdrant and falls back to previews only if Qdrant is unavailable.
2. **Citation indexing.** `[n]` markers index the *retrieved* top-k, but the runner passed only the *cited* chunks, deduplicated and re-ordered, so `[4]` in a two-citation answer scored as wrong. Citation accuracy is now computed against a list aligned to marker indices: 0.525 → 0.93 on the primary model.
3. **Citation formats.** The fallback model (`gpt-oss-120b`) writes `【n】`. These are normalized to `[n]` before extraction, so its citations are no longer silently dropped.

## Consequences

- An eval costs 3 LLM calls per fresh answer. On Groq's on-demand tier (e.g. 1,000 output tokens/min per model) eval competes with live traffic, and under load some scores come back `null`. `benchmarks/rescore_eval.py` re-scores offline with pacing.
- Same-family self-judging inflates scores somewhat. The benchmark's model-free keyword check (91%) is the independent cross-check.
- Citation accuracy is lexical: it catches pointing at the wrong chunk, not subtle misstatements.
- `ragas` is still listed in `pyproject.toml` but unused by the pipeline; removing it is a follow-up.
- Eval gauges are set in the worker process, so they aren't visible on the API's `/metrics` (ADR-009).

## Not done yet

- `GET /eval/aggregate` (rolling averages) and `POST /eval/runs/{id}` (manual re-run) are stubs.
- Context precision / recall columns exist but are never populated.
- No separate judge model or judge-vs-human calibration set.

## Revisit when

- A stronger, independent judge model is available on the same key → split the judge client from the synthesis client.
- Eval volume regularly hits provider quotas → sample (e.g. 20% of traffic) instead of scoring everything.
- The golden set grows past ~100 items → wire `benchmarks/run_e2e.py` into CI as a regression gate.
