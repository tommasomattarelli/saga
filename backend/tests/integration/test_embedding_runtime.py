"""PostgreSQL integration for embedding resolution, isolation and legacy spaces.

Runs against the agent's exclusive database (TEST_DATABASE_URL). No provider
network call ever happens: only the SDK transport boundary is faked, and the
fake asserts rule 15 (no DB connection held across the network step).
"""

from __future__ import annotations

import uuid

import httpx
import openai
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.credentials import resolve_embedding
from app.ai.embedding_config import legacy_space
from app.ai.embeddings import embed_batch, reset_adapter_cache
from app.ai.router import get_user_embedding
from app.config import settings
from app.exceptions import AIProviderError, ValidationError
from app.models.user import User
from app.security.encryption import encrypt_api_key


@pytest.fixture(autouse=True)
def clean_clients():
    reset_adapter_cache()
    yield
    reset_adapter_cache()


async def make_user(
    db_session: AsyncSession,
    *,
    openrouter_key: str | None = None,
    openai_key: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    consents: dict | None = None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="hash",
        embedding_provider=provider,
        embedding_model=model,
        server_key_consents=consents,
    )
    if openrouter_key:
        user.openrouter_api_key_enc = encrypt_api_key(openrouter_key)
    if openai_key:
        user.openai_api_key_enc = encrypt_api_key(openai_key)
    db_session.add(user)
    await db_session.commit()
    return user


def openai_response(dimension: int = 2, count: int = 1):
    from types import SimpleNamespace

    return SimpleNamespace(
        data=[SimpleNamespace(index=index, embedding=[0.1] * dimension) for index in range(count)],
        model_extra=None,
    )


async def test_two_users_share_the_space_but_never_the_credential(db_session: AsyncSession):
    one = await make_user(
        db_session, openrouter_key="key-one", provider="openrouter", model="openai/mistral-embed"
    )
    two = await make_user(
        db_session, openrouter_key="key-two", provider="openrouter", model="openai/mistral-embed"
    )
    resolved_one = await get_user_embedding(one.id)
    resolved_two = await get_user_embedding(two.id)

    assert resolved_one.space == resolved_two.space
    assert resolved_one.credential.key == "key-one"
    assert resolved_two.credential.key == "key-two"
    assert resolved_one.credential.key != resolved_two.credential.key

    from app.ai.embeddings import get_embedding_adapter

    adapter_one = get_embedding_adapter(resolved_one)
    adapter_two = get_embedding_adapter(resolved_two)
    assert adapter_one is not adapter_two


async def test_key_rotation_changes_only_the_credential(db_session: AsyncSession):
    user = await make_user(
        db_session, openrouter_key="before", provider="openrouter", model="openai/mistral-embed"
    )
    before = await get_user_embedding(user.id)
    user.openrouter_api_key_enc = encrypt_api_key("after")
    await db_session.commit()
    after = await get_user_embedding(user.id)

    assert before.space == after.space
    assert before.credential.key == "before"
    assert after.credential.key == "after"
    assert before.credential.source == after.credential.source == "personal"


async def test_manifest_legacy_space_never_borrows_the_personal_profile(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    user = await make_user(
        db_session,
        openrouter_key="personal-or-key",
        provider="openrouter",
        model="openai/mistral-embed",
        consents={"openai": True},
    )
    with pytest.raises(ValidationError):
        await get_user_embedding(user.id, space=legacy_space())

    monkeypatch.setattr(settings, "openai_api_key", "server-openai-key")
    monkeypatch.setattr("app.ai.credentials.get_server_key_fallback", lambda: {"openai": True})
    resolved = await get_user_embedding(user.id, space=legacy_space())
    assert resolved.space.provider == "openai"
    assert resolved.space.pipeline_version == "embed-v1-legacy"
    assert resolved.space.requested_dimensions == 384
    assert resolved.credential.key == "server-openai-key"
    assert resolved.credential.source == "server"
    assert resolved.credential.key != "personal-or-key"


async def test_fallback_only_when_the_personal_key_is_absent(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "openrouter_api_key", "server-or-key")
    monkeypatch.setattr("app.ai.credentials.get_server_key_fallback", lambda: {"openrouter": True})
    without = await make_user(
        db_session,
        provider="openrouter",
        model="openai/mistral-embed",
        consents={"openrouter": True},
    )
    resolved = await get_user_embedding(without.id)
    assert resolved.credential.source == "server"
    assert resolved.credential.key == "server-or-key"

    with_key = await make_user(
        db_session,
        openrouter_key="personal-or-key",
        provider="openrouter",
        model="openai/mistral-embed",
        consents={"openrouter": True},
    )
    resolved_with = await get_user_embedding(with_key.id)
    assert resolved_with.credential.source == "personal"
    assert resolved_with.credential.key == "personal-or-key"


async def test_fallback_requires_both_operator_and_user_consent(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "openrouter_api_key", "server-or-key")
    monkeypatch.setattr(
        "app.ai.credentials.get_server_key_fallback", lambda: {"openrouter": False}
    )
    no_consent = await make_user(db_session, provider="openrouter", model="openai/mistral-embed")
    with pytest.raises(ValidationError):
        await get_user_embedding(no_consent.id)

    consented = await make_user(
        db_session,
        provider="openrouter",
        model="openai/mistral-embed",
        consents={"openrouter": True},
    )
    with pytest.raises(ValidationError):
        await get_user_embedding(consented.id)


async def test_no_db_connection_spans_the_embedding_call(
    db_session: AsyncSession, assert_no_db_held, monkeypatch: pytest.MonkeyPatch
):
    from unittest.mock import patch

    user = await make_user(
        db_session,
        openai_key="openai-key",
        provider="openai",
        model="text-embedding-3-large",
    )
    resolved = await get_user_embedding(user.id)
    calls: list[dict] = []

    async def create(*args, **kwargs):
        assert_no_db_held()
        calls.append(kwargs)
        return openai_response(dimension=3, count=1)

    with patch("openai.resources.embeddings.AsyncEmbeddings.create", side_effect=create):
        batch = await embed_batch(["a turn summary"], resolved)
    assert batch.dimension == 3
    assert calls[0]["input"] == ["a turn summary"]
    assert calls[0]["model"] == "text-embedding-3-large"
    assert "dimensions" not in calls[0]


async def test_auth_error_is_one_attempt_and_never_the_server_key(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    from unittest.mock import AsyncMock, patch

    monkeypatch.setattr(settings, "openrouter_api_key", "server-or-key")
    monkeypatch.setattr("app.ai.credentials.get_server_key_fallback", lambda: {"openrouter": True})
    user = await make_user(
        db_session,
        openrouter_key="personal-or-key",
        provider="openrouter",
        model="openai/mistral-embed",
        consents={"openrouter": True},
    )
    resolved = await get_user_embedding(user.id)
    attempts: list[str] = []

    async def reject(*args, **kwargs):
        attempts.append("call")
        raise openai.APIStatusError(
            "private-payload",
            response=httpx.Response(
                401, request=httpx.Request("POST", "https://provider.test/private")
            ),
            body=None,
        )

    with (
        patch("openai.resources.embeddings.AsyncEmbeddings.create", side_effect=reject),
        patch("app.ai.embedding_validation.asyncio.sleep", new=AsyncMock()),
        pytest.raises(AIProviderError) as error,
    ):
        await embed_batch(["x"], resolved)

    assert attempts == ["call"]
    assert "private-payload" not in str(error.value)
    from app.ai import embeddings as runtime

    cached_keys = {key for key in runtime._openai_adapters}
    assert ("openrouter", "https://openrouter.ai/api/v1", "server-or-key") not in cached_keys


async def test_legacy_query_with_384_at_the_transport_boundary(db_session: AsyncSession):
    from unittest.mock import patch

    user = await make_user(db_session, openai_key="openai-legacy-key")
    resolved = resolve_embedding(user, legacy_space())
    captured: dict = {}

    async def create(*args, **kwargs):
        captured.update(kwargs)
        return openai_response(dimension=384, count=1)

    with patch("openai.resources.embeddings.AsyncEmbeddings.create", side_effect=create):
        batch = await embed_batch(["old summary"], resolved)

    assert captured["dimensions"] == 384
    assert captured["model"] == "text-embedding-3-small"
    assert captured["input"] == ["old summary"]
    assert batch.space.pipeline_version == "embed-v1-legacy"
    assert batch.dimension == 384
