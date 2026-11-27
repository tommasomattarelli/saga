from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import replace
from difflib import SequenceMatcher

from app.memory.recall_config import RecallConfig
from app.memory.semantic import HybridHit


def _is_critical(hit: HybridHit) -> bool:
    return bool(hit.fact_metadata and hit.fact_metadata.importance.level == "critical")


def _normalized(content: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", content.lower()).split())


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalized(left), _normalized(right)).ratio()


def rank_hits(
    hits: Sequence[HybridHit],
    *,
    config: RecallConfig,
    gazetteer: Sequence[str] = (),
    canonical_refs: frozenset[tuple[str, str]] = frozenset(),
    ages: Mapping[uuid.UUID, int] | None = None,
) -> list[HybridHit]:
    gazetteer_lower = {name.lower() for name in gazetteer}
    boosted: list[HybridHit] = []
    for hit in hits:
        score = hit.score
        metadata = hit.fact_metadata
        if metadata and any(
            entity.canonical_ref is not None
            and (entity.canonical_ref.type, entity.canonical_ref.id) in canonical_refs
            for entity in metadata.entities
        ):
            score += config.boosts.entity_canonical_ref
        if metadata and any(
            entity.name.lower() in gazetteer_lower for entity in metadata.entities
        ):
            score += config.boosts.entity_name
        if _is_critical(hit):
            score += config.boosts.critical
        age = ages.get(hit.fact_id) if ages is not None else None
        if age is not None:
            score += config.boosts.recency_tiebreak / (1 + age)
        boosted.append(replace(hit, score=score))

    ordered = sorted(boosted, key=lambda hit: (-hit.score, str(hit.fact_id)))
    threshold = config.dedup.similarity_threshold if config.dedup.enabled else 2.0
    deduplicated: list[HybridHit] = []
    for hit in ordered:
        if any(_similarity(hit.content, kept.content) >= threshold for kept in deduplicated):
            continue
        deduplicated.append(hit)

    selected: list[HybridHit] = []
    if config.critical_always_include:
        selected.extend(
            [hit for hit in deduplicated if _is_critical(hit)][: config.max_critical_inject]
        )
    selected = selected[: config.inject_limit]
    for hit in deduplicated:
        if len(selected) >= config.inject_limit:
            break
        if hit in selected:
            continue
        if (
            config.critical_always_include
            and _is_critical(hit)
            and sum(_is_critical(item) for item in selected) >= config.max_critical_inject
        ):
            continue
        selected.append(hit)
    return selected
