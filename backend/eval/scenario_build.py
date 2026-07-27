"""Build a saturated-context scenario from an authored transcript.

This is the quota-free half: it instantiates the world, replays each turn's typed
updates through the REAL handlers, and emits a scenario file with the derived
world state and message history. The context fields (`global_summary`,
`summary_context`, `recalled_memories`) are left empty and the artefact is marked
`derived: false` — filling them means running the real summariser and fact
extractor, which costs provider quota and belongs to a separate `--derive` pass.

Replaying through `apply_typed_updates` rather than hand-authoring the end state
is the point: every state a fixture can encode is one the engine can actually
produce. See scenarios/README.md.

Usage:
  cd backend
  uv run python eval/scenario_build.py gold
  uv run python eval/scenario_build.py gold --variant contradiction
  uv run python eval/scenario_build.py gold --variant bloat --check-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.router import get_gameplay_config  # noqa: E402
from app.core import world_instantiation  # noqa: E402
from app.core.npc_resolver import resolve_npc  # noqa: E402
from app.core.world_loader import load_world  # noqa: E402
from app.memory.updater import _HANDLERS, apply_typed_updates  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = Path(__file__).resolve().parent / "scenarios"
TRANSCRIPTS = SCENARIOS / "transcripts"
BUILT = SCENARIOS / "built"


# --- deterministic identity -------------------------------------------------
# instantiate_world mints uuid4 per node. For a committed artefact that means a
# fresh set of ids on every rebuild and an unreadable diff, so the build seeds a
# counter instead. Fixture-only: production keeps real uuid4.
class _SeededUUID:
    def __init__(self, seed: str) -> None:
        self._seed = seed
        self._n = 0

    def __call__(self) -> str:
        self._n += 1
        return f"{self._seed}-{self._n:04d}"


# --- loading ----------------------------------------------------------------


def load_transcript(name: str, variant: str | None) -> tuple[dict, list[dict], dict]:
    base = TRANSCRIPTS / name
    meta = yaml.safe_load((base / "meta.yaml").read_text(encoding="utf-8"))

    turns: list[dict] = []
    for chunk in sorted((base / "turns").glob("*.yaml")):
        turns.extend(yaml.safe_load(chunk.read_text(encoding="utf-8")))
    turns.sort(key=lambda t: t["n"])

    build_cfg: dict = {}
    if variant:
        overlay = yaml.safe_load(
            (TRANSCRIPTS / "variants" / variant / "overlay.yaml").read_text(encoding="utf-8")
        )
        if overlay.get("base") != name:
            raise SystemExit(f"variant '{variant}' overlays '{overlay.get('base')}', not '{name}'")
        build_cfg = overlay.get("build") or {}
        replacements = {t["n"]: t for t in overlay.get("replace") or []}
        turns = [replacements.get(t["n"], t) for t in turns]

    return meta, turns, build_cfg


# --- validation -------------------------------------------------------------


def validate(meta: dict, turns: list[dict], asset: Any) -> list[str]:
    """Pre-build gate: a fixture referencing something that no longer exists would
    silently measure garbage, so a bad reference must fail loudly here."""
    errors: list[str] = []
    nodes = set(asset.nodes)
    edges = set(asset.edges)
    npc_names = {npc.name for npc in asset.npcs.values()}

    expected = list(range(1, meta["turns"] + 1))
    if [t["n"] for t in turns] != expected:
        errors.append(f"turn numbers are not 1..{meta['turns']} contiguous")

    def check_place(where: str, slug: str) -> None:
        if slug in nodes:
            return
        kind = "an edge, but positions are nodes (ADR 0008)" if slug in edges else "unknown"
        errors.append(f"{where}: place '{slug}' is {kind}")

    for turn in turns:
        at = f"turn {turn['n']}"
        if turn.get("npc") and turn["npc"]["name"] not in npc_names:
            errors.append(f"{at}: npc '{turn['npc']['name']}' is not in the world")
        for update in turn.get("updates") or []:
            if update["key"] not in _HANDLERS:
                errors.append(f"{at}: no registered handler for '{update['key']}'")
            if update["key"] == "npc_psychology" and update["target"] not in npc_names:
                errors.append(f"{at}: psychology target '{update['target']}' is not in the world")
        patch = turn.get("world_patch") or {}
        if patch.get("player_position"):
            check_place(at, patch["player_position"])
        for name, slug in (patch.get("npc_location") or {}).items():
            if name not in npc_names:
                errors.append(f"{at}: npc_location names '{name}', not in the world")
            check_place(at, slug)
        for slug in patch.get("node_status") or {}:
            check_place(at, slug)

    return errors


# --- replay -----------------------------------------------------------------


def _apply_patch(patch: dict, world_state: dict, slug_map: dict[str, str]) -> None:
    """Overlay writes that no typed handler owns (ADR 0008/0009 surfaces)."""
    if position := patch.get("player_position"):
        world_state["player_position"] = slug_map[position]

    for name, slug in (patch.get("npc_location") or {}).items():
        resolution = resolve_npc(name, world_state)
        if resolution.npc_id:
            world_state["npcs"][resolution.npc_id]["location"] = slug_map[slug]

    for slug, status in (patch.get("node_status") or {}).items():
        world_state.setdefault("node_status", {})[slug_map[slug]] = status


def replay(meta: dict, turns: list[dict], asset: Any) -> tuple[dict, dict, dict, int]:
    """Returns (world_baseline, world_state, character_data, elapsed_minutes)."""
    world_instantiation.uuid4 = _SeededUUID(meta["name"])  # type: ignore[assignment]
    baseline, world_state, quests = world_instantiation.instantiate_world(asset)
    slug_map = baseline["slug_map"]

    char_data = dict(meta["character"])
    char_data["active_quests"] = quests.get("active", [])
    world_state["player_position"] = slug_map[meta["start"]["location"]]
    world_state["time_of_day"] = meta["start"]["time_of_day"]
    world_state["weather"] = meta["start"]["weather"]

    elapsed = 0
    for turn in turns:
        world_state, char_data = apply_typed_updates(
            world_state, char_data, turn.get("updates") or []
        )
        _apply_patch(turn.get("world_patch") or {}, world_state, slug_map)
        elapsed += int(turn.get("minutes", 0))

    world_state.setdefault("clock", {})["total_minutes"] = elapsed
    return baseline, world_state, char_data, elapsed


def build_history(turns: list[dict], window: int) -> list[dict]:
    """The active window only. Older turns belong in summary_context — putting
    every raw turn here would build a prompt production never builds."""
    messages: list[dict] = []
    for turn in turns[-window:]:
        messages.append({"role": "user", "content": turn["player"]})
        content = turn["dm"]
        if npc := turn.get("npc"):
            content += f"\n\n[{npc['name']}] {npc['dialogue']}"
            if npc.get("action"):
                content += f" ({npc['action']})"
        messages.append({"role": "assistant", "content": content})
    return messages


# --- emit -------------------------------------------------------------------


def assemble(meta: dict, turns: list[dict], build_cfg: dict, variant: str | None) -> dict:
    asset = load_world(ROOT / "worlds" / meta["world"]["slug"])

    if errors := validate(meta, turns, asset):
        raise SystemExit("scenario is incoherent:\n  " + "\n  ".join(errors))

    baseline, world_state, char_data, elapsed = replay(meta, turns, asset)
    window = build_cfg.get("active_window_turns") or get_gameplay_config().context_window_turns

    return {
        "meta": {
            "name": variant or meta["name"],
            "base": meta["name"],
            "variant": variant,
            "origin": "synthetic",
            "derived": False,
            "derived_at_turn": len(turns),
            "elapsed_minutes": elapsed,
            "active_window_turns": window,
            "world": meta["world"],
            "language": meta["language"],
            "world_state_rung": world_state.get("schema_version"),
            "build": build_cfg,
        },
        # Empty until the --derive pass runs the real summariser / fact extractor.
        "context": {"global_summary": None, "summary_context": None, "recalled_memories": []},
        "fact_corpus": [],
        "canaries": meta.get("canaries", {}),
        # Per-probe stimuli, authored with the transcript so they fit the scene it
        # ends in. The checks live in eval/probes.py and never move.
        "probes": meta.get("probes", {}),
        "campaign": {
            "death_mode": "cronista",
            "character_data": char_data,
            "world_state": world_state,
            "quests": {"active": char_data.get("active_quests", [])},
        },
        "history": build_history(turns, window),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", help="transcript name, e.g. gold")
    parser.add_argument("--variant", help="overlay under transcripts/variants/")
    parser.add_argument(
        "--check-only", action="store_true", help="validate and report, write nothing"
    )
    args = parser.parse_args()

    meta, turns, build_cfg = load_transcript(args.transcript, args.variant)
    scenario = assemble(meta, turns, build_cfg, args.variant)

    name = args.variant or args.transcript
    npcs = scenario["campaign"]["world_state"].get("npcs", {})
    history_chars = sum(len(m["content"]) for m in scenario["history"])
    print(f"{name}: {len(turns)} turns, {scenario['meta']['elapsed_minutes']} game minutes")
    print(
        f"  npcs {len(npcs)}, inventory {len(scenario['campaign']['character_data'].get('inventory', []))}"
    )
    print(
        f"  active window {scenario['meta']['active_window_turns']} turns, {history_chars} chars"
    )

    if args.check_only:
        print("  check-only: coherent, nothing written")
        return

    BUILT.mkdir(parents=True, exist_ok=True)
    out = BUILT / f"{name}.yaml"
    out.write_text(
        "# GENERATED by eval/scenario_build.py — do not edit by hand.\n"
        "# context/* and fact_corpus stay empty until the --derive pass runs.\n"
        + yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    print(f"  wrote {out.relative_to(SCENARIOS.parent)}")


if __name__ == "__main__":
    main()
