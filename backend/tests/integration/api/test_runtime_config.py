import pytest


@pytest.mark.asyncio
async def test_runtime_config_requires_auth_and_returns_fractional_client_timeout(
    auth_client, client, monkeypatch
):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.api.runtime_config.get_action_policy",
        lambda: SimpleNamespace(client_timeout_seconds=650.5),
    )

    authorization = client.headers.pop("Authorization")
    assert (await client.get("/api/runtime-config")).status_code == 401
    client.headers["Authorization"] = authorization
    response = await auth_client.get("/api/runtime-config")

    assert response.status_code == 200
    assert response.json() == {"action_client_timeout_seconds": 650.5}
