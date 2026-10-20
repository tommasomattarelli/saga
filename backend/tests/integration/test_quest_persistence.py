"""ADR 0019 A7 — #86 quest persistence through the real turn path.

The provider is scripted; the graph, tools, PostgreSQL persistence, prompt,
saves and export are the production ones.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, update

from app.ai.providers.schemas import AgentResponse, ToolCall
from app.ai.router import get_user_generation
from app.models.campaign import Campaign
from app.models.save import Save
from app.security.auth import decode_token

pytestmark = pytest.mark.asyncio


async def _owner(auth_client) -> uuid.UUID:
    token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    return uuid.UUID(str(decode_token(token)["sub"]))


async def _openai_provider(auth_client, generation_clients):
    key = "quest-key"
    assert (
        await auth_client.put("/api/settings/api-keys", json={"openai": key})
    ).status_code == 200
    settings = await auth_client.patch(
        "/api/settings",
        json={"generation_provider": "openai", "generation_model": "quest-model"},
    )
    assert settings.status_code == 200
    await get_user_generation(await _owner(auth_client))
    return generation_clients[key][0]


def _script(provider, responses: list[AgentResponse]) -> list[dict]:
    calls: list[dict] = []

    async def generate(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    provider.generate_with_tools.side_effect = generate
    return calls


def _reply(text: str, *calls: ToolCall) -> AgentResponse:
    return AgentResponse(text=text, tool_calls=list(calls))


def _quest(call_id: str, **arguments) -> ToolCall:
    return ToolCall(id=call_id, name="update_quest", arguments=arguments)


async def _create_campaign(auth_client, name: str = "Quest Campaign") -> dict:
    response = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": name,
            "difficulty": "medium",
            "character_data": {
                "name": "Eron",
                "hp": {"current": 20, "max": 20},
                "abilities": {"strength": 10, "dexterity": 10},
            },
        },
    )
    assert response.status_code == 201
    return response.json()


async def _take_turn(auth_client, campaign_id: str, action: str = "I look around") -> dict:
    with (
        patch("app.api.turns.extract_and_store_facts", new=AsyncMock()),
        patch("app.api.turns._background_compression", new=AsyncMock()),
        patch("app.api.turns._background_global_summary", new=AsyncMock()),
    ):
        response = await auth_client.post(
            f"/api/campaigns/{campaign_id}/action", json={"action": action}
        )
    assert response.status_code == 200, response.text
    return response.json()


async def _stored_quests(db_session, campaign_id: str) -> dict:
    await db_session.commit()
    db_session.expire_all()
    campaign = await db_session.scalar(
        select(Campaign).where(Campaign.id == uuid.UUID(campaign_id))
    )
    assert campaign is not None
    return campaign.quests


async def _autosave(db_session, campaign_id: str) -> tuple[uuid.UUID, dict]:
    await db_session.commit()
    db_session.expire_all()
    result = await db_session.execute(
        select(Save.id, Save.campaign_snapshot).where(
            Save.campaign_id == uuid.UUID(campaign_id), Save.is_auto.is_(True)
        )
    )
    save_id, snapshot = result.one()
    return save_id, snapshot


async def test_authored_quests_keep_ids_names_descriptions_and_objectives(auth_client):
    created = await _create_campaign(auth_client)
    quests = created["quests"]

    assert set(quests) == {"active", "completed", "failed", "abandoned"}
    assert quests["completed"] == quests["failed"] == quests["abandoned"] == []
    assert quests["active"] == [
        {
            "id": "who_am_i",
            "name": "Who Am I?",
            "description": "Discover your identity and why you woke at the Shrine of First Light.",
            "objectives": [
                "Ask the villagers of Thornhaven about strangers",
                "Examine the shrine's carved symbols",
            ],
        }
    ]


async def test_a_real_turn_persists_one_record_per_id_and_drives_the_next_prompt(
    auth_client, db_session, generation_clients
):
    created = await _create_campaign(auth_client)
    campaign_id = created["id"]
    provider = await _openai_provider(auth_client, generation_clients)
    captured = _script(
        provider,
        [
            _reply(
                "",
                _quest(
                    "q1",
                    quest_id="who_am_i",
                    status="active",
                    description="Find out who you were.",
                ),
                _quest("q2", quest_id="who_am_i", status="completed"),
                _quest("q3", quest_id="who_am_i", status="active"),
                _quest(
                    "q4",
                    quest_id="dragon_hunt",
                    status="active",
                    name="Who Am I?",
                    description="Slay the dragon.",
                ),
                _quest("q5", quest_id="dragon_hunt", status="failed"),
                _quest("q6", quest_id="dragon_hunt", status="active"),
                _quest("q7", quest_id="dragon_hunt", status="active"),
                _quest("q8", quest_id="mystery_quest", status="completed", name="Mystery Quest"),
                _quest("q9", quest_id="who_am_i", status="abandoned"),
            ),
            _reply("You have a lead."),
            _reply("Morning comes."),
        ],
    )

    first = await _take_turn(auth_client, campaign_id, "I ask about the dragon")

    active = first["quests"]["active"]
    abandoned = first["quests"]["abandoned"]
    assert [q["id"] for q in active] == ["dragon_hunt"]
    assert [q["id"] for q in abandoned] == ["who_am_i"]
    assert first["quests"]["completed"] == first["quests"]["failed"] == []
    assert active[0] == {
        "id": "dragon_hunt",
        "name": "Who Am I?",
        "description": "Slay the dragon.",
        "objectives": [],
    }
    assert abandoned[0]["description"] == "Find out who you were."
    assert abandoned[0]["objectives"] == [
        "Ask the villagers of Thornhaven about strangers",
        "Examine the shrine's carved symbols",
    ]
    assert await _stored_quests(db_session, campaign_id) == first["quests"]

    await _take_turn(auth_client, campaign_id, "I wait for dawn")

    prompt = captured[2]["system_prompt"]
    assert '<quest id="dragon_hunt">Slay the dragon.</quest>' in prompt
    assert "who_am_i" not in prompt
    assert "Who Am I?" not in prompt
    assert "Ask the villagers" not in prompt
    assert "mystery_quest" not in prompt


async def test_manual_save_restore_replaces_the_registry_and_the_next_prompt(
    auth_client, db_session, generation_clients
):
    created = await _create_campaign(auth_client, "Manual Save Quest")
    campaign_id = created["id"]
    saved = await auth_client.post(f"/api/saves/{campaign_id}", json={"name": "Before"})
    assert saved.status_code == 201

    provider = await _openai_provider(auth_client, generation_clients)
    captured = _script(
        provider,
        [
            _reply(
                "The old life closes.",
                _quest("q1", quest_id="who_am_i", status="completed"),
                _quest(
                    "q2",
                    quest_id="later_quest",
                    status="active",
                    name="Later Quest",
                    description="This appeared after the save.",
                ),
            ),
            _reply("The trail is cold."),
        ],
    )
    await _take_turn(auth_client, campaign_id)

    restored = await auth_client.post(f"/api/saves/{campaign_id}/load/{saved.json()['id']}")
    assert restored.status_code == 200
    stored = await _stored_quests(db_session, campaign_id)
    assert [q["id"] for q in stored["active"]] == ["who_am_i"]
    assert "later_quest" not in str(stored)

    await _take_turn(auth_client, campaign_id, "I retrace my steps")

    prompt = captured[1]["system_prompt"]
    assert '<quest id="who_am_i">' in prompt
    assert "later_quest" not in prompt


async def test_autosave_restore_removes_later_registry_changes(
    auth_client, db_session, generation_clients
):
    created = await _create_campaign(auth_client, "Autosave Quest")
    campaign_id = created["id"]
    provider = await _openai_provider(auth_client, generation_clients)
    captured = _script(
        provider,
        [
            _reply(
                "A new lead.",
                _quest(
                    "q1",
                    quest_id="later_quest",
                    status="active",
                    name="Later Quest",
                    description="First version.",
                ),
            ),
            _reply("You remember the first account."),
        ],
    )

    await _take_turn(auth_client, campaign_id)
    autosave_id, snapshot = await _autosave(db_session, campaign_id)
    first_later = next(q for q in snapshot["quests"]["active"] if q["id"] == "later_quest")
    assert first_later["description"] == "First version."

    changed = await _stored_quests(db_session, campaign_id)
    for quest in changed["active"]:
        if quest["id"] == "later_quest":
            quest["description"] = "Second version."
    await db_session.execute(
        update(Campaign).where(Campaign.id == uuid.UUID(campaign_id)).values(quests=changed)
    )
    await db_session.commit()

    restored = await auth_client.post(f"/api/saves/{campaign_id}/load/{autosave_id}")
    assert restored.status_code == 200
    stored = await _stored_quests(db_session, campaign_id)
    restored_later = next(q for q in stored["active"] if q["id"] == "later_quest")
    assert restored_later["description"] == "First version."

    await _take_turn(auth_client, campaign_id)

    prompt = captured[1]["system_prompt"]
    assert "First version." in prompt
    assert "Second version." not in prompt


async def test_export_matches_the_stored_registry(auth_client, db_session, generation_clients):
    created = await _create_campaign(auth_client, "Export Quest")
    campaign_id = created["id"]
    provider = await _openai_provider(auth_client, generation_clients)
    _script(
        provider,
        [
            _reply(
                "The hunt begins.",
                _quest(
                    "q1",
                    quest_id="dragon_hunt",
                    status="active",
                    name="Dragon Hunt",
                    description="Slay the dragon.",
                ),
            ),
            _reply("The mountain waits."),
        ],
    )
    await _take_turn(auth_client, campaign_id)

    export = await auth_client.get(f"/api/export/{campaign_id}")
    assert export.status_code == 200
    stored = await _stored_quests(db_session, campaign_id)
    exported = export.json()["campaign"]["quests"]
    assert exported == stored
    assert [q["id"] for q in exported["active"]] == ["who_am_i", "dragon_hunt"]


async def test_active_quests_character_writes_are_rejected_with_422(auth_client, db_session):
    rejected_create = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Retired Container",
            "difficulty": "medium",
            "character_data": {"name": "Eron", "active_quests": []},
        },
    )
    assert rejected_create.status_code == 422

    created = await _create_campaign(auth_client, "Character Write Quest")
    campaign_id = created["id"]
    rejected_patch = await auth_client.patch(
        f"/api/characters/{campaign_id}", json={"active_quests": [{"name": "Old"}]}
    )
    assert rejected_patch.status_code == 422

    merged = await auth_client.patch(f"/api/characters/{campaign_id}", json={"name": "Eron II"})
    assert merged.status_code == 200
    await db_session.commit()
    campaign = await db_session.scalar(
        select(Campaign).where(Campaign.id == uuid.UUID(campaign_id))
    )
    assert campaign is not None
    assert "active_quests" not in campaign.character_data
    assert campaign.character_data["name"] == "Eron II"
