"""Singleton loader for saga.config.yaml (project root)."""

import os
from functools import lru_cache
from pathlib import Path

import yaml

# Default: backend/app/config_loader.py -> parents[2] = SAGA root (local dev)
# Docker: saga.config.yaml is mounted at /app/saga.config.yaml, override via env var
_DEFAULT_PATH = Path(__file__).parents[2] / "saga.config.yaml"
_SAGA_CONFIG_PATH = Path(os.getenv("SAGA_CONFIG_PATH", str(_DEFAULT_PATH)))


@lru_cache(maxsize=1)
def load_saga_config() -> dict:
    with open(_SAGA_CONFIG_PATH) as f:
        return yaml.safe_load(f)
