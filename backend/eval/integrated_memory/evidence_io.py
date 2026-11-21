import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from eval.support.provider_trace import ProviderTrace


def provider_evidence(trace: ProviderTrace | None, seconds: float) -> dict[str, JsonValue]:
    return {
        "seconds": seconds,
        "usage": cast(JsonValue, [asdict(item) for item in trace.usage]) if trace else [],
    }


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def append_json(path: Path, value: object) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
