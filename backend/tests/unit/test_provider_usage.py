import asyncio
from unittest.mock import AsyncMock

import pytest
from provider_trace import ProviderTrace

from app.ai.providers.base import AIProvider
from app.ai.providers.usage import UsageMetadata, capture_usage, usage_scope


def test_usage_scope_captures_partial_fields_and_correlation() -> None:
    response = {
        "id": "resp-1",
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 4,
            "total_tokens": 4,
            "prompt_tokens_details": {"cached_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 2},
        },
    }
    with usage_scope(role="actor", step=2, beat=1, npc_id="n1", npc_name="Lysa") as sink:
        capture_usage(response, model="m")
    assert sink.items == [
        UsageMetadata(
            response_id="resp-1",
            model="m",
            input_tokens=0,
            output_tokens=4,
            total_tokens=4,
            cached_input_tokens=0,
            reasoning_output_tokens=2,
            role="actor",
            step=2,
            beat=1,
            npc_id="n1",
            npc_name="Lysa",
        )
    ]


def test_usage_fields_validate_nullable_numeric_primitives() -> None:
    with usage_scope() as sink:
        capture_usage(
            {
                "usage": {
                    "prompt_tokens": True,
                    "completion_tokens": "5",
                    "total_tokens": 0,
                    "cost": "0.2",
                }
            },
            model="m",
        )
    usage = sink.items[0]
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens == 0
    assert usage.cost is None
    assert usage.currency is None


def test_response_id_is_kept_when_token_usage_is_absent() -> None:
    with usage_scope(role="dm", step=0) as sink:
        capture_usage({"id": "response-only"}, model="m")
    assert sink.items[0].response_id == "response-only"
    assert sink.items[0].input_tokens is None
    assert sink.items[0].cost is None


def test_inner_scope_preserves_outer_correlation() -> None:
    with usage_scope(npc_id="n1", step=3) as outer, usage_scope(role="actor") as inner:
        capture_usage({"usage": {"prompt_tokens": 1}}, model="m")
    assert inner.items[0].npc_id == "n1"
    assert inner.items[0].step == 3
    assert outer.items == []


def test_usage_reports_group_missing_and_true_zero() -> None:
    from usage_report import usage_csv, usage_markdown

    rows = [
        {
            "key": "a",
            "model": "m",
            "scenario": "case",
            "usage": [
                {
                    "role": "actor",
                    "step": 2,
                    "npc_id": "n1",
                    "input_tokens": 0,
                    "output_tokens": 5,
                    "total_tokens": 5,
                    "cached_input_tokens": 2,
                    "reasoning_output_tokens": 1,
                }
            ],
        },
        {
            "key": "b",
            "model": "m",
            "scenario": "case",
            "usage": [
                {
                    "role": "actor",
                    "step": 2,
                    "npc_id": "n1",
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                }
            ],
        },
    ]
    csv = usage_csv(rows)
    markdown = usage_markdown(rows)
    assert "cached_input_tokens" in csv and "reasoning_output_tokens" in csv
    assert (
        "| m | case | 2 | actor | n1 | 2 | 0 | 5 | 5 | 1 | 1 | 1 | 2 | 1 | — | — | — |" in markdown
    )
    assert "| m | case | 2 | actor | n1 |" in markdown
    assert "response_id" in csv and "npc_name" in csv and "seconds" in csv


def test_report_preserves_step_zero_and_does_not_add_different_currencies() -> None:
    from usage_report import usage_markdown

    markdown = usage_markdown(
        [
            {
                "model": "m",
                "scenario": "case",
                "seconds": 1.5,
                "rate_limit_wait_seconds": 3.0,
                "usage": [
                    {
                        "step": 0,
                        "role": "actor",
                        "npc_id": None,
                        "input_tokens": 1,
                        "cost": 0.2,
                        "currency": "USD",
                    }
                ],
            },
            {
                "model": "m",
                "scenario": "case",
                "seconds": 2,
                "rate_limit_wait_seconds": 7.0,
                "usage": [
                    {
                        "step": 0,
                        "role": "actor",
                        "npc_id": None,
                        "input_tokens": None,
                        "cost": 3,
                        "currency": "EUR",
                    }
                ],
            },
        ]
    )
    assert (
        "| m | case | 0 | actor |  | 2 | 1 | — | — | 1 | 2 | 2 | — | — | 3.5 | 10.0 | EUR 3, USD 0.2 |"
        in markdown
    )


@pytest.mark.asyncio
async def test_concurrent_scopes_keep_usage_correlated_when_completion_order_inverts() -> None:
    provider = AsyncMock(spec=AIProvider)

    async def generate(**_: object) -> str:
        await asyncio.sleep(0.01 if current_correlation().npc_id == "n1" else 0)
        capture_usage({"usage": {"prompt_tokens": 1}}, model="m")
        return "ok"

    from app.ai.providers.usage import current_correlation

    provider.generate.side_effect = generate

    async def traced(npc_id: str, step: int) -> tuple[str | None, int | None]:
        with usage_scope(npc_id=npc_id, step=step):
            trace = ProviderTrace(provider)
            await trace.generate("s", [], "m")
        item = trace.usage[0]
        return item.npc_id, item.step

    first, second = await asyncio.gather(traced("n1", 1), traced("n2", 2))
    assert first == ("n1", 1)
    assert second == ("n2", 2)


@pytest.mark.asyncio
async def test_outer_correlation_survives_trace_inner_role_scope() -> None:
    provider = AsyncMock(spec=AIProvider)

    async def generate(**_: object) -> str:
        capture_usage({"usage": {"prompt_tokens": 1}}, model="m")
        return "ok"

    provider.generate.side_effect = generate
    with usage_scope(npc_id="n3", step=4):
        trace = ProviderTrace(provider)
        await trace.generate("s", [], "m")
    assert trace.usage[0].role == "actor"
    assert trace.usage[0].npc_id == "n3"
    assert trace.usage[0].step == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("with_tools", [False, True])
async def test_trace_keeps_billed_usage_when_provider_rejects_the_completion(with_tools) -> None:
    provider = AsyncMock(spec=AIProvider)

    async def reject(**_: object) -> str:
        capture_usage({"usage": {"prompt_tokens": 3, "completion_tokens": 5}}, model="m")
        raise ValueError("response truncated")

    provider.generate.side_effect = reject
    provider.generate_with_tools.side_effect = reject
    trace = ProviderTrace(provider)
    with pytest.raises(ValueError, match="truncated"):
        if with_tools:
            await trace.generate_with_tools("s", [], [], "m")
        else:
            await trace.generate("s", [], "m")
    assert trace.usage[0].input_tokens == 3
    assert trace.usage[0].output_tokens == 5


@pytest.mark.asyncio
async def test_previous_direct_concurrent_scope_capture() -> None:
    async def invoke(npc_id: str, step: int, delay: float) -> tuple[str, int]:
        with usage_scope(npc_id=npc_id, step=step) as sink:
            await asyncio.sleep(delay)
            capture_usage({"usage": {"prompt_tokens": step}}, model="m")
        return sink.items[0].npc_id or "", sink.items[0].input_tokens or 0

    first, second = await asyncio.gather(invoke("n1", 1, 0.01), invoke("n2", 2, 0))
    assert first == ("n1", 1)
    assert second == ("n2", 2)
