from functools import cache
from pathlib import Path

import yaml

TEMPLATE_DIR = Path(__file__).with_name("templates")


@cache
def load_templates(name: str) -> dict[str, str]:
    if not name or not all(char.islower() or char == "_" for char in name):
        raise ValueError(f"Invalid template name: {name}")
    path = TEMPLATE_DIR / f"{name}.yaml"
    if not path.is_file():
        raise ValueError(f"Template file missing: {name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or not data
        or any(
            not isinstance(key, str) or not isinstance(value, str) or not value.strip()
            for key, value in data.items()
        )
    ):
        raise ValueError(f"Templates in {name} must be non-empty text.")
    return data


def template(name: str, key: str) -> str:
    values = load_templates(name)
    if key not in values:
        raise ValueError(f"Unknown template reference: {name}.{key}")
    return values[key]
