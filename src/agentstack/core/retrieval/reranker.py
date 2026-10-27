"""Cross-encoder reranker. Optional, gated by RERANKER_ENABLED.

Week 2 / stretch — wraps a sentence-transformers CrossEncoder.
"""

from __future__ import annotations

from functools import lru_cache

from agentstack.config import settings
from agentstack.core.retrieval.hybrid import RetrievedChunk


class CrossEncoderReranker:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.reranker_model
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, device=settings.embedding_device)
        return self._model

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        if not settings.reranker_enabled or not chunks:
            return chunks[: top_k or len(chunks)]
        model = self._ensure_model()
        pairs = [(query, c.text) for c in chunks]
        scores = model.predict(pairs)
        ranked = sorted(
            zip(chunks, scores, strict=True),
            key=lambda x: float(x[1]),
            reverse=True,
        )
        out = []
        for chunk, score in ranked[: top_k or len(chunks)]:
            chunk.score = float(score)
            out.append(chunk)
        return out


# One instance per process: the model is cached on the instance and is ~1.1 GB.
@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoderReranker:
    return CrossEncoderReranker()
