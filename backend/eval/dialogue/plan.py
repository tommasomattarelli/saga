"""Identity and offline planning for the final ADR 0017 dialogue suite."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from app.ai.router import get_gameplay_config, get_instance_default
from eval.dialogue.cases import CASES, scenario_for
from eval.dialogue.limits import FREE_REQUESTS_PER_MINUTE

ROOT = Path(__file__).resolve().parents[3]
MODELS = (
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-super-vl:free",
)
CORE_CASES = frozenset(
    {"npc_speaks", "npc_followup", "actor_en", "actor_it", "actor_silent", "two_npc_two_beat"}
)


def json_default(value: object) -> object:
    if isinstance(value, frozenset | set):
        return sorted(value)
    raise TypeError("Evaluation evidence contains a non-JSON value.")


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=json_default).encode()
    ).hexdigest()


def source_hash() -> str:
    names = (
        subprocess.check_output(
            [
                "git",
                "ls-files",
                "-z",
                "backend/app",
                "backend/eval",
                "frontend/src",
                "saga.config.yaml",
            ],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    checksum = hashlib.sha256()
    for name in sorted(filter(None, names)):
        path = ROOT / name
        checksum.update(name.encode() + b"\0")
        checksum.update(path.read_bytes() if path.exists() else b"<deleted>")
    return checksum.hexdigest()


def manifest(
    models: list[str] | None = None,
    case_names: list[str] | None = None,
    runs: int = 3,
    suite: str = "adr-0017-final-v2",
    paid_allowlist: set[str] | None = None,
    session_affinity: bool = True,
) -> dict:
    selected_models = list(MODELS if models is None else models)
    selected_names = [case.name for case in CASES] if case_names is None else case_names
    by_name = {case.name: case for case in CASES}
    unknown = set(selected_names) - by_name.keys()
    if unknown:
        raise ValueError(f"unknown dialogue case: {sorted(unknown)[0]}")
    if not selected_models or not selected_names or runs < 1:
        raise ValueError("Select at least one model, case, and run.")
    if not suite.strip() or any(not model.strip() for model in selected_models):
        raise ValueError("Suite and model identifiers must not be empty.")
    if len(set(selected_models)) != len(selected_models) or len(set(selected_names)) != len(
        selected_names
    ):
        raise ValueError("Duplicate model or case selections make trial identity ambiguous.")
    allowed_paid = paid_allowlist or set()
    unapproved = {model for model in selected_models if not model.endswith(":free")} - allowed_paid
    if unapproved:
        raise ValueError(f"Paid model requires explicit allowlist: {sorted(unapproved)[0]}")
    selected_cases = [by_name[name] for name in selected_names]
    scenarios = {case.name: scenario_for(case.name) for case in selected_cases}
    return {
        "suite": suite,
        "source_hash": source_hash(),
        "identity_contract": "Tracked source/config and scenario identity; request hashes bind provider-call inputs and explicit sanitized routing headers when enabled.",
        "models": selected_models,
        "execution": {
            "workers": "one-per-selected-model",
            "free_requests_per_minute": FREE_REQUESTS_PER_MINUTE,
            "free_model_suffix": ":free",
            "session_affinity": "per-model" if session_affinity else "implicit",
        },
        "paid_allowlist": sorted(allowed_paid),
        "runs_per_model_case": runs,
        "trials": len(selected_cases) * len(selected_models) * runs,
        "nominal_requests": sum(
            case.ceiling if case.nominal is None else case.nominal for case in selected_cases
        )
        * len(selected_models)
        * runs,
        "request_ceiling": sum(case.ceiling for case in selected_cases)
        * len(selected_models)
        * runs,
        "pipeline_dm_cap": 3,
        "max_output_tokens": get_instance_default().max_tokens,
        "gameplay": asdict(get_gameplay_config()),
        "cases": {
            name: {
                "ceiling": by_name[name].ceiling,
                "comparison": "core" if name in CORE_CASES else "new-review-case",
                "expected_relevance_review": by_name[name].expected_relevance,
                "expected_initial_npcs": sorted(by_name[name].expected_initial_npcs),
                "expect_second_beat": by_name[name].expected_second_npc is not None,
                "turns": 1 + len(by_name[name].followup_actions),
                "scenario_hash": digest(
                    {
                        "case": name,
                        "campaign": vars(sc.campaign),
                        "history": sc.history,
                        "summary": sc.summary_context,
                        "global": sc.global_summary,
                        "recall": sc.recall,
                        "stimuli": {key: asdict(value) for key, value in sc.stimuli.items()},
                        "evaluation_contract": {
                            "expected_relevance": by_name[name].expected_relevance,
                            "expected_initial_npcs": sorted(by_name[name].expected_initial_npcs),
                            "expect_second_beat": by_name[name].expected_second_npc is not None,
                            "expected_second_npc": by_name[name].expected_second_npc,
                            "actor_scene_context": name == "actor_scene",
                            "followup_actions": by_name[name].followup_actions,
                        },
                    }
                ),
            }
            for name, sc in scenarios.items()
        },
    }


def trial_key(plan: dict, case: str, model: str, run: int) -> str:
    return digest([plan, case, model, run])
