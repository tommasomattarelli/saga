from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from app.ai.embedding_config import (
    EmbeddingPolicy,
    EmbeddingSpace,
    check_space_contract,
    get_embedding_policy,
)
from app.ai.router import get_instance_default
from app.memory.batch_source_contracts import BatchInput
from app.memory.production_policy import MemoryProductionPolicy, configured_memory_policy


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class IntegratedPlan(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, arbitrary_types_allowed=True
    )
    run_id: str = Field(min_length=1)
    sources: BatchInput
    policy: MemoryProductionPolicy
    embedding_policy: EmbeddingPolicy
    language: str = "en"
    generation_model: str | None = None
    allow_paid_generation: bool = False
    generation_request_cap: int | None = None
    embedding_space: EmbeddingSpace | None = None
    embedding_request_cap: int | None = None
    embedding_text_cap: int | None = None
    unified_sidecar: bool = False
    output_cap: int
    session_scope: str
    source_hash: str
    implementation_fingerprint: str
    seal: str
    approved: Literal[False] = False
    failure_policy: Literal["stop_before_job_retry"] = "stop_before_job_retry"

    @model_validator(mode="before")
    @classmethod
    def ignore_computed_executable(cls, value: object) -> object:
        if isinstance(value, dict):
            value = dict(value)
            value.pop("executable", None)
            if isinstance(value.get("sources"), dict):
                value["sources"] = BatchInput.model_validate_json(json.dumps(value["sources"]))
            if isinstance(value.get("policy"), dict):
                value["policy"] = MemoryProductionPolicy.model_validate_json(
                    json.dumps(value["policy"])
                )
            if isinstance(value.get("embedding_policy"), dict):
                embedding = dict(value["embedding_policy"])
                embedding["retry_delays_seconds"] = tuple(embedding["retry_delays_seconds"])
                value["embedding_policy"] = EmbeddingPolicy(**embedding)
            if isinstance(value.get("embedding_space"), dict):
                value["embedding_space"] = EmbeddingSpace(**value["embedding_space"])
        return value

    @model_validator(mode="after")
    def valid_caps(self) -> IntegratedPlan:
        if self.output_cap <= 0:
            raise ValueError("output_cap must be positive")
        if any(
            value is not None and value < 0
            for value in (
                self.generation_request_cap,
                self.embedding_request_cap,
                self.embedding_text_cap,
            )
        ):
            raise ValueError("request and text caps must be nonnegative")
        return self

    @property
    def batch_count(self) -> int:
        return max((len(self.sources.turns) - self.policy.raw_turns) // self.policy.batch_turns, 0)

    @property
    def global_count(self) -> int:
        return max(self.batch_count - self.policy.intermediate_limit, 0)

    @property
    def generation_baseline(self) -> int:
        return self.batch_count * 2 + self.global_count

    @property
    def generation_with_sidecar(self) -> int:
        return self.batch_count * 3 + self.global_count

    @property
    def generation_call_counts_by_model(self) -> dict[str, int]:
        if self.generation_model is None:
            return {}
        return {
            self.generation_model: self.generation_with_sidecar
            if self.unified_sidecar
            else self.generation_baseline
        }

    @property
    def embedding_text_upper_bound(self) -> int:
        return self.batch_count * self.policy.facts.max_per_batch

    @property
    def executable(self) -> bool:
        return not self.missing_gates

    @model_serializer(mode="wrap")
    def serialize_with_executable(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        result = cast(dict[str, object], handler(self))
        result["executable"] = self.executable
        return result

    @property
    def missing_gates(self) -> list[str]:
        missing = [
            name
            for name, value in (
                ("generation_model", self.generation_model),
                ("generation_request_cap", self.generation_request_cap),
                ("embedding_space", self.embedding_space),
                ("embedding_request_cap", self.embedding_request_cap),
                ("embedding_text_cap", self.embedding_text_cap),
            )
            if value is None
        ]
        if (
            self.generation_model is not None
            and not self.generation_model.endswith(":free")
            and not self.allow_paid_generation
        ):
            missing.append("paid_generation_allowance")
        planned_generation = (
            self.generation_with_sidecar if self.unified_sidecar else self.generation_baseline
        )
        if (
            self.generation_request_cap is not None
            and self.generation_request_cap < planned_generation
        ):
            missing.append("generation_request_cap below baseline")
        if (
            self.embedding_text_cap is not None
            and self.embedding_text_cap < self.embedding_text_upper_bound
        ):
            missing.append("embedding_text_cap below distinct-content upper bound")
        return missing


def _fingerprint(root: Path) -> str:
    paths = list((root / "app").rglob("*.py")) + list((root / "eval").rglob("*.py"))
    paths += list((root / "app" / "ai" / "prompts").rglob("*.yaml"))
    paths += list((root.parent / "worlds" / "the-awakening").rglob("*.yaml"))
    paths += [
        path
        for path in (root.parent / "saga.config.yaml", root / "pyproject.toml", root / "uv.lock")
        if path.is_file()
    ]
    return _digest(
        {
            str(path.relative_to(root.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(paths))
        }
    )


def _unsigned(
    *,
    source: BatchInput,
    run_id: str,
    root: Path,
    generation_model: str | None,
    generation_request_cap: int | None,
    embedding_space: EmbeddingSpace | None,
    embedding_request_cap: int | None,
    embedding_text_cap: int | None,
    unified_sidecar: bool,
    language: str,
    allow_paid_generation: bool,
) -> IntegratedPlan:
    provisional = IntegratedPlan(
        run_id=run_id,
        sources=source,
        policy=configured_memory_policy(),
        embedding_policy=get_embedding_policy(),
        language=language,
        generation_model=generation_model,
        allow_paid_generation=allow_paid_generation,
        generation_request_cap=generation_request_cap,
        embedding_space=embedding_space,
        embedding_request_cap=embedding_request_cap,
        embedding_text_cap=embedding_text_cap,
        unified_sidecar=unified_sidecar,
        output_cap=get_instance_default().max_tokens,
        session_scope=f"integrated-memory:{run_id}",
        source_hash=source.source_hash(),
        implementation_fingerprint=_fingerprint(root),
        seal="",
    )
    seal = _plan_seal(provisional)
    return provisional.model_copy(update={"seal": seal})


def _plan_seal(plan: IntegratedPlan) -> str:
    payload = plan.model_dump(mode="json", by_alias=True)
    payload.pop("seal", None)
    payload.pop("executable", None)
    return _digest(payload)


def prepare_plan(
    *,
    sources: dict[str, object] | list[dict[str, object]] | Path | str,
    run_id: str,
    generation_model: str | None = None,
    generation_request_cap: int | None = None,
    embedding_space: EmbeddingSpace | None = None,
    embedding_request_cap: int | None = None,
    embedding_text_cap: int | None = None,
    unified_sidecar: bool = False,
    language: str = "en",
    allow_paid_generation: bool = False,
) -> IntegratedPlan:
    if not run_id.strip():
        raise ValueError("run_id must not be empty")
    if not language.strip():
        raise ValueError("language must not be empty")
    if generation_model is not None and not generation_model.strip():
        raise ValueError("generation_model must not be empty")
    if embedding_space is not None:
        check_space_contract(embedding_space)
    if isinstance(sources, (Path, str)):
        data = json.loads(Path(sources).read_text(encoding="utf-8"))
        if isinstance(data, list):
            if len(data) != 1:
                raise ValueError("integrated plan requires one canonical BatchInput")
            data = data[0]
    elif isinstance(sources, list):
        if len(sources) != 1:
            raise ValueError("integrated plan requires one canonical BatchInput")
        data = sources[0]
    else:
        data = sources
    source = BatchInput.model_validate_json(json.dumps(data))
    turns = source.turns
    policy = configured_memory_policy()
    _validate_source(source, policy.raw_turns, policy.batch_turns)
    if len(turns) < policy.raw_turns or (len(turns) - policy.raw_turns) % policy.batch_turns:
        raise ValueError("source has an incomplete raw prefix or batch tail")
    root = Path(__file__).resolve().parents[2]
    return _unsigned(
        source=source,
        run_id=run_id,
        root=root,
        generation_model=generation_model,
        generation_request_cap=generation_request_cap,
        embedding_space=embedding_space,
        embedding_request_cap=embedding_request_cap,
        embedding_text_cap=embedding_text_cap,
        unified_sidecar=unified_sidecar,
        language=language,
        allow_paid_generation=allow_paid_generation,
    )


def _validate_source(source: BatchInput, raw_turns: int, batch_turns: int) -> None:
    turns = source.turns
    if len({turn.turn_id for turn in turns}) != len(turns):
        raise ValueError("source turn IDs must be unique")
    if len({turn.reference for turn in turns}) != len(turns) or any(
        turn.reference != f"t{index}" for index, turn in enumerate(turns, 1)
    ):
        raise ValueError("source references must be unique and contiguous")
    if len(turns) < raw_turns or (len(turns) - raw_turns) % batch_turns:
        raise ValueError("source has an incomplete raw prefix or batch tail")


def validate_plan(
    plan: IntegratedPlan, *, check_fingerprint: bool = True, check_embedding_policy: bool = True
) -> None:
    if not plan.run_id.strip() or not plan.session_scope.strip() or not plan.language.strip():
        raise ValueError("run_id, session_scope, and language must not be empty")
    if plan.generation_model is not None and not plan.generation_model.strip():
        raise ValueError("generation_model must not be empty")
    _validate_source(plan.sources, plan.policy.raw_turns, plan.policy.batch_turns)
    expected_source = plan.sources.source_hash()
    if expected_source != plan.source_hash:
        raise ValueError("manifest source hash mismatch")
    seal = _plan_seal(plan)
    if plan.seal != seal:
        raise ValueError("manifest seal mismatch")
    if check_fingerprint and plan.implementation_fingerprint != _fingerprint(
        Path(__file__).resolve().parents[2]
    ):
        raise ValueError("implementation fingerprint changed")
    if check_fingerprint and plan.output_cap != get_instance_default().max_tokens:
        raise ValueError("configured generation output cap changed")
    if check_embedding_policy:
        if plan.embedding_policy != get_embedding_policy():
            raise ValueError("configured embedding policy changed")
        if plan.embedding_space is not None:
            check_space_contract(plan.embedding_space)


def write_plan(plan: IntegratedPlan, directory: Path | str) -> Path:
    validate_plan(plan)
    destination = Path(directory)
    manifest = destination / "manifest.json"
    if destination.exists() and not manifest.exists() and any(destination.iterdir()):
        raise ValueError(
            "evidence artifacts already exist without a manifest; use a new directory"
        )
    destination.mkdir(parents=True, exist_ok=True)
    path = manifest
    encoded = plan.model_dump_json(indent=2, by_alias=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError("manifest differs; use a new evidence directory")
    else:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
    return path


def load_plan(
    directory: Path | str, *, check_fingerprint: bool = True, check_embedding_policy: bool = True
) -> IntegratedPlan:
    plan = IntegratedPlan.model_validate_json(
        (Path(directory) / "manifest.json").read_text(encoding="utf-8")
    )
    validate_plan(
        plan, check_fingerprint=check_fingerprint, check_embedding_policy=check_embedding_policy
    )
    return plan
