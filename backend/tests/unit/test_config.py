import pytest
from pydantic import ValidationError

from app.config import Settings


def test_dev_with_default_secrets_passes():
    s = Settings(saga_environment="dev")
    assert s.jwt_secret.startswith("change-me")
    assert s.saga_environment == "dev"


def test_test_env_with_default_secrets_passes():
    s = Settings(saga_environment="test")
    assert s.jwt_secret.startswith("change-me")


def test_prod_with_default_jwt_secret_raises():
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(saga_environment="prod")


def test_prod_with_default_encryption_key_raises():
    with pytest.raises(ValidationError, match="api_key_encryption_key"):
        Settings(
            saga_environment="prod",
            jwt_secret="a" * 64,
        )


def test_prod_with_real_secrets_passes():
    s = Settings(
        saga_environment="prod",
        jwt_secret="a" * 64,
        api_key_encryption_key="b" * 64,
    )
    assert s.saga_environment == "prod"
