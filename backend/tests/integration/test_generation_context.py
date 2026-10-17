import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.ai.generation_context import generation_context
from app.ai.router import get_generation
from app.exceptions import ValidationError
from app.memory.fact_extractor import extract_facts
from app.security.auth import decode_token


async def test_background_task_keeps_its_owner_after_request_context_exits(
    auth_client: AsyncClient,
) -> None:
    await auth_client.put("/api/settings/api-keys", json={"openai": "background-key"})
    await auth_client.patch(
        "/api/settings",
        json={"generation_provider": "openai", "generation_model": "background-model"},
    )
    token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    owner = uuid.UUID(str(decode_token(token)["sub"]))
    provider = AsyncMock()
    provider.generate.return_value = '[{"entity_name":"Inn","content":"The inn is closed."}]'
    with patch("app.ai.providers.openai.OpenAIProvider", return_value=provider) as factory:
        with generation_context(owner):
            task = asyncio.create_task(extract_facts("look", "The inn is closed."))
        facts = await task

    assert facts[0]["entity_name"] == "Inn"
    factory.assert_called_once_with(api_key="background-key")
    assert provider.generate.call_args.kwargs["model"] == "background-model"
    with pytest.raises(ValidationError, match="context"):
        await get_generation()
