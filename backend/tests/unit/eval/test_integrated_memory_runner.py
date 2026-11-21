from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_integrated_runner_rejects_live_without_authorization(tmp_path) -> None:
    from eval.integrated_memory.runner import run_plan as run_integrated

    with pytest.raises(ValueError, match="authorization"):
        await run_integrated(None, tmp_path, uuid4(), authorized=False)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_integrated_runner_rejects_missing_gates_before_creating_evidence(tmp_path) -> None:
    from eval.integrated_memory.plan import prepare_plan as prepare_integrated
    from eval.integrated_memory.runner import run_plan as run_integrated

    turns = [
        {
            "reference": f"t{index}",
            "turn_id": str(uuid4()),
            "player_action": "Wait",
            "narration": "A quiet moment.",
            "operations": [],
        }
        for index in range(1, 13)
    ]
    plan = prepare_integrated(sources={"turns": turns}, run_id="blocked")
    with pytest.raises(ValueError, match="gates are incomplete"):
        await run_integrated(plan, tmp_path, uuid4(), authorized=True)
    assert list(tmp_path.iterdir()) == []
