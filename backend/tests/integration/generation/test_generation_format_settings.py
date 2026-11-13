import pytest
from httpx import AsyncClient

from app.ai.providers.google import GoogleProvider


async def _google_sdk_destination(
    api_key: str,
) -> tuple[bool, str | None, str | None, str | None, str | None]:
    client = GoogleProvider(api_key=api_key).client
    try:
        api_client = client._api_client
        http_options = api_client._http_options
        return (
            client.vertexai,
            api_client.project,
            api_client.location,
            http_options.base_url,
            http_options.api_version,
        )
    finally:
        await client.aio.aclose()
        client.close()


async def test_format_settings_are_effective_without_credentials(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["generation_allow_json_mode_fallback"] is False
    assert payload["generation_allow_prompt_only_fallback"] is False
    assert payload["generation_format_fingerprint"]
    assert "localhost" not in payload["generation_format_fingerprint"]


async def test_google_fingerprint_tracks_the_actual_sdk_destination(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-one")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.setenv("GOOGLE_VERTEX_BASE_URL", "https://unused.vertex.invalid")
    monkeypatch.delenv("GOOGLE_GEMINI_BASE_URL", raising=False)

    response = await auth_client.patch(
        "/api/settings",
        json={
            "generation_allow_json_mode_fallback": True,
            "generation_allow_prompt_only_fallback": True,
        },
    )
    assert response.status_code == 200
    initial_settings = response.json()
    initial_destination = await _google_sdk_destination("non-secret-key-one")
    assert initial_destination == (
        True,
        None,
        None,
        "https://aiplatform.googleapis.com/",
        "v1beta1",
    )

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-two")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west4")
    monkeypatch.setenv("GOOGLE_VERTEX_BASE_URL", "https://another-unused.vertex.invalid")
    ignored_settings = (await auth_client.get("/api/settings")).json()
    ignored_destination = await _google_sdk_destination("non-secret-key-two")

    assert ignored_destination == initial_destination
    assert (
        ignored_settings["generation_format_fingerprint"]
        == initial_settings["generation_format_fingerprint"]
    )
    assert ignored_settings["generation_allow_json_mode_fallback"] is True
    assert ignored_settings["generation_allow_prompt_only_fallback"] is True

    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "")
    empty_url_settings = (await auth_client.get("/api/settings")).json()
    empty_url_destination = await _google_sdk_destination("non-secret-key-empty-url")
    assert empty_url_destination == initial_destination
    assert (
        empty_url_settings["generation_format_fingerprint"]
        == initial_settings["generation_format_fingerprint"]
    )

    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://proxy.invalid")
    url_settings = (await auth_client.get("/api/settings")).json()
    url_destination = await _google_sdk_destination("non-secret-key-three")

    assert url_destination[3] == "https://proxy.invalid"
    assert url_destination != ignored_destination
    assert (
        url_settings["generation_format_fingerprint"]
        != ignored_settings["generation_format_fingerprint"]
    )
    assert url_settings["generation_allow_json_mode_fallback"] is False
    assert url_settings["generation_allow_prompt_only_fallback"] is False

    monkeypatch.delenv("GOOGLE_GEMINI_BASE_URL")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "false")
    mode_settings = (await auth_client.get("/api/settings")).json()
    mode_destination = await _google_sdk_destination("non-secret-key-four")

    assert mode_destination[0] is False
    assert mode_destination[3] == "https://generativelanguage.googleapis.com/"
    assert mode_destination[4] == "v1beta"
    assert mode_destination != initial_destination
    assert (
        mode_settings["generation_format_fingerprint"]
        != initial_settings["generation_format_fingerprint"]
    )
    assert mode_settings["generation_allow_json_mode_fallback"] is False
    assert mode_settings["generation_allow_prompt_only_fallback"] is False


async def test_google_model_change_invalidates_format_choices(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.patch(
        "/api/settings",
        json={
            "generation_provider": "google",
            "generation_model": "model-one",
            "generation_allow_json_mode_fallback": True,
            "generation_allow_prompt_only_fallback": True,
        },
    )
    assert response.status_code == 200
    original_fingerprint = response.json()["generation_format_fingerprint"]

    response = await auth_client.patch("/api/settings", json={"generation_model": "model-two"})

    assert response.status_code == 200
    assert response.json()["generation_format_fingerprint"] != original_fingerprint
    assert response.json()["generation_allow_json_mode_fallback"] is False
    assert response.json()["generation_allow_prompt_only_fallback"] is False


async def test_google_url_change_rebinds_stale_one_field_grant(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://first-proxy.invalid")
    response = await auth_client.patch(
        "/api/settings",
        json={
            "generation_provider": "google",
            "generation_model": "model",
            "generation_allow_json_mode_fallback": True,
            "generation_allow_prompt_only_fallback": True,
        },
    )
    assert response.status_code == 200
    original_fingerprint = response.json()["generation_format_fingerprint"]

    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://second-proxy.invalid")
    response = await auth_client.patch(
        "/api/settings",
        json={"generation_allow_json_mode_fallback": True},
    )

    assert response.status_code == 200
    assert response.json()["generation_format_fingerprint"] != original_fingerprint
    assert response.json()["generation_allow_json_mode_fallback"] is True
    assert response.json()["generation_allow_prompt_only_fallback"] is False


async def test_google_key_changes_preserve_format_choices(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.patch(
        "/api/settings",
        json={
            "generation_provider": "google",
            "generation_model": "model",
            "generation_allow_json_mode_fallback": True,
            "generation_allow_prompt_only_fallback": True,
        },
    )
    assert response.status_code == 200
    fingerprint = response.json()["generation_format_fingerprint"]

    for key in ("non-secret-key-one", "non-secret-key-two"):
        response = await auth_client.put("/api/settings/api-keys", json={"google": key})
        assert response.status_code == 200
        assert key not in response.text

        settings = (await auth_client.get("/api/settings")).json()
        assert settings["generation_format_fingerprint"] == fingerprint
        assert settings["generation_allow_json_mode_fallback"] is True
        assert settings["generation_allow_prompt_only_fallback"] is True


async def test_google_url_credentials_and_routing_queries_are_bound_without_disclosure(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "GOOGLE_GEMINI_BASE_URL",
        "https://first:secret-one@proxy.invalid/v1?route=primary&token=secret-one",
    )
    first_response = await auth_client.get("/api/settings")
    first_settings = first_response.json()
    first_destination = await _google_sdk_destination("non-secret-key-one")

    monkeypatch.setenv(
        "GOOGLE_GEMINI_BASE_URL",
        "https://second:secret-two@proxy.invalid/v1?route=primary&token=secret-two",
    )
    second_response = await auth_client.get("/api/settings")
    second_settings = second_response.json()
    second_destination = await _google_sdk_destination("non-secret-key-two")

    monkeypatch.setenv(
        "GOOGLE_GEMINI_BASE_URL",
        "https://second:secret-two@proxy.invalid/v1?route=secondary&token=secret-two",
    )
    third_response = await auth_client.get("/api/settings")
    third_settings = third_response.json()
    third_destination = await _google_sdk_destination("non-secret-key-three")

    assert "secret-one" not in first_response.text
    assert "secret-two" not in second_response.text
    assert first_destination[3] != second_destination[3]
    assert (
        first_settings["generation_format_fingerprint"]
        != second_settings["generation_format_fingerprint"]
    )
    assert "secret-two" not in third_response.text
    assert second_destination[3] != third_destination[3]
    assert (
        second_settings["generation_format_fingerprint"]
        != third_settings["generation_format_fingerprint"]
    )


@pytest.mark.parametrize(
    ("vertexai", "default_url", "expected_vertexai", "expected_api_version"),
    [
        ("true", "https://aiplatform.googleapis.com/", True, "v1beta1"),
        ("false", "https://generativelanguage.googleapis.com/", False, "v1beta"),
    ],
)
async def test_google_implicit_and_explicit_default_url_share_identity(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    vertexai: str,
    default_url: str,
    expected_vertexai: bool,
    expected_api_version: str,
) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", vertexai)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-one")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.delenv("GOOGLE_GEMINI_BASE_URL", raising=False)

    implicit_settings = (await auth_client.get("/api/settings")).json()
    implicit_sdk = await _google_sdk_destination("non-secret-key-one")

    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", default_url)
    explicit_settings = (await auth_client.get("/api/settings")).json()
    explicit_sdk = await _google_sdk_destination("non-secret-key-two")

    assert implicit_sdk[0] is expected_vertexai
    assert implicit_sdk[3] == default_url
    assert implicit_sdk[4] == expected_api_version
    assert explicit_sdk[0] is expected_vertexai
    assert explicit_sdk[3] == default_url
    assert explicit_sdk[4] == expected_api_version
    assert (
        implicit_settings["generation_format_fingerprint"]
        == explicit_settings["generation_format_fingerprint"]
    )


@pytest.mark.parametrize("value", [None, "true", 1])
async def test_format_choices_require_strict_boolean(
    auth_client: AsyncClient, value: object
) -> None:
    response = await auth_client.patch(
        "/api/settings", json={"generation_allow_json_mode_fallback": value}
    )
    assert response.status_code == 422
