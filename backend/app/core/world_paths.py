import re
from pathlib import Path

from app.models.world import is_valid_slug

_WINDOWS_DEVICE = re.compile(
    r"(?:con|prn|aux|nul|conin\$|conout\$|com[1-9¹²³]|lpt[1-9¹²³])",
    re.IGNORECASE,
)


def is_portable_component(name: str) -> bool:
    return (
        bool(name)
        and name not in {".", ".."}
        and not name.endswith((".", " "))
        and not any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name)
        and _WINDOWS_DEVICE.fullmatch(name.partition(".")[0].rstrip(" ")) is None
    )


def is_world_slug(value: object) -> bool:
    return isinstance(value, str) and is_valid_slug(value) and is_portable_component(value)


def validate_world_tree(root: Path) -> None:
    if root.is_symlink() or root.is_junction():
        raise ValueError("World files must not contain symbolic links or junctions.")
    for entry in root.rglob("*"):
        if entry.is_symlink() or entry.is_junction():
            raise ValueError("World files must not contain symbolic links or junctions.")
