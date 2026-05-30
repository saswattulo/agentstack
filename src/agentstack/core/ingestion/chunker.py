"""Chunking strategies.

Recursive: deterministic, fast, char-based. Default.
Semantic:  groups consecutive sentences whose embeddings are similar above a
           cosine threshold. Higher cost (one embedder pass) but better for
           dense prose. See ADR 002.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from agentstack.config import settings


@dataclass
class Chunk:
    index: int
    text: str
    start: int | None = None
    end: int | None = None
    meta: dict | None = None


class Chunker(Protocol):
    def split(self, text: str) -> list[Chunk]: ...


_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]


class RecursiveChunker:
    def __init__(self, chunk_size: int | None = None, chunk_overlap: int | None = None) -> None:
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap

    def split(self, text: str) -> list[Chunk]:
        if not text.strip():
            return []
        pieces = self._recursive_split(text, _SEPARATORS)
        chunks = self._merge_with_overlap(pieces)
        return [Chunk(index=i, text=c) for i, c in enumerate(chunks)]

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text]
        for i, sep in enumerate(separators):
            if sep == "":
                return self._fixed_split(text)
            if sep in text:
                parts = text.split(sep)
                rest = separators[i + 1 :]
                out: list[str] = []
                for p in parts:
                    if len(p) <= self.chunk_size:
                        out.append(p)
                    else:
                        out.extend(self._recursive_split(p, rest))
                return out
        return self._fixed_split(text)

    def _fixed_split(self, text: str) -> list[str]:
        return [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]

    def _merge_with_overlap(self, pieces: list[str]) -> list[str]:
        chunks: list[str] = []
        current = ""
        for piece in pieces:
            if not piece:
                continue
            candidate = (current + " " + piece).strip() if current else piece
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                if self.chunk_overlap and chunks:
                    tail = current[-self.chunk_overlap :]
                    current = (tail + " " + piece).strip()
                else:
                    current = piece
                if len(current) > self.chunk_size:
                    chunks.extend(self._fixed_split(current))
                    current = ""
        if current:
            chunks.append(current)
        return [c for c in chunks if c.strip()]


class SemanticChunker:
    """Sentence-grouping chunker driven by embedding similarity.

    Cheaper variant of the LangChain SemanticChunker — no extra deps beyond
    the local embedder.
    """

    def __init__(
        self,
        embedder=None,
        max_chunk_chars: int | None = None,
        breakpoint_percentile: float = 0.90,
    ) -> None:
        from agentstack.core.ingestion.embedder import get_embedder

        self.embedder = embedder or get_embedder()
        self.max_chunk_chars = max_chunk_chars or (settings.chunk_size * 4)
        self.breakpoint_percentile = breakpoint_percentile

    def split(self, text: str) -> list[Chunk]:
        sentences = _split_sentences(text)
        if len(sentences) <= 1:
            return [Chunk(index=0, text=text.strip())] if text.strip() else []

        embeddings = np.asarray(self.embedder.embed(sentences))
        distances = []
        for i in range(len(sentences) - 1):
            a, b = embeddings[i], embeddings[i + 1]
            sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
            distances.append(1.0 - sim)

        threshold = float(np.percentile(distances, self.breakpoint_percentile * 100))

        chunks: list[Chunk] = []
        buf: list[str] = [sentences[0]]
        idx = 0
        for i, dist in enumerate(distances):
            next_sentence = sentences[i + 1]
            joined_len = sum(len(s) for s in buf) + len(next_sentence)
            if dist >= threshold or joined_len > self.max_chunk_chars:
                chunks.append(Chunk(index=idx, text=" ".join(buf).strip()))
                idx += 1
                buf = [next_sentence]
            else:
                buf.append(next_sentence)
        if buf:
            chunks.append(Chunk(index=idx, text=" ".join(buf).strip()))
        return [c for c in chunks if c.text]


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def get_chunker(strategy: str, chunk_size: int, chunk_overlap: int) -> Chunker:
    if strategy == "recursive":
        return RecursiveChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if strategy == "semantic":
        return SemanticChunker(max_chunk_chars=chunk_size * 4)
    raise ValueError(f"Unknown chunking strategy: {strategy}")
