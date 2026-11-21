from collections.abc import Callable, Hashable, Mapping, Sequence
from uuid import UUID


class ExportIntegrityError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExportIntegrityError(message)


def _unique[T](rows: Sequence[T], key: Callable[[T], Hashable], label: str) -> None:
    seen: set[Hashable] = set()
    for row in rows:
        value = key(row)
        _require(value not in seen, f"Duplicate {label} in campaign archive.")
        seen.add(value)


def _ancestors(parents: Mapping[UUID, UUID | None], head: UUID | None) -> list[UUID]:
    path: list[UUID] = []
    visited: set[UUID] = set()
    while head is not None:
        _require(head in parents, "History reference is missing from the archive.")
        _require(head not in visited, "History contains a cycle.")
        visited.add(head)
        path.append(head)
        head = parents[head]
    return path


def _acyclic(parents: Mapping[UUID, UUID | None]) -> None:
    checked: set[UUID] = set()
    for node in parents:
        path: set[UUID] = set()
        current: UUID | None = node
        while current is not None and current not in checked:
            _require(current in parents, "History reference is missing from the archive.")
            _require(current not in path, "History contains a cycle.")
            path.add(current)
            current = parents[current]
        checked.update(path)
