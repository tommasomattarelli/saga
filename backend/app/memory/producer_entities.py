from collections import defaultdict

from app.memory.batch_source_contracts import BatchInput, NPCSourceResult
from app.memory.document_contracts import CanonicalReference, FactEntity
from app.memory.producer_contracts import GeneratedFact


def resolve_entities(fact: GeneratedFact, source: BatchInput) -> tuple[FactEntity, ...]:
    candidates: dict[tuple[str, str], set[str]] = defaultdict(set)
    for turn in source.turns:
        if turn.reference not in fact.source_turns:
            continue
        for operation in turn.operations or ():
            payload = operation.payload
            if payload.outcome != "succeeded":
                continue
            if (
                payload.origin == "npc"
                and payload.name in {"create_npc", "invoke_npc"}
                and isinstance(payload.result, NPCSourceResult)
            ):
                name = payload.arguments.get("name")
                if isinstance(name, str) and name.strip():
                    candidates[("npc", name.strip().casefold())].add(payload.result.npc_id)
            if payload.origin == "tool" and payload.name == "update_quest":
                name, quest_id = payload.arguments.get("name"), payload.arguments.get("quest_id")
                if (
                    isinstance(name, str)
                    and name.strip()
                    and isinstance(quest_id, str)
                    and quest_id
                ):
                    candidates[("quest", name.strip().casefold())].add(quest_id)
    entities = []
    for entity in fact.entities:
        ids = candidates[(entity.type, entity.name.strip().casefold())]
        canonical_ref = (
            CanonicalReference(type=entity.type, id=next(iter(ids))) if len(ids) == 1 else None
        )
        entities.append(FactEntity(**entity.model_dump(), canonical_ref=canonical_ref))
    return tuple(entities)
