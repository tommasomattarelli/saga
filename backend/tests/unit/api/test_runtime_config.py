from types import SimpleNamespace

import pytest

from app.api.runtime_config import get_runtime_config


@pytest.mark.asyncio
async def test_runtime_config_returns_authenticated_client_timeout(monkeypatch):
    monkeypatch.setattr(
        "app.api.runtime_config.get_action_policy",
        lambda: SimpleNamespace(client_timeout_seconds=650.5),
    )

    result = await get_runtime_config(user=object())

    assert result.model_dump() == {"action_client_timeout_seconds": 650.5}
