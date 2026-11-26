from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from eval.attribution.manifest import DECLARATIVE, ExpectedClaim, Scenario


@dataclass(frozen=True)
class ScenarioScore:
    name: str
    matched: int
    expected: int
    coverage: float
    wrong_speaker: tuple[str, ...]
    bundled: tuple[str, ...]
    forbidden_hits: tuple[str, ...]
    extra_declarative: tuple[str, ...]
    tokens: dict[str, int | None]
    latency_ms: float
    raw_output: str

    @property
    def hard_fail(self) -> bool:
        return bool(self.wrong_speaker or self.bundled or self.forbidden_hits)


def _covers(content: str, phrases: tuple[str, ...]) -> bool:
    text = content.casefold()
    return all(phrase.casefold() in text for phrase in phrases)


def _speakers(fact: dict[str, object]) -> tuple[tuple[str, str], ...]:
    entities = cast(list[dict[str, object]], fact.get("entities", []))
    attribution = cast(list[int], fact.get("attribution", []))
    return tuple(
        (str(entities[index]["name"]).casefold(), str(entities[index]["type"]))
        for index in attribution
    )


def _same_speaker(fact: dict[str, object], expected: ExpectedClaim) -> bool:
    if expected.speaker is None:
        return not _speakers(fact) and expected.kind == "occurrence"
    return _speakers(fact) == ((expected.speaker.name.casefold(), expected.speaker.type),)


def score_scenario(scenario: Scenario, evidence: dict[str, object]) -> ScenarioScore:
    facts = cast(list[dict[str, object]], evidence.get("facts", []))
    matched: set[int] = set()
    wrong: list[str] = []
    bundled: list[str] = []
    extra: list[str] = []

    for index, expected in enumerate(scenario.expected):
        covering = [
            fact
            for fact in facts
            if _covers(str(fact.get("content", "")), expected.key_phrases)
            and fact.get("assertion_type") == expected.kind
        ]
        for fact in covering:
            if _same_speaker(fact, expected):
                matched.add(index)
            else:
                wrong.append(f"{scenario.name}: claim {index} attributed to {_speakers(fact)}")

    for fact in facts:
        covered = [
            index
            for index, expected in enumerate(scenario.expected)
            if _covers(str(fact.get("content", "")), expected.key_phrases)
        ]
        claim_speakers: set[tuple[str, str]] = set()
        for index in covered:
            speaker = scenario.expected[index].speaker
            if speaker is not None:
                claim_speakers.add((speaker.name, speaker.type))
        if len(claim_speakers) > 1 or len(set(_speakers(fact))) > 1:
            bundled.append(f"{scenario.name}: one fact covers {sorted(claim_speakers)}")
        if fact.get("assertion_type") in DECLARATIVE and not covered:
            extra.append(f"{scenario.name}: {fact.get('content', '')}")

    forbidden_hits: list[str] = []
    for rule in scenario.forbidden:
        if rule.kinds:
            for fact in facts:
                if fact.get("assertion_type") in rule.kinds:
                    forbidden_hits.append(
                        f"{scenario.name}: forbidden {fact.get('assertion_type')}"
                    )
        elif rule.claim is not None and rule.speaker is not None:
            expected = scenario.expected[rule.claim]
            target = (rule.speaker.name.casefold(), rule.speaker.type)
            for fact in facts:
                if _covers(
                    str(fact.get("content", "")), expected.key_phrases
                ) and target in _speakers(fact):
                    forbidden_hits.append(f"{scenario.name}: forbidden claim {rule.claim}")

    total = len(scenario.expected)
    return ScenarioScore(
        name=scenario.name,
        matched=len(matched),
        expected=total,
        coverage=len(matched) / total if total else 1.0,
        wrong_speaker=tuple(wrong),
        bundled=tuple(bundled),
        forbidden_hits=tuple(forbidden_hits),
        extra_declarative=tuple(extra),
        tokens=cast(
            dict[str, int | None], evidence.get("tokens", {"input": None, "output": None})
        ),
        latency_ms=cast(float, evidence.get("latency_ms", 0.0)),
        raw_output=str(evidence.get("raw", "")),
    )


def overall(scores: tuple[ScenarioScore, ...], real_name: str) -> dict[str, object]:
    total_expected = sum(score.expected for score in scores if score.name != real_name)
    total_matched = sum(score.matched for score in scores if score.name != real_name)
    real = next((score for score in scores if score.name == real_name), None)
    green = (
        not any(score.hard_fail for score in scores)
        and real is not None
        and real.matched == real.expected
        and total_expected > 0
        and total_matched / total_expected >= 0.8
    )
    return {
        "green": green,
        "synthetic_coverage": total_matched / total_expected if total_expected else 0.0,
        "real_covered": real.matched if real else 0,
        "real_expected": real.expected if real else 0,
        "hard_fail": any(score.hard_fail for score in scores),
    }
