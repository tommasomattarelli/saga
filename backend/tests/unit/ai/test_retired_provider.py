import pytest

from app.ai.providers import base


def test_direct_anthropic_provider_is_rejected_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(base, "_providers", {})

    with pytest.raises(ValueError, match="removed.*OpenRouter"):
        base.get_provider("anthropic")

    assert base._providers == {}
