from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

T = TypeVar("T", bound=BaseModel)


class ValidatedJSON(TypeDecorator[T]):
    impl = JSONB(none_as_null=True)
    cache_ok = True

    def __init__(self, model: type[T]) -> None:
        super().__init__()
        self.model = model

    def process_bind_param(self, value: T | None, _dialect: Dialect) -> object:
        if value is None:
            return None
        payload = self.model.model_validate(value).model_dump_json(by_alias=True)
        return self.model.model_validate_json(payload).model_dump(mode="json", by_alias=True)

    def process_result_value(self, value: object, _dialect: Dialect) -> T | None:
        if value is None:
            return None
        return self.model.model_validate(value)
