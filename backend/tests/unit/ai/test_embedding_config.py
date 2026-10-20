"""Tests for the ADR 0018 embedding policy block (saga.config.yaml)."""

from __future__ import annotations

import dataclasses
from unittest.mock import patch

import pytest

from app.ai.embedding_config import (
    LEGACY_DIMENSIONS,
    LEGACY_PIPELINE,
    NEW_PIPELINE,
    EmbeddingPolicy,
    EmbeddingRebuildConfig,
    EmbeddingSpace,
    build_space,
    check_space_contract,
    get_embedding_default_space,
    get_embedding_policy,
    get_embedding_rebuild_config,
    legacy_space,
    local_space,
    validate_embedding_config,
    worst_case_embedding_call_seconds,
)
from app.ai.router import get_allowed_providers
from app.exceptions import ValidationError


class TestEmbeddingDefaultSpace:
    def test_instance_default_is_openrouter_openai_small(self):
        space = get_embedding_default_space()
        assert space.provider == "openrouter"
        assert space.model == "openai/text-embedding-3-small"

    def test_openrouter_default_needs_only_the_openrouter_key(self):
        space = get_embedding_default_space()
        assert space.api_family == "openai"
        assert space.endpoint_name is None
        assert space.endpoint_identity == "https://openrouter.ai/api/v1"

    def test_new_spaces_are_native_and_use_the_current_pipeline(self):
        space = get_embedding_default_space()
        assert space.pipeline_version == NEW_PIPELINE == "embed-v1"
        assert space.requested_dimensions is None

    def test_native_openai_small_is_allowed_without_dimensions(self):
        space = build_space("openai", "text-embedding-3-small")
        assert space.pipeline_version == NEW_PIPELINE
        assert space.requested_dimensions is None
        with patch("app.ai.embedding_config.get_allowed_providers", lambda: ["openai"]):
            check_space_contract(space)

    def test_native_openai_small_with_explicit_dimensions_is_rejected(self):
        from dataclasses import replace

        space = replace(build_space("openai", "text-embedding-3-small"), requested_dimensions=384)
        with (
            patch("app.ai.embedding_config.get_allowed_providers", lambda: ["openai"]),
            pytest.raises(ValidationError, match="never request explicit dimensions"),
        ):
            check_space_contract(space)

    def test_api_family_must_match_the_provider(self):
        from dataclasses import replace

        allowed = ["openai", "openrouter", "google", "local"]
        with patch("app.ai.embedding_config.get_allowed_providers", lambda: allowed):
            for space in (
                replace(build_space("openai", "m"), api_family="google"),
                replace(build_space("google", "m"), api_family="openai"),
                replace(build_space("openrouter", "m"), api_family="google"),
                replace(local_space("ollama", "m"), api_family="google"),
            ):
                with pytest.raises(ValidationError, match="transport"):
                    check_space_contract(space)

    def test_default_provider_is_on_the_instance_allowlist(self):
        space = get_embedding_default_space()
        assert space.provider in get_allowed_providers()

    def test_hosted_always_carries_the_endpoint_url(self):
        assert build_space("openai", "m").endpoint_identity == "https://api.openai.com/v1"
        assert build_space("google", "m").endpoint_identity is None
        with pytest.raises(ValueError, match="base URL"):
            build_space("not-a-provider", "m")

    def test_local_space_needs_a_named_endpoint(self):
        space = local_space("ollama", "nomic-embed-text")
        assert space.endpoint_name == "ollama"
        assert space.endpoint_identity == "http://localhost:11434/v1"
        assert space.pipeline_version == NEW_PIPELINE
        with pytest.raises(ValueError, match="not configured"):
            local_space("unknown-alias", "m")


class TestLegacySpaceContract:
    def test_legacy_space_requests_exactly_384(self):
        space = legacy_space()
        assert space.pipeline_version == LEGACY_PIPELINE == "embed-v1-legacy"
        assert space.requested_dimensions == LEGACY_DIMENSIONS == 384
        assert space.provider == "openai"
        assert space.model == "text-embedding-3-small"
        check_space_contract(space)

    def test_native_profiles_never_request_dimensions(self):
        space = build_space("openrouter", "openai/text-embedding-3-small")
        assert space.requested_dimensions is None
        with patch("app.ai.embedding_config.get_allowed_providers", lambda: ["openrouter"]):
            check_space_contract(space)

    def test_legacy_label_cannot_export_384_to_other_providers(self):
        with (
            patch(
                "app.ai.embedding_config.get_allowed_providers", lambda: ["openrouter", "local"]
            ),
            pytest.raises(ValidationError, match="dimensions=384` applies only"),
        ):
            check_space_contract(build_space("openrouter", "m", pipeline_version=LEGACY_PIPELINE))

    def test_native_spaces_cannot_request_explicit_dimensions(self):
        from dataclasses import replace

        space = replace(build_space("openrouter", "m"), requested_dimensions=768)
        with (
            patch("app.ai.embedding_config.get_allowed_providers", lambda: ["openrouter"]),
            pytest.raises(ValidationError, match="Native embedding profiles never request"),
        ):
            check_space_contract(space)

    def test_unauthorized_provider_is_rejected(self):
        with (
            patch("app.ai.embedding_config.get_allowed_providers", lambda: ["google"]),
            pytest.raises(ValidationError, match="not enabled"),
        ):
            check_space_contract(build_space("openrouter", "m"))

    def test_stale_local_alias_url_is_never_authorized(self):
        space = local_space("ollama", "nomic-embed-text")
        from dataclasses import replace

        moved = replace(space, endpoint_identity="http://10.0.0.99:11434/v1")
        with pytest.raises(ValidationError, match="no longer authorized"):
            check_space_contract(moved)

    def test_removed_local_alias_is_never_authorized(self):
        space = local_space("ollama", "nomic-embed-text")
        from dataclasses import replace

        instance_alias = replace(space, endpoint_name="alias-now-removed")
        with (
            patch(
                "app.ai.embedding_config.get_local_endpoints",
                lambda: {"ollama": "http://localhost:11434/v1"},
            ),
            pytest.raises(ValidationError, match="not authorized on this instance"),
        ):
            check_space_contract(instance_alias)

    def test_unknown_pipeline_is_rejected(self):
        from dataclasses import replace

        space = replace(build_space("openrouter", "m"), pipeline_version="legacy-384")
        with (
            patch("app.ai.embedding_config.get_allowed_providers", lambda: ["openrouter"]),
            pytest.raises(ValidationError, match="Unknown embedding pipeline"),
        ):
            check_space_contract(space)


class TestEmbeddingPolicy:
    def test_owner_confirmed_pacing_values(self):
        policy = get_embedding_policy()
        assert policy.batch_size == 32
        assert policy.rebuild_min_interval_seconds == 1
        assert policy.rebuild_concurrency == 1
        assert policy.request_timeout_seconds == 30
        assert policy.max_retries == 2
        assert policy.retry_delays_seconds == (1, 3)


class TestEmbeddingRebuildConfig:
    def test_worker_reader_exposes_the_five_pacing_values(self):
        config = get_embedding_rebuild_config()
        assert isinstance(config, EmbeddingRebuildConfig)
        assert config.batch_size == 32
        assert config.rebuild_min_interval_seconds == 1
        assert config.rebuild_concurrency == 1
        assert config.rebuild_claim_ttl_seconds == 600
        assert config.scan_interval_seconds == 5

    def test_claim_ttl_covers_the_worst_case_call(self):
        # one embed_batch == one HTTP chunk: 3 timeouts of 30s + delays 1s and 3s
        assert worst_case_embedding_call_seconds() == 94
        assert get_embedding_rebuild_config().rebuild_claim_ttl_seconds > (
            worst_case_embedding_call_seconds()
        )

    def test_worst_case_repeats_the_last_delay_like_the_retry_loop(self):
        # max_retries=5 over [1,3] => delays 1,3,3,3,3 (13s), not just 4s: 180+13=193.
        block = {
            "embedding": {
                "default": {"provider": "openrouter", "model": "m"},
                "target_pipeline": "embed-v1",
                "batch_size": 32,
                "rebuild_min_interval_seconds": 1,
                "rebuild_concurrency": 1,
                "rebuild_claim_ttl_seconds": 193,
                "scan_interval_seconds": 5,
                "request_timeout_seconds": 30,
                "max_retries": 5,
                "retry_delays_seconds": [1, 3],
            }
        }
        with _with_config(block):
            assert worst_case_embedding_call_seconds() == 193
            validate_embedding_config()
        block["embedding"]["rebuild_claim_ttl_seconds"] = 190
        with _with_config(block), pytest.raises(ValueError, match="rebuild_claim_ttl_seconds"):
            validate_embedding_config()


def _with_config(config: dict):
    return patch("app.ai.embedding_config.load_saga_config", return_value=config)


class TestValidateEmbeddingConfig:
    def test_repo_config_is_valid(self):
        validate_embedding_config()

    def _block(self, **embedding_fields) -> dict:
        return {"embedding": embedding_fields}

    @pytest.mark.parametrize(
        "embedding_block,fragment",
        [
            (None, "embedding block is missing"),
            (
                {
                    "default": {"provider": "openrouter", "model": "m"},
                    "target_pipeline": "embed-v1",
                    "batch_size": 32,
                    "rebuild_min_interval_seconds": 1,
                    "rebuild_concurrency": 1,
                    "request_timeout_seconds": 30,
                    "max_retries": 2,
                },
                "retry_delays_seconds",
            ),
            ({"default": {"provider": "openrouter", "model": ""}}, "model"),
            (
                {"default": {"provider": "not-a-provider", "model": "m"}},
                "not-a-provider",
            ),
            (
                {
                    "default": {"provider": "local", "model": "m", "local_endpoint": "nope"},
                },
                "local_endpoint",
            ),
            (
                {
                    "default": {"provider": "openrouter", "model": "m"},
                    "target_pipeline": "legacy-384",
                },
                "target_pipeline",
            ),
        ],
    )
    def test_invalid_blocks_fail_fast(self, embedding_block, fragment: str):
        config = {} if embedding_block is None else {"embedding": embedding_block}
        with _with_config(config), pytest.raises(ValueError, match=fragment):
            validate_embedding_config()

    @pytest.mark.parametrize(
        "field,value",
        [
            ("batch_size", -1),
            ("rebuild_min_interval_seconds", 0.5),
            ("rebuild_concurrency", 2),
            ("request_timeout_seconds", 0),
            ("max_retries", 0.5),
            ("retry_delays_seconds", [1, 0.5]),
            ("rebuild_claim_ttl_seconds", 90),
            ("scan_interval_seconds", 0),
            ("request_timeout_seconds", float("inf")),
            ("max_retries", float("inf")),
            ("retry_delays_seconds", [1, float("nan")]),
        ],
    )
    def test_invalid_policy_values_fail_fast(self, field: str, value):
        block = {
            "default": {"provider": "openrouter", "model": "openai/text-embedding-3-small"},
            "target_pipeline": "embed-v1",
            "batch_size": 32,
            "rebuild_min_interval_seconds": 1,
            "rebuild_concurrency": 1,
            "rebuild_claim_ttl_seconds": 600,
            "scan_interval_seconds": 5,
            "request_timeout_seconds": 30,
            "max_retries": 2,
            "retry_delays_seconds": [1, 3],
        }
        block[field] = value
        config = {"embedding": block}
        with _with_config(config), pytest.raises(ValueError, match=field):
            validate_embedding_config()


def test_policy_and_space_are_frozen():
    space = get_embedding_default_space()
    policy = get_embedding_policy()
    assert isinstance(space, EmbeddingSpace)
    assert isinstance(policy, EmbeddingPolicy)
    with pytest.raises(dataclasses.FrozenInstanceError):
        space.model = "other"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.batch_size = 64  # type: ignore[misc]
