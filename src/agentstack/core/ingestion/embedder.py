"""Local embedding via sentence-transformers.

Loaded once per process. Encodes in batches; for large jobs the caller should
split work across Celery worker processes.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from agentstack.config import settings
from agentstack.infra.logging import get_logger

logger = get_logger(__name__)


class LocalEmbedder:
    def __init__(self, model_name: str | None = None, device: str | None = None) -> None:
        self.model_name = model_name or settings.embedding_model
        self.device = device or settings.embedding_device
        logger.info("loading embedding model", model=self.model_name, device=self.device)
        self._model = SentenceTransformer(self.model_name, device=self.device)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        if not texts:
            return []
        vectors: np.ndarray = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vectors.tolist()

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


@lru_cache(maxsize=1)
def get_embedder() -> LocalEmbedder:
    return LocalEmbedder()
