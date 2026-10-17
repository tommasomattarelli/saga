import inspect
from pathlib import Path

import pytest

from app.ai.providers import base
from app.ai.providers.google import GoogleProvider
from app.ai.providers.local import LocalProvider
from app.ai.providers.openai import OpenAIProvider
from app.config import Settings


@pytest.mark.parametrize(
    "provider", [base.AIProvider, OpenAIProvider, GoogleProvider, LocalProvider]
)
@pytest.mark.parametrize("method", ["generate", "stream", "generate_with_tools"])
def test_generation_has_no_temperature_parameter(provider: type, method: str) -> None:
    assert "temperature" not in inspect.signature(getattr(provider, method)).parameters


@pytest.mark.parametrize("name", ["cohere", "groq"])
def test_secondary_providers_are_not_constructed(name: str) -> None:
    with pytest.raises(ValueError, match="Unknown AI provider"):
        base.get_provider(name)


def test_leftover_legacy_dotenv_variables_are_ignored(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SAGA_GLOBAL_PROVIDER=cohere\nSAGA_GLOBAL_MODEL_HIGH=old-model\n"
        "SAGA_MODEL_MEMORY_COMPRESSION_DEFAULT=old-background\n"
        "COHERE_API_KEY=old-key\nGROQ_API_KEY=old-key\n"
    )
    config = Settings(_env_file=env_file)
    assert not hasattr(config, "saga_global_provider")
