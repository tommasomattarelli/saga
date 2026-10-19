"""Embedding policy and vector-space identity from saga.config.yaml (ADR 0018 B)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol

from app.ai.router import PROVIDER_NAMES, get_allowed_providers, get_local_endpoints
from app.config_loader import load_saga_config
from app.exceptions import ValidationError

NEW_PIPELINE = "embed-v1"
LEGACY_PIPELINE = "embed-v1-legacy"

ApiFamily = Literal["openai", "google"]

# The transport is a property of the provider, never a manifest choice: a
# stored space claiming the wrong adapter must fail before any network call.
EXPECTED_API_FAMILY: dict[str, ApiFamily] = {
    "openai": "openai",
    "openrouter": "openai",
    "local": "openai",
    "google": "google",
}

# The historical space the pre-0018 writer produced: direct OpenAI small at 384.
# Only this label unlocks the explicit `dimensions` parameter on OpenAI requests;
# every embed-v1 space is native and never passes `dimensions`.
LEGACY_PROVIDER = "openai"
LEGACY_MODEL = "text-embedding-3-small"
LEGACY_DIMENSIONS = 384
LEGACY_BASE_URL = "https://api.openai.com/v1"

# Hosted base URLs per OpenAI-compatible provider; the model id (e.g.
# `openai/text-embedding-3-small`) is sent verbatim, no per-call overrides.
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_OPENAI_BASE_URL = "https://api.openai.com/v1"

# Documented OpenAI request-limit for embedding inputs; rebuild workers slice
# by policy.batch_size, adapters refuse anything larger than the documented cap.
OPENAI_MAX_EMBEDDING_INPUTS = 2048


@dataclass(frozen=True)
class EmbeddingSpace:
    """Immutable identity of a vector space (ADR 0018 B3; space identity != dimension).

    provider + model + endpoint_name + endpoint_identity + pipeline_version name
    the space the vectors belong to (storage adds the index UUID). Key rotation
    never changes any of these fields — no key material lives here. For
    embed-v1-legacy (and only there) `requested_dimensions` carries 384 so OpenAI
    queries land in the historical space instead of its native 1536.
    """

    provider: str
    model: str
    api_family: ApiFamily  # "openai" | "google" — the transport the adapter uses
    endpoint_name: str | None  # named local endpoint (A5/B2); None for hosted APIs
    endpoint_identity: str | None  # resolved current URL behind the named endpoint
    pipeline_version: str  # embed-v1 | embed-v1-legacy
    requested_dimensions: int | None = None  # None = native; 384 only for embed-v1-legacy


@dataclass(frozen=True)
class EmbeddingCredential:
    """Key material plus the resolved provenance for ONE call (never persisted)."""

    key: str | None
    source: str  # personal | server | missing | not_required


@dataclass(frozen=True)
class EmbeddingPolicy:
    batch_size: int
    rebuild_min_interval_seconds: float
    rebuild_concurrency: int
    rebuild_claim_ttl_seconds: float
    request_timeout_seconds: float
    max_retries: int
    retry_delays_seconds: tuple[float, ...]


@dataclass(frozen=True)
class EmbeddingRebuildConfig:
    """The rebuild worker's pacing/lease knobs, read from MY embedding block."""

    batch_size: int
    rebuild_min_interval_seconds: float
    rebuild_concurrency: int
    rebuild_claim_ttl_seconds: float
    scan_interval_seconds: float


@dataclass(frozen=True)
class ResolvedEmbedding:
    """Everything a caller needs to embed without importing ORM objects.

    Resolved through the router in a short DB session; consumed afterwards in
    network calls that hold no session.
    """

    space: EmbeddingSpace
    credential: EmbeddingCredential
    policy: EmbeddingPolicy


@dataclass(frozen=True)
class EmbeddingBatch:
    """Ordered vectors (1:1 with input text) plus the dimension the response showed."""

    space: EmbeddingSpace
    dimension: int
    vectors: tuple[tuple[float, ...], ...]


class EmbeddingAdapter(Protocol):
    """The transport interface both provider adapters implement."""

    async def embed(
        self, model: str, texts: list[str], *, dimensions: int | None = None
    ) -> tuple[int, list[list[float]]]: ...


def legacy_space() -> EmbeddingSpace:
    """The historical pre-0018 space; queries against it send dimensions=384."""
    return EmbeddingSpace(
        provider=LEGACY_PROVIDER,
        model=LEGACY_MODEL,
        api_family="openai",
        endpoint_name=None,
        endpoint_identity=LEGACY_BASE_URL,
        pipeline_version=LEGACY_PIPELINE,
        requested_dimensions=LEGACY_DIMENSIONS,
    )


def build_space(
    provider: str, model: str, *, pipeline_version: str = NEW_PIPELINE
) -> EmbeddingSpace:
    """Identity for one (provider, model) pair; hosted base URLs are stable here."""
    if provider == "google":
        base_url: str | None = None
    elif provider == "openrouter":
        base_url = _OPENROUTER_BASE_URL
    elif provider == "openai":
        base_url = _OPENAI_BASE_URL
    else:
        raise ValueError(f"Hosted embedding provider `{provider}` has no known base URL")
    return EmbeddingSpace(
        provider=provider,
        model=model,
        api_family="google" if provider == "google" else "openai",
        endpoint_name=None,
        endpoint_identity=base_url,
        pipeline_version=pipeline_version,
    )


def local_space(endpoint_name: str, model: str) -> EmbeddingSpace:
    """Local space carrying BOTH the admin-named endpoint and the URL resolved today."""
    base_url = get_local_endpoints().get(endpoint_name)
    if not base_url:
        raise ValueError(f"Local endpoint `{endpoint_name}` is not configured on this instance")
    return EmbeddingSpace(
        provider="local",
        model=model,
        api_family="openai",
        endpoint_name=endpoint_name,
        endpoint_identity=base_url,
        pipeline_version=NEW_PIPELINE,
    )


def get_embedding_default_space() -> EmbeddingSpace:
    """Space identity of the instance default; a personal profile overrides both halves."""
    default = _default_config()
    provider = str(default.get("provider", "")).strip()
    model = str(default.get("model", "")).strip()
    if provider == "local":
        endpoint_name = str(default.get("local_endpoint") or "").strip()
        if not endpoint_name:
            raise ValueError("embedding.default.local_endpoint must name a configured endpoint")
        return local_space(endpoint_name, model)
    return build_space(provider, model)


def get_embedding_policy() -> EmbeddingPolicy:
    """Static YAML policy: no user, no DB, no network — safe before any credential resolve."""
    config = _embedding_config()
    return EmbeddingPolicy(
        batch_size=int(_number_or(config, "batch_size", 32)),
        rebuild_min_interval_seconds=_number_or(config, "rebuild_min_interval_seconds", 1),
        rebuild_concurrency=int(_number_or(config, "rebuild_concurrency", 1)),
        rebuild_claim_ttl_seconds=_number_or(config, "rebuild_claim_ttl_seconds", 600),
        request_timeout_seconds=_number_or(config, "request_timeout_seconds", 30),
        max_retries=int(_number_or(config, "max_retries", 2)),
        retry_delays_seconds=tuple(_delays(config) or [1.0, 3.0]),
    )


def _retry_delay_total(retries: int, delays: list[float]) -> float:
    """Mirror the runtime loop: it repeats the LAST delay once the table is exhausted."""
    if not delays:
        return 0.0
    if retries <= len(delays):
        return sum(delays[:retries])
    return sum(delays) + (retries - len(delays)) * delays[-1]


def _worst_case_seconds(timeout: float, retries: int, delays: list[float]) -> float:
    return timeout * (retries + 1) + _retry_delay_total(retries, delays)


def worst_case_embedding_call_seconds() -> float:
    """One embed_batch = one HTTP chunk: (max_retries+1) timeouts + the loop's real delays."""
    policy = get_embedding_policy()
    return _worst_case_seconds(
        policy.request_timeout_seconds, policy.max_retries, list(policy.retry_delays_seconds)
    )


def get_embedding_rebuild_config() -> EmbeddingRebuildConfig:
    """Single reader the rebuild worker lazy-imports; values validated at startup."""
    policy = get_embedding_policy()
    config = _embedding_config()
    return EmbeddingRebuildConfig(
        batch_size=policy.batch_size,
        rebuild_min_interval_seconds=policy.rebuild_min_interval_seconds,
        rebuild_concurrency=policy.rebuild_concurrency,
        rebuild_claim_ttl_seconds=policy.rebuild_claim_ttl_seconds,
        scan_interval_seconds=_number_or(config, "scan_interval_seconds", 5),
    )


def _embedding_config() -> dict[str, object]:
    config = load_saga_config().get("embedding")
    return config if isinstance(config, dict) else {}


def _default_config() -> dict[str, object]:
    default = _embedding_config().get("default")
    return default if isinstance(default, dict) else {}


def check_space_contract(space: EmbeddingSpace) -> None:
    """Fail fast on a space that cannot be honored (policy/legacy invariants)."""
    provider_check = space.provider in PROVIDER_NAMES and space.provider in get_allowed_providers()
    if not provider_check:
        raise ValidationError(
            f"Embedding provider `{space.provider}` is not enabled on this instance."
        )
    expected_family = EXPECTED_API_FAMILY.get(space.provider)
    if space.api_family != expected_family:
        raise ValidationError(
            "The embedding transport does not match its provider; refusing to pick an adapter."
        )
    if space.pipeline_version not in (NEW_PIPELINE, LEGACY_PIPELINE):
        raise ValidationError(f"Unknown embedding pipeline `{space.pipeline_version}`.")
    is_legacy = space.pipeline_version == LEGACY_PIPELINE
    is_legacy_identity = space.provider == LEGACY_PROVIDER and space.model == LEGACY_MODEL
    if is_legacy and not is_legacy_identity:
        raise ValidationError(
            "`dimensions=384` applies only to the stored legacy OpenAI small space."
        )
    if not is_legacy and space.requested_dimensions is not None:
        raise ValidationError("Native embedding profiles never request explicit dimensions.")
    if is_legacy and space.requested_dimensions != LEGACY_DIMENSIONS:
        raise ValidationError("The legacy space must request exactly 384 dimensions.")
    expected_url: str | None
    if space.provider == "local":
        if not space.endpoint_name or space.endpoint_name not in get_local_endpoints():
            raise ValidationError(
                f"Local endpoint `{space.endpoint_name}` is not authorized on this instance."
            )
        expected_url = get_local_endpoints()[space.endpoint_name]
    elif space.provider == "openai":
        expected_url = _OPENAI_BASE_URL
    elif space.provider == "openrouter":
        expected_url = _OPENROUTER_BASE_URL
    else:
        expected_url = None
    if space.endpoint_identity != expected_url:
        raise ValidationError(
            "The stored endpoint address is no longer authorized on this instance."
        )


def _number(config: dict[str, object], field: str) -> float | None:
    value = config.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _number_or(config: dict[str, object], field: str, default: float) -> float:
    value = _number(config, field)
    return default if value is None else value


def _delays(config: dict[str, object]) -> list[float] | None:
    raw = config.get("retry_delays_seconds")
    if not isinstance(raw, list) or not raw:
        return None
    delays: list[float] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        delays.append(float(value))
    return delays


def _worst_case(config: dict[str, object]) -> float | None:
    """Finite-only bound, or None when an input is invalid (reported separately)."""
    timeout = _number(config, "request_timeout_seconds")
    retries = _number(config, "max_retries")
    delays = _delays(config)
    if (
        timeout is None
        or not math.isfinite(timeout)
        or timeout <= 0
        or retries is None
        or not math.isfinite(retries)
        or retries != int(retries)
        or retries < 1
        or delays is None
        or any(not math.isfinite(delay) or delay < 1 for delay in delays)
    ):
        return None
    return _worst_case_seconds(timeout, int(retries), delays)


def _policy_problems(config: dict[str, object]) -> list[str]:
    problems: list[str] = []
    batch = _number(config, "batch_size")
    if batch is None or batch != int(batch) or batch < 1:
        problems.append("embedding.batch_size must be a positive integer")
    interval = _number(config, "rebuild_min_interval_seconds")
    if interval is None or interval < 1:
        problems.append("embedding.rebuild_min_interval_seconds must be >= 1 second")
    if _number(config, "rebuild_concurrency") != 1:
        problems.append("embedding.rebuild_concurrency must stay 1 (one request at a time)")
    timeout = _number(config, "request_timeout_seconds")
    if timeout is None or not math.isfinite(timeout) or timeout <= 0:
        problems.append("embedding.request_timeout_seconds must be a positive finite number")
    retries = _number(config, "max_retries")
    if retries is None or not math.isfinite(retries) or retries != int(retries) or retries < 1:
        problems.append("embedding.max_retries must be a positive integer")
    delays = _delays(config)
    if delays is None:
        problems.append("embedding.retry_delays_seconds must be a non-empty list of numbers")
    elif any(not math.isfinite(delay) or delay < 1 for delay in delays):
        problems.append("embedding.retry_delays_seconds values must be finite numbers >= 1 second")
    claim_ttl = _number(config, "rebuild_claim_ttl_seconds")
    if claim_ttl is None or not math.isfinite(claim_ttl) or claim_ttl <= 0:
        problems.append("embedding.rebuild_claim_ttl_seconds must be a positive finite number")
    else:
        worst_case = _worst_case(config)
        if worst_case is not None and claim_ttl < worst_case:
            problems.append(
                "embedding.rebuild_claim_ttl_seconds must cover one worst-case embedding call "
                f"({worst_case:.0f}s)"
            )
    scan_interval = _number(config, "scan_interval_seconds")
    if scan_interval is None or not math.isfinite(scan_interval) or scan_interval <= 0:
        problems.append("embedding.scan_interval_seconds must be a positive finite number")
    return problems


def validate_embedding_config() -> None:
    """Fail fast on an unusable embedding block (ADR 0018 A9/B1); no network probe."""
    problems: list[str] = []
    config = _embedding_config()
    if not config:
        problems.append("the embedding block is missing")
    else:
        default = _default_config()
        provider = str(default.get("provider", "")).strip()
        model = str(default.get("model", "")).strip()
        if provider not in PROVIDER_NAMES or provider not in get_allowed_providers():
            problems.append(f"embedding.default.provider `{provider}` is not in providers.allowed")
        if not model:
            problems.append("embedding.default.model is empty")
        if provider == "local" and default.get("local_endpoint") not in get_local_endpoints():
            problems.append("embedding.default.local_endpoint must name a configured endpoint")
        if str(config.get("target_pipeline") or "") != NEW_PIPELINE:
            problems.append(f"embedding.target_pipeline must be `{NEW_PIPELINE}`")
        problems += _policy_problems(config)
    if problems:
        raise ValueError("saga.config.yaml (ADR 0018): " + "; ".join(problems))
