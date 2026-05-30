"""Versioned prompt templates. Keep prompts here, never inline in feature code."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    template: str

    def render(self, **kwargs) -> str:
        return self.template.format(**kwargs)


ROUTER_V1 = PromptTemplate(
    name="router",
    version="v1",
    template=(
        "You are a router for a retrieval-augmented assistant. Classify the user's "
        "question into exactly one of these intents:\n"
        "- factual:        a direct lookup answerable from the indexed corpus\n"
        "- analytical:     requires reasoning over multiple chunks\n"
        "- comparison:     compares two or more concepts/entities\n"
        "- web:            fresh/external info; corpus unlikely to contain answer\n"
        "- code:           involves computation that benefits from running code\n"
        "- conversational: chit-chat or clarification\n\n"
        "User question:\n{question}\n\n"
        "Reply with ONLY the intent label."
    ),
)


SYNTHESIZER_V1 = PromptTemplate(
    name="synthesizer",
    version="v1",
    template=(
        "You are a careful research assistant. Answer the user's question using ONLY "
        "the provided context. If the context is insufficient, say so explicitly — "
        "do not fabricate.\n\n"
        "Cite every factual claim with bracketed numeric citations like [1], [2] that "
        "map to the chunks in the context block. Multiple citations for one claim are "
        "fine: [1][3].\n\n"
        "Question:\n{question}\n\n"
        "Context:\n{context}\n\n"
        "Answer:"
    ),
)


REFLECTION_V1 = PromptTemplate(
    name="reflection",
    version="v1",
    template=(
        "Critique this answer for groundedness and citation accuracy. For each "
        "factual claim, verify it appears in the cited chunk. Report:\n"
        "- unsupported_claims: list of claims not in the context\n"
        "- missing_citations: claims without citations\n"
        "- confidence:        0..1\n\n"
        "Question: {question}\nAnswer: {answer}\nContext: {context}\n\n"
        "Return JSON only."
    ),
)
