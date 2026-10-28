import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.schemas import ToolCall
from app.models.campaign import Campaign
from app.models.memory_fact import MemoryFact
from app.models.save import Save
from app.models.turn import Turn
from app.models.user import User
from app.security.auth import create_access_token
from tests.integration.test_quest_persistence import (
    _autosave,
    _openai_provider,
    _reply,
    _script,
    _take_turn,
)


async def _create(client: AsyncClient, **fields: object) -> dict:
    response = await client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": "Language", "difficulty": "medium", **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_missing_language_persists_english(auth_client: AsyncClient) -> None:
    campaign = await _create(auth_client)
    assert campaign["language"] == "en"
    assert (await auth_client.get(f"/api/campaigns/{campaign['id']}")).json()["language"] == "en"


async def test_config_default_is_resolved_once_not_reapplied_on_read(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.core.campaign_language.load_saga_config",
        lambda: {"gameplay": {"default_campaign_language": "it"}},
    )
    campaign = await _create(auth_client)
    assert campaign["language"] == "it"
    monkeypatch.setattr(
        "app.core.campaign_language.load_saga_config",
        lambda: {"gameplay": {"default_campaign_language": "en"}},
    )
    assert (await auth_client.get(f"/api/campaigns/{campaign['id']}")).json()["language"] == "it"


@pytest.mark.parametrize("language", ["it", "en", "ja", "ar", "sw", "uk"])
async def test_supported_language_round_trips(auth_client: AsyncClient, language: str) -> None:
    campaign = await _create(auth_client, language=language)
    assert campaign["language"] == language
    response = await auth_client.get(f"/api/campaigns/{campaign['id']}")
    assert response.json()["language"] == language


@pytest.mark.parametrize("language", ["zz", "en-GB", "italiano", "IT", "", None])
async def test_unsupported_language_is_structured_validation_error(
    auth_client: AsyncClient, language: str | None
) -> None:
    response = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Invalid",
            "difficulty": "easy",
            "language": language,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "language"]


async def test_languages_is_authenticated_catalog_not_a_campaign_id(
    client: AsyncClient, auth_client: AsyncClient
) -> None:
    response = await auth_client.get("/api/campaigns/languages")
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 184
    assert {"code": "en", "display_name": "English", "is_default": True} in entries
    assert {"code": "it", "display_name": "Italian", "is_default": False} in entries
    assert len({entry["code"] for entry in entries}) == len(entries)
    client.headers.pop("Authorization")
    assert (await client.get("/api/campaigns/languages")).status_code == 401


async def test_language_update_does_not_rewrite_history_or_facts(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    campaign = await _create(auth_client, language="it")
    campaign_id = uuid.UUID(campaign["id"])
    turn = Turn(
        campaign_id=campaign_id,
        turn_number=1,
        player_action="ciao",
        narration="Il bosco.",
        model_used="test",
        summary="Un incontro.",
    )
    fact = MemoryFact(
        campaign_id=campaign_id,
        turn_number=1,
        entity_name="Bosco",
        entity_type="location",
        content="Il bosco è silenzioso.",
    )
    db_session.add_all([turn, fact])
    await db_session.commit()
    response = await auth_client.patch(f"/api/campaigns/{campaign_id}", json={"language": "en"})
    assert response.status_code == 200
    assert response.json()["language"] == "en"
    await db_session.refresh(turn)
    await db_session.refresh(fact)
    assert (turn.narration, turn.summary, fact.content) == (
        "Il bosco.",
        "Un incontro.",
        "Il bosco è silenzioso.",
    )
    export = (await auth_client.get(f"/api/export/{campaign_id}")).json()
    assert export["campaign"]["language"] == "en"
    assert export["turns"][0]["narration"] == "Il bosco."


async def test_update_is_ownership_checked_and_not_an_arbitrary_patch(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    campaign = await _create(auth_client, language="it")
    url = f"/api/campaigns/{campaign['id']}"
    assert (await auth_client.patch(url, json={"language": "zz"})).status_code == 422
    assert (
        await auth_client.patch(url, json={"language": "en", "user_id": str(uuid.uuid4())})
    ).status_code == 422
    other = User(
        username="other-language", email="other-language@example.com", hashed_password="x"
    )
    db_session.add(other)
    await db_session.commit()
    auth_client.headers["Authorization"] = f"Bearer {create_access_token(other.id)}"
    assert (await auth_client.patch(url, json={"language": "en"})).status_code == 404
    stored = (
        await db_session.execute(select(Campaign).where(Campaign.id == uuid.UUID(campaign["id"])))
    ).scalar_one()
    assert stored.language == "it"


async def test_restore_keeps_current_language_even_if_snapshot_contains_old_preference(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    campaign = await _create(auth_client, language="it")
    campaign_id = campaign["id"]
    saved = await auth_client.post(f"/api/saves/{campaign_id}", json={"name": "Italian"})
    assert saved.status_code == 201
    save_id = saved.json()["id"]
    save = await db_session.get(Save, uuid.UUID(save_id))
    assert save is not None
    assert "language" not in save.campaign_snapshot
    # Old or imported snapshots cannot overwrite a current campaign preference.
    save.campaign_snapshot = {**save.campaign_snapshot, "language": "it"}
    await db_session.commit()
    assert (
        await auth_client.patch(f"/api/campaigns/{campaign_id}", json={"language": "en"})
    ).status_code == 200
    assert (await auth_client.post(f"/api/saves/{campaign_id}/load/{save_id}")).status_code == 200
    assert (await auth_client.get(f"/api/campaigns/{campaign_id}")).json()["language"] == "en"


async def test_language_reaches_real_dm_and_actor_and_survives_autosave_restore(
    auth_client: AsyncClient, db_session: AsyncSession, generation_clients: dict
) -> None:
    campaign = await _create(auth_client, language="it")
    campaign_id = campaign["id"]
    provider = await _openai_provider(auth_client, generation_clients)
    captured = _script(
        provider,
        [
            _reply(
                "",
                ToolCall(
                    id="actor",
                    name="invoke_npc",
                    arguments={"name": "Lyra", "context": "Player greets you in English."},
                ),
            ),
            _reply("Gli alberi fremono."),
            _reply("The trees stir."),
        ],
    )

    async def actor_reply(**kwargs: object) -> str:
        return '{"dialogue": "Salve.", "axis_changes": {}}'

    provider.generate.side_effect = actor_reply
    first = await _take_turn(auth_client, campaign_id, "Hello, Lyra!")
    assert "Italian (it)" in captured[0]["system_prompt"]
    actor = provider.generate.call_args.kwargs
    assert "Italian (it)" in actor["messages"][0]["content"]
    assert first["npc_dialogues"][0]["dialogue"] == "Salve."
    save_id, snapshot = await _autosave(db_session, campaign_id)
    assert "language" not in snapshot
    await auth_client.patch(f"/api/campaigns/{campaign_id}", json={"language": "en"})
    assert (await auth_client.post(f"/api/saves/{campaign_id}/load/{save_id}")).status_code == 200
    await _take_turn(auth_client, campaign_id, "Aspetto.")
    assert "English (en)" in captured[-1]["system_prompt"]
