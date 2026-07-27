"""Shared response guards for OpenAI-compatible endpoints (OpenAI, OpenRouter, local).

OpenRouter reports an upstream failure as HTTP 200 with an in-band `error` object and
no `choices`, so the SDK raises nothing and the caller crashes on indexing (#50)."""

from __future__ import annotations

from typing import Any

from app.exceptions import AIProviderError


def _upstream_reason(response: Any) -> str | None:
    error = getattr(response, "error", None)
    if error is None:
        extra = getattr(response, "model_extra", None)
        error = extra.get("error") if isinstance(extra, dict) else None
    if not error:
        return None

    if isinstance(error, dict):
        message, code = error.get("message"), error.get("code")
    else:
        message, code = getattr(error, "message", None), getattr(error, "code", None)

    reason = str(message) if message else "upstream error"
    return f"{reason} (code {code})" if code else reason


def first_choice(response: Any, provider: str) -> Any:
    choices = getattr(response, "choices", None)
    if choices:
        return choices[0]
    raise AIProviderError(provider, _upstream_reason(response) or "no choices in response")


def stream_choice(chunk: Any, provider: str) -> Any | None:
    """None for a benign chunk carrying no choices (keepalive, usage-only trailer)."""
    choices = getattr(chunk, "choices", None)
    if choices:
        return choices[0]
    reason = _upstream_reason(chunk)
    if reason:
        raise AIProviderError(provider, reason)
    return None
