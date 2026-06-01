import math

import pytest

from agentstack.core.retrieval.hybrid import reciprocal_rank_fusion


@pytest.mark.unit
def test_empty_inputs_yield_empty_output():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


@pytest.mark.unit
def test_single_list_orders_by_rank():
    out = reciprocal_rank_fusion([["a", "b", "c"]], rrf_k=60)
    assert [k for k, _ in out] == ["a", "b", "c"]
    # ranks 1, 2, 3 → scores 1/61, 1/62, 1/63 (strictly decreasing)
    scores = [s for _, s in out]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.unit
def test_doc_in_both_lists_beats_either_alone():
    """Standard RRF property: appearing in both lists pushes a doc above singletons."""
    out = dict(reciprocal_rank_fusion([["a", "b"], ["b", "c"]], rrf_k=60))
    # b is rank 2 in list 1 + rank 1 in list 2 → 1/62 + 1/61
    # a is rank 1 only in list 1 → 1/61
    # c is rank 2 only in list 2 → 1/62
    assert out["b"] > out["a"] > out["c"]
    assert math.isclose(out["b"], 1 / 62 + 1 / 61)
    assert math.isclose(out["a"], 1 / 61)
    assert math.isclose(out["c"], 1 / 62)


@pytest.mark.unit
def test_rrf_k_controls_score_scale():
    out_small = dict(reciprocal_rank_fusion([["x"]], rrf_k=1))
    out_large = dict(reciprocal_rank_fusion([["x"]], rrf_k=1000))
    assert out_small["x"] > out_large["x"]


@pytest.mark.unit
def test_result_is_sorted_descending_by_score():
    keys = list("abcdefg")
    out = reciprocal_rank_fusion(
        [keys[:], list(reversed(keys))], rrf_k=60
    )
    scores = [s for _, s in out]
    assert scores == sorted(scores, reverse=True)
