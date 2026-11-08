import pytest
from eval.dialogue.plan import manifest


@pytest.mark.parametrize(
    "kwargs",
    [
        {"models": ["m:free", "m:free"]},
        {"case_names": ["npc_speaks", "npc_speaks"]},
        {"suite": "  "},
        {"models": [" "]},
    ],
)
def test_manifest_rejects_ambiguous_or_empty_identity(kwargs):
    with pytest.raises(ValueError):
        manifest(**kwargs)


def test_selected_plan_identifies_core_and_new_review_cases_separately():
    plan = manifest(
        models=["nvidia/example:free"],
        case_names=["npc_speaks", "actor_scene", "two_npc_natural"],
        runs=1,
        suite="candidate-2026-10-29",
    )
    assert plan["suite"] == "candidate-2026-10-29"
    assert plan["cases"]["npc_speaks"]["comparison"] == "core"
    assert (
        plan["cases"]["npc_speaks"]["scenario_hash"]
        != plan["cases"]["actor_scene"]["scenario_hash"]
    )
    assert plan["cases"]["two_npc_natural"]["comparison"] == "new-review-case"
    assert plan["cases"]["two_npc_natural"]["expected_relevance_review"] is True
    assert plan["request_ceiling"] == 9
