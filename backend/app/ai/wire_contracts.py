from __future__ import annotations

from copy import copy
from types import GenericAlias
from typing import cast, get_args, get_origin

from pydantic import BaseModel, ConfigDict, create_model, field_validator
from pydantic.fields import FieldInfo

from app.ai.tools.tools_npc import UpdateNpc
from app.ai.tools.tools_world import ChangeNpcPsychology

_MAP_FIELDS: dict[type[BaseModel], frozenset[str]] = {
    UpdateNpc: frozenset({"updates"}),
    ChangeNpcPsychology: frozenset({"changes"}),
}
_WIRE_MODELS: dict[type[BaseModel], type[BaseModel]] = {}


def _entry_model(source: type[BaseModel], field_name: str) -> type[BaseModel]:
    annotation = source.model_fields[field_name].annotation
    if get_origin(annotation) is not dict:
        raise TypeError(f"{source.__name__}.{field_name} must be a dict field.")
    key_type, value_type = get_args(annotation)
    if not isinstance(key_type, type) or not isinstance(value_type, type):
        raise TypeError(f"{source.__name__}.{field_name} has unsupported map types.")

    entry = create_model(
        f"{source.__name__}{field_name.title()}Entry",
        __config__=ConfigDict(extra="forbid", strict=True),
        key=(key_type, ...),
        value=(value_type, ...),
    )
    return entry


def wire_model_for(source: type[BaseModel]) -> type[BaseModel]:
    if source not in _MAP_FIELDS:
        raise TypeError(f"No lossless wire representation is defined for {source.__name__}.")
    if source in _WIRE_MODELS:
        return _WIRE_MODELS[source]

    map_fields = _MAP_FIELDS[source]
    fields: dict[str, tuple[object, FieldInfo]] = {}
    validators = {}
    for name, source_field in source.model_fields.items():
        field_info = copy(source_field)
        if name not in map_fields:
            fields[name] = (source_field.annotation, field_info)
            continue

        entry = _entry_model(source, name)

        def reject_duplicate_keys(entries: list[BaseModel], *, key: str = name) -> list[BaseModel]:
            keys = [item.model_dump()["key"] for item in entries]
            if len(keys) != len(set(keys)):
                raise ValueError(f"Duplicate key in {key} entries.")
            return entries

        validators[f"validate_{name}_keys"] = field_validator(name)(reject_duplicate_keys)
        field_info.default = ...
        fields[name] = (GenericAlias(list, entry), field_info)

    wire = create_model(
        f"{source.__name__}Wire",
        __config__=ConfigDict(extra="forbid", strict=True),
        __validators__=validators,
        **fields,
    )  # type: ignore[call-overload]
    _WIRE_MODELS[source] = wire
    return wire


def encode_wire(value: BaseModel) -> BaseModel:
    source = type(value)
    wire_type = wire_model_for(source)
    canonical = source.model_validate(value.model_dump(), strict=True)
    data = canonical.model_dump()
    for name in _MAP_FIELDS[source]:
        data[name] = [{"key": key, "value": item} for key, item in data[name].items()]
    return wire_type.model_validate(data, strict=True)


def decode_wire(source: type[BaseModel], payload: object) -> BaseModel:
    wire = wire_model_for(source).model_validate(payload, strict=True)
    data = wire.model_dump()
    for name in _MAP_FIELDS[source]:
        entries = cast(list[dict[str, object]], data[name])
        data[name] = {entry["key"]: entry["value"] for entry in entries}
    return source.model_validate(data, strict=True)
