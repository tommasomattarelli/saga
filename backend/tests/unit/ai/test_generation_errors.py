from __future__ import annotations

import asyncio
from dataclasses import replace

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError

from app.ai.generation_errors import (
    Adapter,
    FailureAction,
    FailureSignals,
    classify_failure,
)


@pytest.mark.parametrize(
    ("adapter", "status", "expected"),
    [
        (Adapter.OPENAI, 408, FailureAction.RETRY),
        (Adapter.OPENAI, 409, FailureAction.RETRY),
        (Adapter.OPENAI, 500, FailureAction.RETRY),
        (Adapter.GOOGLE, 502, FailureAction.RETRY),
        (Adapter.OPENROUTER, 503, FailureAction.RETRY),
        (Adapter.LOCAL, 504, FailureAction.RETRY),
        (Adapter.OPENAI, 400, FailureAction.STOP),
        (Adapter.OPENAI, 404, FailureAction.STOP),
        (Adapter.GOOGLE, 400, FailureAction.STOP),
        (Adapter.LOCAL, 422, FailureAction.STOP),
    ],
)
def test_status_classification_is_adapter_scoped(
    adapter: Adapter, status: int, expected: FailureAction
) -> None:
    result = classify_failure(FailureSignals(adapter=adapter, http_status=status))

    assert result.action is expected
    assert result.reason


def test_cancellation_is_terminal_and_does_not_expose_exception_text() -> None:
    result = classify_failure(
        FailureSignals(
            adapter=Adapter.OPENAI,
            exception=asyncio.CancelledError("private provider detail"),
        )
    )

    assert result.action is FailureAction.CANCELLED
    assert result.reason == "cancelled"
    assert result.message == "Generation was cancelled."
    assert "private provider detail" not in result.message + result.reason


@pytest.mark.parametrize(
    ("code", "error_type", "expected"),
    [
        (None, "rate_limit_error", FailureAction.RATE_LIMIT),
        ("rate_limit_exceeded", None, FailureAction.RATE_LIMIT),
        ("slow_down", None, FailureAction.RATE_LIMIT),
        ("insufficient_quota", None, FailureAction.STOP),
        ("credit_balance_exhausted", None, FailureAction.STOP),
        ("organization_spend_limit_exceeded", None, FailureAction.STOP),
        ("mystery", None, FailureAction.STOP),
    ],
)
def test_openai_429_requires_known_rate_signal(
    code: str | None, error_type: str | None, expected: FailureAction
) -> None:
    result = classify_failure(
        FailureSignals(
            adapter=Adapter.OPENAI,
            http_status=429,
            code=code,
            error_type=error_type,
        )
    )

    assert result.action is expected


def test_prose_and_near_miss_codes_never_create_retry_or_fallback() -> None:
    for signals in (
        FailureSignals(
            adapter=Adapter.OPENAI,
            http_status=503,
            exception=RuntimeError("503 rate limit /private/provider/path"),
        ),
        FailureSignals(
            adapter=Adapter.OPENAI,
            http_status=429,
            exception=RuntimeError("rate limit /private/provider/path"),
        ),
        FailureSignals(adapter=Adapter.OPENAI, http_status=400, code="unsupported_value"),
    ):
        result = classify_failure(signals)
        assert result.action is FailureAction.STOP
        assert "503" not in result.message + result.reason
        assert "rate limit" not in result.message + result.reason
        assert "/private/provider/path" not in result.message + result.reason


@pytest.mark.parametrize(
    ("status", "code", "http_status", "expected"),
    [
        ("RESOURCE_EXHAUSTED", None, 429, FailureAction.RATE_LIMIT),
        ("INVALID_ARGUMENT", None, 503, FailureAction.STOP),
        ("UNAUTHENTICATED", None, 503, FailureAction.STOP),
        ("PERMISSION_DENIED", None, 503, FailureAction.STOP),
        ("NOT_FOUND", None, 503, FailureAction.STOP),
        (None, "503", None, FailureAction.STOP),
    ],
)
def test_google_typed_status_precedes_http_status(
    status: str | None, code: str | None, http_status: int | None, expected: FailureAction
) -> None:
    result = classify_failure(
        FailureSignals(
            adapter=Adapter.GOOGLE,
            http_status=http_status,
            status=status,
            code=code,
        )
    )

    assert result.action is expected


def test_router_typed_error_classification_precedes_http_status() -> None:
    signals = FailureSignals(
        adapter=Adapter.OPENROUTER,
        http_status=200,
        error_type="provider_overloaded",
    )

    result = classify_failure(signals)

    assert result.action is FailureAction.RETRY
    assert result.reason == "provider_overloaded"


@pytest.mark.parametrize("code", [429, "429"])
def test_router_code_only_rate_limit_is_classified_without_http_status(
    code: str | int,
) -> None:
    result = classify_failure(
        FailureSignals(adapter=Adapter.OPENROUTER, http_status=200, code=code)
    )

    assert result.action is FailureAction.RATE_LIMIT
    assert result.reason == "rate_limited"


def test_router_unknown_error_type_precedes_code_only_rate_limit() -> None:
    result = classify_failure(
        FailureSignals(
            adapter=Adapter.OPENROUTER,
            http_status=200,
            code=429,
            error_type="unrecognized",
        )
    )

    assert result.action is FailureAction.STOP
    assert result.reason == "unmapped_router_error"


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [
        ("timeout", FailureAction.RETRY),
        ("server_error", FailureAction.STOP),
        ("rate_limit_exceeded", FailureAction.RATE_LIMIT),
        ("context_length_exceeded", FailureAction.CONTEXT),
        ("max_tokens_exceeded", FailureAction.STOP),
        ("refusal", FailureAction.REFUSAL),
        ("payment_required", FailureAction.STOP),
        ("invalid_request", FailureAction.STOP),
    ],
)
def test_router_structured_error_types(error_type: str, expected: FailureAction) -> None:
    result = classify_failure(FailureSignals(adapter=Adapter.OPENROUTER, error_type=error_type))
    assert result.action is expected


def test_pre_io_schema_incompatibility_is_the_only_fallback_class() -> None:
    signals = FailureSignals(adapter=Adapter.OPENAI, pre_io_schema_incompatibility=True)

    assert classify_failure(signals).action is FailureAction.FALLBACK
    assert (
        classify_failure(
            replace(signals, pre_io_schema_incompatibility=False, http_status=400)
        ).action
        is FailureAction.STOP
    )


@pytest.mark.parametrize(
    ("signals", "expected"),
    [
        (FailureSignals(adapter=Adapter.OPENAI, refusal=True), FailureAction.REFUSAL),
        (FailureSignals(adapter=Adapter.OPENAI, finish_reason="length"), FailureAction.TRUNCATED),
        (
            FailureSignals(adapter=Adapter.GOOGLE, finish_reason="MAX_TOKENS"),
            FailureAction.TRUNCATED,
        ),
        (FailureSignals(adapter=Adapter.GOOGLE, finish_reason="SAFETY"), FailureAction.STOP),
        (FailureSignals(adapter=Adapter.GOOGLE, prompt_blocked=True), FailureAction.STOP),
        (
            FailureSignals(adapter=Adapter.OPENAI, context_length_exceeded=True),
            FailureAction.CONTEXT,
        ),
    ],
)
def test_response_terminal_signals_override_transient_status(
    signals: FailureSignals, expected: FailureAction
) -> None:
    result = classify_failure(replace(signals, http_status=503))
    assert result.action is expected


def test_local_gateway_rate_limit_and_unknown_client_failure() -> None:
    assert (
        classify_failure(FailureSignals(adapter=Adapter.LOCAL, http_status=429)).action
        is FailureAction.RATE_LIMIT
    )
    assert (
        classify_failure(
            FailureSignals(
                adapter=Adapter.LOCAL,
                http_status=400,
                exception=RuntimeError("try 503 /private/provider/path"),
            )
        ).action
        is FailureAction.STOP
    )


@pytest.mark.parametrize(
    ("adapter", "exception"),
    [
        (adapter, exception)
        for adapter in (Adapter.OPENAI, Adapter.OPENROUTER, Adapter.LOCAL)
        for exception in (
            APIConnectionError(request=httpx.Request("POST", "https://example.test")),
            APITimeoutError(request=httpx.Request("POST", "https://example.test")),
        )
    ],
)
def test_typed_transport_failures_are_retryable(
    adapter: Adapter,
    exception: APIConnectionError | APITimeoutError,
) -> None:
    result = classify_failure(FailureSignals(adapter=adapter, exception=exception))

    assert result.action is FailureAction.RETRY
    assert result.reason == "transport_failure"


@pytest.mark.parametrize(
    ("error_type", "http_status", "expected"),
    [
        ("server", 503, FailureAction.RETRY),
        ("authentication", 503, FailureAction.STOP),
        ("unmapped", 503, FailureAction.STOP),
        ("unmapped", 429, FailureAction.STOP),
        ("server_error", 503, FailureAction.STOP),
        (None, 429, FailureAction.RATE_LIMIT),
        (None, 503, FailureAction.RETRY),
    ],
)
def test_router_error_type_table_and_status_fallback(
    error_type: str | None, http_status: int, expected: FailureAction
) -> None:
    result = classify_failure(
        FailureSignals(
            adapter=Adapter.OPENROUTER,
            http_status=http_status,
            error_type=error_type,
        )
    )

    assert result.action is expected
    if error_type == "authentication":
        assert result.reason == "provider_request_rejected"


@pytest.mark.parametrize(
    ("error_type", "expected_action", "reason"),
    [
        ("string_too_long", FailureAction.STOP, "input_field_too_long"),
        ("context_length_exceeded", FailureAction.CONTEXT, "context_length_exceeded"),
    ],
)
def test_router_context_errors_have_accurate_action_and_reason(
    error_type: str, expected_action: FailureAction, reason: str
) -> None:
    result = classify_failure(FailureSignals(adapter=Adapter.OPENROUTER, error_type=error_type))

    assert result.action is expected_action
    assert result.reason == reason
    if error_type == "string_too_long":
        assert "context" not in result.message.lower()


def test_local_context_error_overrides_transient_http_status() -> None:
    result = classify_failure(
        FailureSignals(
            adapter=Adapter.LOCAL,
            http_status=503,
            code="context_length_exceeded",
        )
    )

    assert result.action is FailureAction.CONTEXT


def test_mixed_pre_io_marker_and_remote_failure_is_internal_stop() -> None:
    signals = FailureSignals(adapter=Adapter.OPENAI, http_status=401)
    result = classify_failure(replace(signals, pre_io_schema_incompatibility=True))

    assert result.action is FailureAction.STOP
    assert result.reason == "invalid_classification_input"


@pytest.mark.parametrize(
    "exception",
    [httpx.ConnectError("private provider endpoint"), httpx.TimeoutException("private timeout")],
)
def test_google_httpx_transport_errors_are_retryable(exception: httpx.HTTPError) -> None:
    result = classify_failure(FailureSignals(adapter=Adapter.GOOGLE, exception=exception))

    assert result.action is FailureAction.RETRY
