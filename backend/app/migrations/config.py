"""Alembic configuration shared by startup, adoption and env.py."""

from pathlib import Path

from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_DIR = BACKEND_DIR / "alembic"
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def alembic_config(
    *,
    connection: object | None = None,
    lock_already_held: bool = False,
    configure_logger: bool = False,
) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.attributes["connection"] = connection
    config.attributes["lock_already_held"] = lock_already_held
    config.attributes["configure_logger"] = configure_logger
    return config
