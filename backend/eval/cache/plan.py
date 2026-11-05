import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from dialogue_plan import ROOT, source_hash
from pydantic import BaseModel, ConfigDict, Field

from cache.payloads import Payload, build_payloads

MODELS = ("deepseek/deepseek-v4.1-flash-1017", "z-ai/glm-5.3-flash")
type Phase = Literal["identical", "replay"]
type Regime = Literal["per-trial", "shared"]


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int
    regime: Regime
    trial: int
    step: int
    session_id: str
    payload: Literal["A", "B"]
    body_hash: str
    request_hash: str


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    run_id: str = Field(min_length=1, max_length=64)
    phase: Phase
    model: str
    source_hash: str
    commit: str
    dirty: bool
    max_tokens: int
    payloads: dict[str, Payload]
    requests: list[Request] = Field(min_length=8, max_length=8)
    fixture: str = "debug-thornhaven / npc_speaks; fixed npc_followup actor via real tools_node"
    limitations: tuple[str, ...] = (
        "Unknown initial cache warmth; per-trial runs before shared, allowing cross-regime warming.",
        "Pausing or changing session IDs does not reset upstream prefix caches.",
        "NPC result is simulated; this measures DM reuse, not interleaved live actor requests.",
        "Output cap differs from production; generated responses never drive the replay.",
    )


async def build_plan(model: str, phase: Phase, run_id: str, max_tokens: int) -> Plan:
    if model not in MODELS or phase not in ("identical", "replay"):
        raise ValueError("Select one of the agreed models and phases.")
    payloads = await build_payloads(model, max_tokens)
    if phase == "identical":
        payloads = {"A": payloads["A"]}
    identity = digest({name: p.body() for name, p in payloads.items()})
    requests: list[Request] = []
    for regime in ("per-trial", "shared"):
        for trial in range(2):
            key = ["saga-cache", run_id, model, phase, identity, regime]
            if regime == "per-trial":
                key.append(str(trial))
            session = str(uuid5(NAMESPACE_URL, digest(key)))
            for step in range(2):
                label = "B" if phase == "replay" and step else "A"
                body = payloads[label].body()
                requests.append(
                    Request(
                        index=len(requests),
                        regime=regime,
                        trial=trial,
                        step=step,
                        session_id=session,
                        payload=label,
                        body_hash=digest(body),
                        request_hash=digest({"body": body, "headers": {"x-session-id": session}}),
                    )
                )
    probe_sources = {
        path.name: path.read_text() for path in sorted(Path(__file__).parent.glob("*.py"))
    }
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--", ".", ":!scratch"], cwd=ROOT, text=True
    ).strip()
    return Plan(
        run_id=run_id,
        phase=phase,
        model=model,
        max_tokens=max_tokens,
        payloads=payloads,
        requests=requests,
        commit=commit,
        dirty=bool(dirty),
        source_hash=digest({"tracked": source_hash(), "probe": probe_sources}),
    )


def write_plan(plan: Plan, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "manifest.json"
    if path.exists():
        if Plan.model_validate_json(path.read_text()) != plan:
            raise ValueError("Manifest changed; use a new evidence directory.")
        return
    with path.open("x") as handle:
        handle.write(plan.model_dump_json(indent=2) + "\n")
