"""Task-local capture of provider-reported completion usage."""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class UsageCorrelation:
    role: str | None = None
    step: int | None = None
    beat: int | None = None
    npc_id: str | None = None
    npc_name: str | None = None


@dataclass(frozen=True)
class UsageMetadata:
    response_id: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    cost: float | None = None
    currency: str | None = None
    role: str | None = None
    step: int | None = None
    beat: int | None = None
    npc_id: str | None = None
    npc_name: str | None = None


class UsageCollector:
    def __init__(self, correlation: UsageCorrelation) -> None:
        self.correlation = correlation
        self.items: list[UsageMetadata] = []


_collector: ContextVar[UsageCollector | None] = ContextVar("provider_usage", default=None)
_correlation: ContextVar[UsageCorrelation | None] = ContextVar(
    "provider_usage_correlation", default=None
)


class UsageScope:
    def __init__(self, correlation: UsageCorrelation) -> None:
        current = current_correlation()
        self.correlation = UsageCorrelation(
            role=correlation.role if correlation.role is not None else current.role,
            step=correlation.step if correlation.step is not None else current.step,
            beat=correlation.beat if correlation.beat is not None else current.beat,
            npc_id=correlation.npc_id if correlation.npc_id is not None else current.npc_id,
            npc_name=correlation.npc_name
            if correlation.npc_name is not None
            else current.npc_name,
        )
        self.collector = UsageCollector(self.correlation)
        self._collector_token: Token[UsageCollector | None] | None = None
        self._correlation_token: Token[UsageCorrelation | None] | None = None

    def __enter__(self) -> UsageCollector:
        self._collector_token = _collector.set(self.collector)
        self._correlation_token = _correlation.set(self.correlation)
        return self.collector

    def __exit__(self, *_: object) -> None:
        if self._collector_token is not None:
            _collector.reset(self._collector_token)
        if self._correlation_token is not None:
            _correlation.reset(self._correlation_token)


def usage_scope(
    *,
    role: str | None = None,
    step: int | None = None,
    beat: int | None = None,
    npc_id: str | None = None,
    npc_name: str | None = None,
) -> UsageScope:
    return UsageScope(UsageCorrelation(role, step, beat, npc_id, npc_name))


def current_correlation() -> UsageCorrelation:
    return _correlation.get() or UsageCorrelation()


def _field(value: object, key: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _text(value: object | None) -> str | None:
    return value if isinstance(value, str) else None


def _integer(value: object | None) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: object | None) -> float | None:
    return (
        float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    )


def capture_usage(response: object, *, model: str | None = None) -> UsageMetadata | None:
    collector = _collector.get()
    usage = _field(response, "usage")
    if collector is None:
        return None
    prompt = _field(usage, "prompt_tokens_details")
    completion = _field(usage, "completion_tokens_details")
    correlation = collector.correlation
    details = UsageMetadata(
        response_id=_text(_field(response, "id")),
        model=_text(_field(response, "model")) or model,
        input_tokens=_integer(_field(usage, "prompt_tokens")),
        output_tokens=_integer(_field(usage, "completion_tokens")),
        total_tokens=_integer(_field(usage, "total_tokens")),
        cached_input_tokens=_integer(_field(prompt, "cached_tokens")),
        reasoning_output_tokens=_integer(_field(completion, "reasoning_tokens")),
        cost=_number(_field(usage, "cost")),
        currency=_text(_field(usage, "currency")),
        role=correlation.role,
        step=correlation.step,
        beat=correlation.beat,
        npc_id=correlation.npc_id,
        npc_name=correlation.npc_name,
    )
    collector.items.append(details)
    return details
