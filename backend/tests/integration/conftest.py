from collections.abc import Callable, Iterator
from contextvars import ContextVar
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event
from sqlalchemy.pool import ConnectionPoolEntry

from app import dependencies
from app.ai.providers import base
from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentResponse


@pytest.fixture
def assert_no_db_held() -> Iterator[Callable[[], None]]:
    active: ContextVar[frozenset[object]] = ContextVar(
        "active_test_connections", default=frozenset()
    )
    checked_out: set[object] = set()

    def checkout(connection: object, record: ConnectionPoolEntry, proxy: object) -> None:
        token = object()
        record.info["generation_test_token"] = token
        checked_out.add(token)
        active.set(active.get() | {token})

    def checkin(connection: object, record: ConnectionPoolEntry) -> None:
        checked_out.discard(record.info.pop("generation_test_token", None))

    def check() -> None:
        assert not active.get() & checked_out, "A database connection spans a provider call"

    event.listen(dependencies.engine.sync_engine, "checkout", checkout)
    event.listen(dependencies.engine.sync_engine, "checkin", checkin)
    try:
        yield check
    finally:
        event.remove(dependencies.engine.sync_engine, "checkout", checkout)
        event.remove(dependencies.engine.sync_engine, "checkin", checkin)


@pytest.fixture
def generation_clients(
    monkeypatch: pytest.MonkeyPatch, assert_no_db_held: Callable[[], None]
) -> Iterator[dict[str, list[AsyncMock]]]:
    clients: dict[str, list[AsyncMock]] = {}

    async def generate(*args: object, **kwargs: object) -> str:
        assert_no_db_held()
        return (
            '{"summary":"The inn is closed.","dialogue":"Welcome!",'
            '"facts":[{"entity_name":"Inn","content":"The inn is closed."}]}'
        )

    async def generate_with_tools(*args: object, **kwargs: object) -> AgentResponse:
        assert_no_db_held()
        return AgentResponse(text="A torch flickers in the quiet hall.")

    def create(*, api_key: str | None = None) -> AIProvider:
        assert api_key is not None
        provider = AsyncMock(spec=AIProvider)
        provider.generate.side_effect = generate
        provider.generate_with_tools.side_effect = generate_with_tools
        clients.setdefault(api_key, []).append(provider)
        return cast(AIProvider, provider)

    base._providers.clear()
    monkeypatch.setattr("app.ai.providers.openai.OpenAIProvider", create)
    try:
        yield clients
    finally:
        base._providers.clear()
