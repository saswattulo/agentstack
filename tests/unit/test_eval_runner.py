"""Eval runner: judge sees full chunk text, and citation accuracy follows the answer's [n] numbering."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agentstack.core.eval.metrics import EvalScores
from agentstack.core.eval.runner import evaluate_and_persist


@pytest.mark.unit
async def test_citation_accuracy_uses_answer_marker_indices():
    # The answer cites retrieved chunks [2] and [4]; only two chunks are cited.
    log = SimpleNamespace(
        question="q",
        answer="Qdrant is the vector store [2]. Argon2id hashes passwords [4].",
        collection_id=uuid4(),
        citations=[
            {"index": 2, "chunk_id": "c2", "preview": "Qdrant…"},
            {"index": 4, "chunk_id": "c4", "preview": "Argon2id…"},
        ],
    )
    full = {"c2": "We use Qdrant as the vector store.", "c4": "Passwords are hashed with Argon2id."}
    session = MagicMock()
    session.get = AsyncMock(return_value=log)
    session.commit = AsyncMock()
    judge = AsyncMock(return_value=EvalScores(faithfulness=1.0, answer_relevancy=0.9))

    with (
        patch("agentstack.core.eval.runner._chunk_texts", AsyncMock(return_value=full)),
        patch("agentstack.core.eval.runner.run_ragas_metrics", judge),
    ):
        scores = await evaluate_and_persist(uuid4(), session)

    assert scores.citation_accuracy == 1.0
    assert judge.await_args.args[0].contexts == list(full.values())
