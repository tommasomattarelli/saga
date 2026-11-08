import uuid
from copy import deepcopy

from app.ai.router import ModelConfig
from eval.dialogue.cases import case_for_scenario_name
from eval.dialogue.pipeline import run_pipeline
from eval.dialogue.requests import SuiteProvider
from eval.scenario_tools.scenario import Scenario


async def run_conversation(
    scenario: Scenario,
    trace: SuiteProvider,
    config: ModelConfig,
    user_id: uuid.UUID,
) -> tuple[dict, list[str]]:
    current = deepcopy(scenario)
    case = case_for_scenario_name(current.name)
    actions = (current.stimuli["npc_speaks"].player, *case.followup_actions)
    turns: list[dict] = []
    failures: list[str] = []
    for index, action in enumerate(actions):
        if trace.exhausted or trace.paused:
            break
        current.stimuli["npc_speaks"].player = action
        data, failed = await run_pipeline(current, trace, config, user_id)
        turns.append(data)
        failures.extend(f"turn-{index}:{item}" for item in failed)
        current.campaign.world_state = deepcopy(data["after"])
        current.campaign.character_data = deepcopy(data["character_after"])
        current.campaign.quests = deepcopy(data["quests_after"])
        current.history.extend(
            [
                {"role": "user", "content": action},
                {"role": "assistant", "content": data["narration"]},
            ]
        )
        if "foreground-run-incomplete" in failed:
            failures.append("foreground-run-incomplete")
            break
    return {
        "turns": turns,
        "expected_turns": len(actions),
        "semantic_review_required": True,
    }, sorted(set(failures))
