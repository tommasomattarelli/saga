from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class Metrics:
    recall_at_5: float
    mrr_at_5: float


class Ranking(list[int]):
    def __init__(self, order: Sequence[int], scores: Mapping[int, float]) -> None:
        super().__init__(order)
        self.scores = dict(scores)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def top(vectors: Sequence[Sequence[float]], query: Sequence[float], limit: int) -> list[int]:
    return sorted(range(len(vectors)), key=lambda index: -cosine(query, vectors[index]))[:limit]


def rrf_scores(rankings: Sequence[Sequence[int]], k: int) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, index in enumerate(ranking, start=1):
            scores[index] = scores.get(index, 0.0) + 1.0 / (k + rank)
    return scores


def rrf(rankings: Sequence[Sequence[int]], k: int) -> Ranking:
    scores = rrf_scores(rankings, k)
    return Ranking(sorted(scores, key=lambda index: (-scores[index], index)), scores)


def metrics(rankings: Sequence[Sequence[int]], expected: Sequence[Sequence[int]]) -> Metrics:
    if not expected:
        raise ValueError("At least one labelled query is required.")
    recall = reciprocal = 0.0
    for ranking, wanted in zip(rankings, expected, strict=True):
        hits = [rank for rank, index in enumerate(ranking[:5], start=1) if index in wanted]
        recall += len(hits) / len(wanted)
        reciprocal += 1 / min(hits) if hits else 0.0
    return Metrics(round(recall / len(expected), 3), round(reciprocal / len(expected), 3))


def variant_rankings(
    fact_vectors: Sequence[Sequence[float]],
    queries: Mapping[str, Sequence[Sequence[float]]],
    lexical: Sequence[Sequence[int]],
    *,
    rrf_k: int,
    pool: int = 25,
) -> dict[str, list[Sequence[int]]]:
    action = queries["action"]
    anchor = queries["anchor"]
    composed = queries["composed"]
    count = len(action)
    if not (len(anchor) == len(composed) == len(lexical) == count):
        raise ValueError("Query vectors and lexical rankings must have the same length.")

    def fused(second: Sequence[Sequence[float]]) -> list[Sequence[int]]:
        return [
            rrf(
                [
                    top(fact_vectors, action[index], pool),
                    top(fact_vectors, second[index], pool),
                    lexical[index],
                ],
                rrf_k,
            )
            for index in range(count)
        ]

    return {
        "a_naked_top3": [top(fact_vectors, vector, 3) for vector in action],
        "b_composed_top5": [top(fact_vectors, vector, 5) for vector in composed],
        "c_action_anchor_lex": fused(anchor),
        "c2_action_composed_lex": fused(composed),
        "c3_action_anchor_composed_lex": [
            rrf(
                [
                    top(fact_vectors, action[index], pool),
                    top(fact_vectors, anchor[index], pool),
                    top(fact_vectors, composed[index], pool),
                    lexical[index],
                ],
                rrf_k,
            )
            for index in range(count)
        ],
    }


def _normalized(content: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", content.lower()).split())


def _deduplicate(order: Sequence[int], contents: Sequence[str]) -> list[int]:
    normalized = {index: _normalized(contents[index]) for index in order}
    kept: list[int] = []
    for index in order:
        if any(
            SequenceMatcher(None, normalized[index], normalized[other]).ratio() >= 1.0
            for other in kept
        ):
            continue
        kept.append(index)
    return kept


def boosted(
    ranking: Ranking,
    entities: Sequence[Sequence[str]],
    critical: Sequence[bool],
    *,
    names: Sequence[str],
    name_boost: float,
    critical_boost: float,
    contents: Sequence[str] | None = None,
    pool: int = 25,
) -> list[int]:
    lowered = {name.lower() for name in names}
    scored: list[tuple[float, int]] = []
    for index in list(ranking)[:pool]:
        score = ranking.scores[index]
        if any(name.lower() in lowered for name in entities[index]):
            score += name_boost
        if critical[index]:
            score += critical_boost
        scored.append((score, index))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    order = [index for _, index in scored]
    if contents is not None:
        order = _deduplicate(order, contents)
    return order[:5]
