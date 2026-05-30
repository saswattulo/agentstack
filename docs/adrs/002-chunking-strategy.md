# ADR 002 — Chunking: recursive default, semantic optional

- **Status:** Accepted
- **Date:** 2026-05-30

## Context

Two chunking strategies are commonly cited:

- **Recursive character splitter** — split on a hierarchy of separators (`\n\n`, `\n`, `. `, `, `, ` `), merge until the budget is hit. Deterministic, fast, dependency-free.
- **Semantic chunking** — embed sentences, group consecutive sentences whose pairwise distance is below a percentile threshold. Better for dense prose; pays one embedding pass over each document.

A third option (token-aware splitting) was rejected because we are not constrained by a fixed-window context model at ingest time — synthesis uses far fewer tokens than the worst-case document length.

## Decision

Recursive is the default. Semantic is selectable per-collection via `chunking_strategy` on `Collection`.

## Rationale

- Recursive is fast enough to ingest a hundreds-of-page PDF in seconds and produces predictable chunk sizes — a property hybrid search benefits from.
- Semantic improves retrieval precision on continuous prose but doubles ingestion cost and produces variable-length chunks that interact poorly with naive top-k retrieval. We don't want to pay that for code or markdown.
- Per-collection selection gives users (and Week 3's eval suite) a knob to compare strategies on a fixed golden set.

## Consequences

- The `Collection` row stores the strategy alongside `chunk_size` and `chunk_overlap` so re-ingestion is deterministic.
- A semantic-chunked collection embeds twice (once during chunking, once for the final chunk vectors). Worth documenting cost in the README before promoting it.

## Revisit when

- Eval data shows semantic outperforming recursive by >5% faithfulness on representative docs.
- A token-budget-aware chunker becomes worth the dependency (likely after we add per-document context budgets in the synthesizer).
