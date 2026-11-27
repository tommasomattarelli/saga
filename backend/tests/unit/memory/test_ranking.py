import uuid

import pytest

from app.memory.document_contracts import (
    CanonicalReference,
    FactEntity,
    FactImportance,
    FactMetadata,
)
from app.memory.ranking import rank_hits
from app.memory.recall_config import RecallConfig
from app.memory.semantic import HybridHit


def _hit(content: str, score: float, *, critical: bool = False, name: str = "") -> HybridHit:
    entities = ()
    if name:
        entities = (FactEntity(name=name, type="npc", role="subject"),)
    metadata = FactMetadata(
        entities=entities,
        attribution=(),
        temporal_references=(),
        importance=FactImportance(level="critical" if critical else "ordinary", reason="test"),
    )
    return HybridHit(uuid.uuid4(), content, "event", "occurrence", metadata, score)


def test_critical_boost_reorders_hits() -> None:
    ordinary = _hit("A minor clue.", 0.04)
    critical = _hit("A binding oath.", 0.03, critical=True)
    config = RecallConfig.model_validate({"boosts": {"critical": 0.5}})

    assert [hit.content for hit in rank_hits([ordinary, critical], config=config)] == [
        "A binding oath.",
        "A minor clue.",
    ]


def test_entity_boosts_use_canonical_ref_and_gazetteer_name() -> None:
    entity = FactEntity(
        name="Lyra",
        type="npc",
        role="subject",
        canonical_ref=CanonicalReference(type="npc", id="lyra-id"),
    )
    metadata = FactMetadata(
        entities=(entity,),
        attribution=(),
        temporal_references=(),
        importance=FactImportance(level="ordinary", reason="test"),
    )
    hit = HybridHit(
        fact_id=uuid.uuid4(),
        content="Lyra spoke.",
        category="event",
        assertion_type="statement",
        fact_metadata=metadata,
        score=0.01,
    )
    config = RecallConfig.model_validate(
        {"boosts": {"entity_canonical_ref": 0.2, "entity_name": 0.1}}
    )

    ranked = rank_hits(
        [hit],
        config=config,
        gazetteer=["Lyra"],
        canonical_refs=frozenset({("npc", "lyra-id")}),
    )

    assert ranked[0].score == pytest.approx(0.31)


def test_dedup_keeps_highest_scoring_representative() -> None:
    low = _hit("Lyra kept the key!", 0.02)
    high = _hit("lyra kept the key", 0.05)

    assert [hit.score for hit in rank_hits([low, high], config=RecallConfig())] == [0.05]


def test_recency_tiebreak_prefers_newer_fact_without_multiplying() -> None:
    config = RecallConfig.model_validate({"boosts": {"recency_tiebreak": 0.1}})
    old = _hit("Old event.", 0.02)
    new = _hit("New event.", 0.02)

    ranked = rank_hits([old, new], config=config, ages={old.fact_id: 10, new.fact_id: 0})

    assert [hit.content for hit in ranked] == ["New event.", "Old event."]
    assert ranked[0].score == pytest.approx(0.12)


def test_unknown_age_gets_no_recency_bonus() -> None:
    config = RecallConfig.model_validate({"boosts": {"recency_tiebreak": 0.1}})
    known = _hit("Known event.", 0.02)
    unknown = _hit("Unknown event.", 0.02)

    ranked = rank_hits([unknown, known], config=config, ages={known.fact_id: 1})

    assert ranked[0].content == "Known event."
    assert ranked[1].score == pytest.approx(0.02)


def test_critical_cap_holds_with_spare_slots() -> None:
    config = RecallConfig.model_validate(
        {"inject_limit": 5, "critical_always_include": True, "max_critical_inject": 1}
    )
    hits = [
        _hit("Oath one.", 0.06, critical=True),
        _hit("Oath two.", 0.05, critical=True),
        _hit("Oath three.", 0.04, critical=True),
        _hit("Detail one.", 0.03),
        _hit("Detail two.", 0.02),
    ]

    selected = rank_hits(hits, config=config)

    assert len(selected) == 3
    assert (
        sum(
            1
            for hit in selected
            if hit.fact_metadata and hit.fact_metadata.importance.level == "critical"
        )
        == 1
    )


def test_critical_cap_is_ignored_when_injection_is_disabled() -> None:
    config = RecallConfig.model_validate(
        {"critical_always_include": False, "max_critical_inject": 0}
    )
    hits = [_hit("Critical clue.", 0.01, critical=True), _hit("Plain clue.", 0.02)]

    assert len(rank_hits(hits, config=config)) == 2


def test_critical_injection_fills_the_same_slots_with_a_hard_cap() -> None:
    config = RecallConfig.model_validate(
        {"inject_limit": 2, "critical_always_include": True, "max_critical_inject": 1}
    )
    hits = [
        _hit("Oath one.", 0.01, critical=True),
        _hit("Oath two.", 0.02, critical=True),
        _hit("Minor detail.", 0.03),
        _hit("Another detail.", 0.04),
    ]

    selected = rank_hits(hits, config=config)

    assert len(selected) == 2
    assert [hit.content for hit in selected] == ["Oath two.", "Another detail."]


def test_inject_limit_bounds_output() -> None:
    hits = [_hit(f"Distinct fact {index}.", 0.01 + index / 1000) for index in range(10)]

    assert len(rank_hits(hits, config=RecallConfig())) == 5
