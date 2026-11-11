import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.ai.generation_context import generation_context
from app.ai.router import get_generation
from app.exceptions import ValidationError
from app.memory.batch_source_contracts import BatchInput
from app.memory.producer_prompts import prepare_request
from app.memory.producers import generate_memory
from app.memory.production_policy import FactsPolicy
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
    provider.generate.return_value = '{"facts":[]}'
    source = BatchInput.model_validate(
        {
            "turns": (
                {
                    "reference": "t1",
                    "turn_id": uuid.uuid4(),
                    "player_action": "look",
                    "narration": "The inn is closed.",
                    "operations": None,
                },
            )
        }
    )
    facts_policy = FactsPolicy.model_validate(
        {
            "max_per_batch": 4,
            "importance_levels": [
                {"name": "ordinary", "criteria": "Useful later", "examples": "A clue."}
            ],
        }
    )
    request = prepare_request("facts", source, language="en", facts_policy=facts_policy)
    with patch("app.ai.providers.openai.OpenAIProvider", return_value=provider) as factory:
        with generation_context(owner):
            task = asyncio.create_task(generate_memory(request))
        resolved = await task

    factory.assert_called_once_with(api_key="background-key")
    assert resolved.facts == ()
    assert provider.generate.call_args.kwargs["model"] == "background-model"
    assert request.source.turns[0].narration == "The inn is closed."
    with pytest.raises(ValidationError, match="context"):
        await get_generation()
