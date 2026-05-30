import pytest

from agentstack.core.eval.metrics import citation_accuracy


@pytest.mark.unit
def test_no_citations_returns_zero():
    assert citation_accuracy("No citations here.", ["whatever"], []) == 0.0


@pytest.mark.unit
def test_matching_keywords_count_as_accurate():
    answer = "The capital is Paris [1]."
    contexts = ["Paris is the capital of France"]
    assert citation_accuracy(answer, contexts, []) == 1.0


@pytest.mark.unit
def test_out_of_range_citation_counts_as_miss():
    answer = "Atlas Mountains lie in Morocco [3]."
    contexts = ["only one context"]
    assert citation_accuracy(answer, contexts, []) == 0.0
