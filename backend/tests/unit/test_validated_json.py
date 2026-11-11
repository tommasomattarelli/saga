import pytest
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import dialect

from app.memory.document_contracts import SummaryPayload
from app.models.validated_json import ValidatedJSON


def test_json_storage_revalidates_copied_payloads() -> None:
    payload = SummaryPayload(text="A valid summary.").model_copy(update={"text": ""})
    with pytest.raises(ValidationError):
        ValidatedJSON(SummaryPayload).process_bind_param(payload, dialect())


def test_nullable_json_uses_sql_null_not_json_null() -> None:
    storage = ValidatedJSON(SummaryPayload)
    assert storage.process_bind_param(None, dialect()) is None
    assert storage.impl.none_as_null is True


def test_json_storage_round_trip_is_typed() -> None:
    storage = ValidatedJSON(SummaryPayload)
    payload = SummaryPayload(text="A valid summary.")
    assert (
        storage.process_result_value(storage.process_bind_param(payload, dialect()), dialect())
        == payload
    )
