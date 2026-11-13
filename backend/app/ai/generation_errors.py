from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

import httpx
from google.genai.errors import APIError as GoogleAPIError
from openai import APIConnectionError, APIStatusError, APITimeoutError


class Adapter(StrEnum):
    OPENAI = "openai"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    LOCAL = "local"


class FailureAction(StrEnum):
    RETRY = "retry"
    RATE_LIMIT = "rate_limit"
    FALLBACK = "fallback"
    CONTEXT = "context"
    REFUSAL = "refusal"
    TRUNCATED = "truncated"
    CANCELLED = "cancelled"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class FailureSignals:
    adapter: Adapter
    http_status: int | None = None
    code: str | int | None = None
    status: str | None = None
    error_type: str | None = None
    exception: BaseException | None = None
    pre_io_schema_incompatibility: bool = False
    refusal: bool = False
    context_length_exceeded: bool = False
    prompt_blocked: bool = False
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class FailureClassification:
    action: FailureAction
    reason: str
    message: str


_OPENAI_QUOTA_CODES = {
    "insufficient_quota",
    "credit_balance_exhausted",
    "organization_spend_limit_exceeded",
    "project_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
}
_RETRY_STATUSES = {408, 500, 502, 503, 504}
_OPENAI_RETRY_STATUSES = _RETRY_STATUSES | {409}
_ROUTER_RETRY_TYPES = {
    "timeout",
    "server",
    "provider_overloaded",
    "provider_unavailable",
}
_ROUTER_TERMINAL: dict[str, tuple[FailureAction, str]] = {
    "context_length_exceeded": (FailureAction.CONTEXT, "context_length_exceeded"),
    "string_too_long": (FailureAction.STOP, "input_field_too_long"),
    "refusal": (FailureAction.REFUSAL, "refusal"),
    "content_policy_violation": (FailureAction.REFUSAL, "refusal"),
    "max_tokens_exceeded": (FailureAction.STOP, "token_limit_exceeded"),
    "token_limit_exceeded": (FailureAction.STOP, "token_limit_exceeded"),
    "authentication": (FailureAction.STOP, "provider_request_rejected"),
    "permission_denied": (FailureAction.STOP, "provider_request_rejected"),
    "payment_required": (FailureAction.STOP, "provider_request_rejected"),
    "invalid_request": (FailureAction.STOP, "provider_request_rejected"),
    "invalid_prompt": (FailureAction.STOP, "provider_request_rejected"),
    "not_found": (FailureAction.STOP, "provider_request_rejected"),
    "precondition_failed": (FailureAction.STOP, "provider_request_rejected"),
    "payload_too_large": (FailureAction.STOP, "provider_request_rejected"),
    "unprocessable": (FailureAction.STOP, "provider_request_rejected"),
}
_GOOGLE_STOP_FINISHES = {
    "SAFETY",
    "RECITATION",
    "BLOCKLIST",
    "PROHIBITED_CONTENT",
    "SPII",
    "LANGUAGE",
}


def _result(action: FailureAction, reason: str) -> FailureClassification:
    messages = {
        FailureAction.RETRY: "Temporary provider failure; retry may be attempted.",
        FailureAction.RATE_LIMIT: "Provider rate limit reached; retry may be attempted.",
        FailureAction.FALLBACK: "The requested schema mode is not supported before sending.",
        FailureAction.CONTEXT: "The request exceeds the provider context limit.",
        FailureAction.REFUSAL: "The provider refused the request.",
        FailureAction.TRUNCATED: "The provider response was truncated.",
        FailureAction.CANCELLED: "Generation was cancelled.",
        FailureAction.STOP: "Generation failed and must not be retried automatically.",
    }
    return FailureClassification(action=action, reason=reason, message=messages[action])


def classify_failure(signals: FailureSignals) -> FailureClassification:
    if isinstance(signals.exception, asyncio.CancelledError):
        return _result(FailureAction.CANCELLED, "cancelled")

    if signals.pre_io_schema_incompatibility and (
        signals.exception is not None
        or signals.http_status is not None
        or signals.code is not None
        or signals.status is not None
        or signals.error_type is not None
        or signals.refusal
        or signals.context_length_exceeded
        or signals.prompt_blocked
        or signals.finish_reason is not None
    ):
        return _result(FailureAction.STOP, "invalid_classification_input")

    if signals.exception is not None:
        if isinstance(signals.exception, (APIConnectionError, APITimeoutError)):
            return _result(FailureAction.RETRY, "transport_failure")
        if isinstance(signals.exception, (httpx.NetworkError, httpx.TimeoutException)):
            return _result(FailureAction.RETRY, "transport_failure")
        known_status_error = (
            isinstance(signals.exception, (APIStatusError, GoogleAPIError))
            and signals.http_status is not None
        )
        if not known_status_error:
            return _result(FailureAction.STOP, "internal_failure")

    if signals.refusal:
        return _result(FailureAction.REFUSAL, "refusal")
    if signals.context_length_exceeded:
        return _result(FailureAction.CONTEXT, "context_length_exceeded")

    finish = (signals.finish_reason or "").upper()
    if finish == "CONTENT_FILTER":
        return _result(FailureAction.REFUSAL, "refusal")
    if finish == "LENGTH" or (signals.adapter is Adapter.GOOGLE and finish == "MAX_TOKENS"):
        return _result(FailureAction.TRUNCATED, "truncated")
    if signals.prompt_blocked or (
        signals.adapter is Adapter.GOOGLE and finish in _GOOGLE_STOP_FINISHES
    ):
        return _result(FailureAction.STOP, "content_blocked")

    if signals.pre_io_schema_incompatibility:
        return _result(FailureAction.FALLBACK, "schema_mode_unsupported")

    code = str(signals.code or "").lower()
    status = (signals.status or "").upper()
    error_type = (signals.error_type or "").lower()
    if code == "context_length_exceeded":
        return _result(FailureAction.CONTEXT, "context_length_exceeded")

    if signals.adapter is Adapter.OPENROUTER:
        terminal = _ROUTER_TERMINAL.get(error_type)
        if terminal:
            return _result(*terminal)
        if error_type == "rate_limit_exceeded":
            return _result(FailureAction.RATE_LIMIT, "rate_limited")
        if error_type in _ROUTER_RETRY_TYPES:
            return _result(FailureAction.RETRY, error_type)
        if error_type:
            return _result(FailureAction.STOP, "unmapped_router_error")
        if code == "429":
            return _result(FailureAction.RATE_LIMIT, "rate_limited")
        if signals.http_status == 429:
            return _result(FailureAction.RATE_LIMIT, "rate_limited")
        if signals.http_status in {408, 502, 503}:
            return _result(FailureAction.RETRY, "transient_provider_failure")
        return _result(FailureAction.STOP, "unclassified_provider_failure")

    if signals.adapter is Adapter.GOOGLE:
        if status == "RESOURCE_EXHAUSTED" and signals.http_status == 429:
            return _result(FailureAction.RATE_LIMIT, "rate_limited")
        if status in {"INVALID_ARGUMENT", "UNAUTHENTICATED", "PERMISSION_DENIED", "NOT_FOUND"}:
            return _result(FailureAction.STOP, "provider_request_rejected")
        if signals.http_status in _RETRY_STATUSES:
            return _result(FailureAction.RETRY, "transient_provider_failure")
        return _result(FailureAction.STOP, "unclassified_provider_failure")

    if signals.adapter is Adapter.OPENAI:
        if signals.http_status == 429:
            if code in _OPENAI_QUOTA_CODES:
                return _result(FailureAction.STOP, "quota_or_billing_limit")
            if code in {"rate_limit_exceeded", "slow_down"} or error_type == "rate_limit_error":
                return _result(FailureAction.RATE_LIMIT, "rate_limited")
            return _result(FailureAction.STOP, "unclassified_rate_limit")
        if signals.http_status in _OPENAI_RETRY_STATUSES:
            return _result(FailureAction.RETRY, "transient_provider_failure")
        return _result(FailureAction.STOP, "unclassified_provider_failure")

    if signals.http_status == 429:
        return _result(FailureAction.RATE_LIMIT, "rate_limited")
    if signals.http_status in _RETRY_STATUSES:
        return _result(FailureAction.RETRY, "transient_provider_failure")
    return _result(FailureAction.STOP, "unclassified_provider_failure")
