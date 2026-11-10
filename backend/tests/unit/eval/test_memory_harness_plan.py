import json

import pytest
from eval.memory.plan import MemoryPlan, load_plan, prepare_plan, write_plan


def fixture_source() -> dict[str, object]:
    return {
        "turns": [
            {
                "reference": "t1",
                "turn_id": "00000000-0000-0000-0000-000000000001",
                "player_action": "Ask",
                "narration": "A door opens.",
                "operations": None,
            },
            {
                "reference": "t2",
                "turn_id": "00000000-0000-0000-0000-000000000002",
                "player_action": "Wait",
                "narration": "The party rests.",
                "operations": None,
            },
        ]
    }


def policy() -> dict[str, object]:
    return {
        "max_per_batch": 2,
        "importance_levels": [{"name": "high", "criteria": "Major", "examples": "A secret"}],
    }


def test_prepare_plan_freezes_sources_and_calculates_budget(tmp_path) -> None:
    plan = prepare_plan(
        sources=[fixture_source(), fixture_source()],
        facts_policy=policy(),
        global_policy={"target_words": 120},
        language="en",
        models=["provider/model"],
        repetitions=2,
        global_count=1,
    )
    assert plan.call_budget == 2 * (3 * 2 + 1)
    assert plan.producer_version == "memory-v1"
    assert len(plan.implementation_fingerprint) == 64
    assert plan.output_cap > 0
    write_plan(plan, tmp_path)
    assert MemoryPlan.model_validate_json((tmp_path / "manifest.json").read_text()) == plan


def test_manifest_rejects_source_or_setting_edits(tmp_path) -> None:
    original = prepare_plan(
        sources=[fixture_source()],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
    )
    write_plan(original, tmp_path)
    changed = fixture_source()
    changed["turns"][0]["narration"] = "A different door opens."
    edited = prepare_plan(
        sources=[changed],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
    )
    with pytest.raises(ValueError, match="manifest"):
        write_plan(edited, tmp_path)


def test_global_count_cannot_exceed_available_batches() -> None:
    with pytest.raises(ValueError, match="global_count"):
        prepare_plan(
            sources=[fixture_source()],
            facts_policy=policy(),
            global_policy={"target_words": 120},
            language="en",
            models=["provider/model"],
            repetitions=1,
            global_count=2,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("models", ["provider/edited"]),
        ("repetitions", 2),
        ("global_count", 1),
        ("language", "it"),
        (
            "facts_policy",
            {
                "max_per_batch": 1,
                "importance_levels": [
                    {"name": "high", "criteria": "Major", "examples": "A secret"}
                ],
            },
        ),
    ],
)
def test_manifest_seal_rejects_non_source_edits(tmp_path, field, replacement) -> None:
    plan = prepare_plan(
        sources=[fixture_source()],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
    )
    write_plan(plan, tmp_path)
    path = tmp_path / "manifest.json"
    changed = json.loads(path.read_text())
    changed[field] = replacement
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="seal"):
        load_plan(tmp_path)


def test_manifest_rejects_changed_instruction_fingerprint(tmp_path, monkeypatch) -> None:
    import eval.memory.plan as plan_module

    plan = prepare_plan(
        sources=[fixture_source()],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
    )
    write_plan(plan, tmp_path)
    monkeypatch.setattr(plan_module, "current_implementation_fingerprint", lambda: "changed")
    with pytest.raises(ValueError, match="instructions changed"):
        load_plan(tmp_path)


def test_fingerprint_includes_the_complete_memory_harness(monkeypatch) -> None:
    from pathlib import Path

    from eval.memory.plan import current_implementation_fingerprint

    original = current_implementation_fingerprint()
    read_bytes = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: read_bytes(path) + b"\n" if path.name == "report.py" else read_bytes(path),
    )
    assert current_implementation_fingerprint() != original
