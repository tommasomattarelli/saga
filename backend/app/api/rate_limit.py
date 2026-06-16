"""Per-user rate limiting for the turns endpoint via slowapi."""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from app.config_loader import load_saga_config


def _turns_per_minute() -> int:
    cfg = load_saga_config()
    return int(cfg.get("api", {}).get("rate_limit", {}).get("turns_per_minute", 10))


def _user_id_key(request: Request) -> str:
    """Key by user_id stored on request.state by the auth dependency, fall back to IP."""
    user = getattr(request.state, "rate_limit_user_id", None)
    if user:
        return str(user)
    return get_remote_address(request)


limiter = Limiter(key_func=_user_id_key)


def turns_limit() -> str:
    return f"{_turns_per_minute()}/minute"


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please wait before submitting another action."},
    )
