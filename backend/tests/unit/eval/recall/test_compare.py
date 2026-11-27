from eval.recall.compare import (
    Ranking,
    boosted,
    cosine,
    metrics,
    rrf,
    top,
    variant_rankings,
)


def test_cosine_and_top_rank_by_similarity() -> None:
    vectors = ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0))

    assert cosine((1.0, 0.0), (0.0, 1.0)) == 0.0
    assert top(vectors, (0.9, 0.1), 2) == [0, 1]


def test_rrf_rewards_agreement_and_breaks_ties_deterministically() -> None:
    assert rrf([[0, 1], [0, 1]], 20) == [0, 1]
    assert rrf([[1, 0], [0, 1]], 20) == [0, 1]


def test_metrics_reports_recall_and_mrr_at_five() -> None:
    rankings = [[3, 0, 1, 2], [0, 3, 1, 2]]
    expected = ((0, 3), (3,))

    result = metrics(rankings, expected)

    assert result.recall_at_5 == 1.0
    assert result.mrr_at_5 == 0.75


def test_metrics_ignores_hits_beyond_five() -> None:
    result = metrics([[0, 1, 2, 3, 4, 7]], ((7,),))

    assert result.recall_at_5 == 0.0
    assert result.mrr_at_5 == 0.0


def test_variant_rankings_distinguish_anchor_from_composed_branch() -> None:
    facts = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    queries = {
        "action": ((1.0, 0.0, 0.0),),
        "anchor": ((0.0, 1.0, 0.0),),
        "composed": ((0.9, 0.1, 0.0),),
    }
    lexical = ((2, 1, 0),)

    rankings = variant_rankings(facts, queries, lexical, rrf_k=1)

    assert set(rankings) == {
        "a_naked_top3",
        "b_composed_top5",
        "c_action_anchor_lex",
        "c2_action_composed_lex",
        "c3_action_anchor_composed_lex",
    }
    assert rankings["a_naked_top3"] == [[0, 1, 2]]
    assert rankings["b_composed_top5"] == [[0, 1, 2]]
    assert rankings["c_action_anchor_lex"][0][0] == 1
    assert rankings["c2_action_composed_lex"][0][0] == 0
    assert rankings["c3_action_anchor_composed_lex"][0][0] == 0


def test_boosted_uses_fused_scores_and_exact_entity_names() -> None:
    ranking = Ranking([0, 1], {0: 0.05, 1: 0.04})
    entities = (("anna",), ("lyra",))

    assert boosted(
        ranking,
        entities,
        (False, False),
        names=("lyra",),
        name_boost=0.02,
        critical_boost=0.0,
    ) == [1, 0]
    assert boosted(
        ranking,
        entities,
        (False, False),
        names=("ly",),
        name_boost=0.02,
        critical_boost=0.0,
    ) == [0, 1]


def test_boosted_ignores_facts_outside_candidate_pool() -> None:
    ranking = Ranking([0, 1, 2], {0: 0.05, 1: 0.04, 2: 10.0})

    assert boosted(
        ranking,
        ((), (), ("lyra",)),
        (False, False, False),
        names=("lyra",),
        name_boost=0.02,
        critical_boost=0.0,
        pool=2,
    ) == [0, 1]


def test_boosted_deduplicates_identical_content_before_selection() -> None:
    ranking = Ranking([0, 1], {0: 0.05, 1: 0.04})

    assert boosted(
        ranking,
        ((), ()),
        (False, False),
        names=(),
        name_boost=0.0,
        critical_boost=0.0,
        contents=("Lyra, kept the key!", "lyra kept the key"),
    ) == [0]


def test_boosted_does_not_scale_boosts_beyond_rrf_units() -> None:
    ranking = Ranking([0, 1], {0: 1.0, 1: 0.5})

    assert boosted(
        ranking,
        ((), ("lyra",)),
        (False, False),
        names=("lyra",),
        name_boost=0.02,
        critical_boost=0.0,
    ) == [0, 1]
