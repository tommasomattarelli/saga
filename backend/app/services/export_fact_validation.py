from collections import defaultdict
from uuid import UUID

from app.schemas.campaign_export import CampaignExport
from app.services.export_integrity import _require, _unique


def validate_facts(archive: CampaignExport, ordered_members: dict[UUID, list[UUID]]) -> None:
    campaign_id = archive.campaign.id
    turns = {row.id: row for row in archive.turns}
    policies = {row.id: row for row in archive.memory_policies}
    batches = {row.id: row for row in archive.memory_batches}
    generations = {row.id: row for row in archive.generations}
    facts = {row.id: row for row in archive.memory_facts}
    _unique(archive.fact_sources, lambda row: (row.fact_id, row.turn_id), "fact source")
    _unique(
        [fact for fact in archive.memory_facts if fact.batch_id is not None],
        lambda fact: (fact.batch_id, fact.ordinal),
        "fact ordinal",
    )
    sources_by_fact: dict[UUID, list[UUID]] = defaultdict(list)
    for fact in archive.memory_facts:
        if fact.batch_id is None:
            _require(
                fact.policy_id is None
                and fact.ordinal is None
                and fact.category is None
                and fact.assertion_type is None
                and fact.fact_metadata is None
                and fact.generation_id is None
                and fact.schema_version is None,
                "Legacy fact has partial production provenance.",
            )
            continue
        _require(
            fact.batch_id in batches
            and fact.policy_id in policies
            and fact.generation_id in generations,
            "Fact provenance reference is invalid.",
        )
        assert fact.policy_id is not None and fact.generation_id is not None
        _require(fact.fact_metadata is not None, "Generated fact metadata is missing.")
        assert fact.fact_metadata is not None
        _require(
            fact.category is not None
            and fact.assertion_type is not None
            and fact.ordinal is not None
            and fact.schema_version == 1
            and fact.turn_number is None
            and fact.entity_name is None
            and fact.entity_type is None
            and bool(fact.content.strip()),
            "Generated fact contract is incomplete.",
        )
        batch = batches[fact.batch_id]
        _require(fact.policy_id == batch.policy_id, "Fact policy differs from its batch.")
        generation = generations[fact.generation_id]
        _require(
            generation.role in {"facts", "batch"}
            and generation.batch_id == fact.batch_id
            and generation.policy_id == fact.policy_id,
            "Fact generation provenance is inconsistent.",
        )
        allowed = {
            level.name for level in policies[fact.policy_id].payload.facts.importance_levels
        }
        _require(
            fact.fact_metadata.importance.level in allowed,
            "Fact importance is outside its policy.",
        )
    for source in archive.fact_sources:
        _require(
            source.campaign_id == campaign_id
            and source.fact_id in facts
            and source.turn_id in turns
            and source.batch_id in batches,
            "Fact source reference is invalid.",
        )
        _require(
            facts[source.fact_id].batch_id == source.batch_id, "Fact source batch is inconsistent."
        )
        _require(
            source.turn_id in ordered_members.get(source.batch_id, []),
            "Fact source is outside batch membership.",
        )
        sources_by_fact[source.fact_id].append(source.turn_id)
    for fact in archive.memory_facts:
        if fact.batch_id is not None:
            _require(bool(sources_by_fact.get(fact.id)), "Generated fact has no source turn.")
