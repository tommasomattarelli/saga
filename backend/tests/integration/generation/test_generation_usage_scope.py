from app.ai.providers.usage import current_correlation
from tests.integration.gameplay.test_npc_beats import actor, call, speaking
from tests.integration.gameplay.test_quest_persistence import (
    _create_campaign,
    _openai_provider,
    _reply,
    _take_turn,
)


async def test_runtime_correlates_actual_dm_steps_and_parallel_actor_identities(
    auth_client,
    generation_clients,
):
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    dm_scopes = []
    actor_scopes = []
    replies = [
        _reply(
            "",
            call(
                "move-npc",
                "update_npc",
                name="Aldric",
                updates={"location": "Shrine of First Light"},
            ),
            actor("Lyra"),
            actor("Aldric"),
        ),
        _reply("[[npc:Lyra:1]] [[npc:Aldric:1]]"),
    ]

    async def generate_dm(**kwargs):
        dm_scopes.append(current_correlation())
        return replies.pop(0)

    async def generate_actor(**kwargs):
        actor_scopes.append(current_correlation())
        return speaking("Hello.")

    provider.generate_with_tools.side_effect = generate_dm
    provider.generate.side_effect = generate_actor
    await _take_turn(auth_client, created["id"])
    assert [(scope.role, scope.step) for scope in dm_scopes] == [("dm", 0), ("dm", 1)]
    assert {scope.npc_name for scope in actor_scopes} == {"Lyra", "Aldric"}
    assert {scope.npc_id for scope in actor_scopes} == {
        npc_id
        for npc_id, npc in created["world_state"]["npcs"].items()
        if npc["name"] in {"Lyra", "Aldric"}
    }
    assert all((scope.role, scope.step, scope.beat) == ("actor", 0, 0) for scope in actor_scopes)
    assert current_correlation().role is None
