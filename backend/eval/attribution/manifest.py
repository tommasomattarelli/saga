from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.memory.batch_source_contracts import BatchInput
from app.memory.producer_prompts import prepare_request
from app.memory.production_policy import configured_memory_policy
from eval.integrated_memory.evidence_io import write_json
from eval.support.digest import digest

SCENARIOS = Path(__file__).parent / "scenarios"
LIVE_MODEL = "nvidia/nemotron-3.5-super-vl:free"
DECLARATIVE = ("statement", "belief", "intention")


class Speaker(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str
    type: Literal["player", "npc"]


class ExpectedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    speaker: Speaker | None
    kind: Literal["statement", "belief", "intention", "occurrence"]
    key_phrases: tuple[str, ...] = Field(min_length=1)


class Forbidden(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    claim: int | None = None
    speaker: Speaker | None = None
    kinds: tuple[str, ...] = ()


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str
    source: BatchInput
    expected: tuple[ExpectedClaim, ...]
    forbidden: tuple[Forbidden, ...] = ()


class AttributionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run_id: str = Field(min_length=1)
    language: str = "en"
    model: str
    request_cap: int
    scenarios: tuple[Scenario, ...] = Field(min_length=1)
    source_hashes: dict[str, str]
    prompt_hashes: dict[str, str]
    seal: str
    approved: Literal[False] = False
    failure_policy: Literal["stop_on_first_error"] = "stop_on_first_error"

    @property
    def missing_gates(self) -> list[str]:
        missing = []
        if not self.model.endswith(":free"):
            missing.append("free_model")
        if self.request_cap < len(self.scenarios):
            missing.append("request_cap below scenario count")
        return missing


def load_scenarios() -> tuple[Scenario, ...]:
    raw = json.loads((SCENARIOS / "scenarios.json").read_text(encoding="utf-8"))
    scenarios = []
    for item in raw:
        item = dict(item)
        source_file = item.pop("source_file", None)
        if source_file is not None:
            item["source"] = json.loads((SCENARIOS / source_file).read_text(encoding="utf-8"))
        scenarios.append(Scenario.model_validate_json(json.dumps(item)))
    names = [scenario.name for scenario in scenarios]
    if len(set(names)) != len(names):
        raise ValueError("Scenario names must be unique.")
    for scenario in scenarios:
        for forbidden in scenario.forbidden:
            if forbidden.claim is not None and forbidden.claim >= len(scenario.expected):
                raise ValueError(f"Unknown expected claim in {scenario.name}.")
    return tuple(scenarios)


def _hashes(
    scenarios: tuple[Scenario, ...], language: str
) -> tuple[dict[str, str], dict[str, str]]:
    policy = configured_memory_policy().facts
    sources, prompts = {}, {}
    for scenario in scenarios:
        sources[scenario.name] = scenario.source.source_hash()
        prompts[scenario.name] = prepare_request(
            "batch", scenario.source, language=language, facts_policy=policy
        ).instruction_hash
    return sources, prompts


def _sealed(payload: dict[str, object]) -> str:
    return digest(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _seal_payload(manifest: AttributionManifest) -> dict[str, object]:
    return {
        "run_id": manifest.run_id,
        "language": manifest.language,
        "model": manifest.model,
        "request_cap": manifest.request_cap,
        "scenarios": [scenario.model_dump(mode="json") for scenario in manifest.scenarios],
        "source_hashes": manifest.source_hashes,
        "prompt_hashes": manifest.prompt_hashes,
    }


def prepare_manifest(
    *, run_id: str, model: str = LIVE_MODEL, request_cap: int | None = None, language: str = "en"
) -> AttributionManifest:
    if not run_id.strip() or not language.strip() or not model.strip():
        raise ValueError("run_id, language and model must be nonempty")
    scenarios = load_scenarios()
    cap = len(scenarios) if request_cap is None else request_cap
    if cap < len(scenarios):
        raise ValueError("request_cap must cover every scenario")
    sources, prompts = _hashes(scenarios, language)
    payload: dict[str, object] = {
        "run_id": run_id,
        "language": language,
        "model": model,
        "request_cap": cap,
        "scenarios": [scenario.model_dump(mode="json") for scenario in scenarios],
        "source_hashes": sources,
        "prompt_hashes": prompts,
    }
    return AttributionManifest.model_validate_json(
        json.dumps({**payload, "seal": _sealed(payload)})
    )


def validate_manifest(manifest: AttributionManifest) -> None:
    expected_seal = _sealed(_seal_payload(manifest))
    if expected_seal != manifest.seal:
        raise ValueError("Manifest seal does not match its contents.")
    sources, prompts = _hashes(manifest.scenarios, manifest.language)
    if sources != manifest.source_hashes or prompts != manifest.prompt_hashes:
        raise ValueError("Manifest no longer matches the current sources or prompts.")
    if manifest.missing_gates:
        raise ValueError(
            "Manifest has unresolved live gates: " + ", ".join(manifest.missing_gates)
        )


def load_manifest(directory: Path) -> AttributionManifest:
    manifest = AttributionManifest.model_validate_json(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    validate_manifest(manifest)
    return manifest


def write_manifest(manifest: AttributionManifest, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "manifest.json", manifest.model_dump(mode="json"))
