from unittest.mock import AsyncMock, Mock

import pytest
from eval.support.provider_trace import ProviderTrace

from app.ai.providers.usage import current_correlation


@pytest.mark.asyncio
async def test_provider_trace_supports_memory_diagnostic_roles_and_keeps_default_actor() -> None:
    observed: list[str | None] = []

    async def generate(**_request: object) -> str:
        observed.append(current_correlation().role)
        return "{}"

    provider = Mock()
    provider.generate = AsyncMock(side_effect=generate)
    await ProviderTrace(provider).generate("system", [], "model")
    await ProviderTrace(provider, role="memory_global").generate("system", [], "model")
    assert observed == ["actor", "memory_global"]
