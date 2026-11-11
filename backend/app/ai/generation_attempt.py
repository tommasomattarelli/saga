from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_single_generation_attempt: ContextVar[bool] = ContextVar(
    "single_generation_attempt", default=False
)


@contextmanager
def single_generation_attempt() -> Iterator[None]:
    token: Token[bool] = _single_generation_attempt.set(True)
    try:
        yield
    finally:
        _single_generation_attempt.reset(token)


def generation_attempt_is_single() -> bool:
    return _single_generation_attempt.get()
