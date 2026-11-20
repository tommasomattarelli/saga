from __future__ import annotations

import json
from pathlib import Path

from .plan import IntegratedPlan, _fingerprint, load_plan, validate_plan


def render_report(
    plan: IntegratedPlan,
    *,
    fingerprint_drift: bool = False,
    run_state: dict[str, object] | None = None,
    campaign_archive_present: bool = False,
) -> str:
    validate_plan(plan, check_fingerprint=False, check_embedding_policy=False)
    batches = plan.batch_count
    lines = [
        f"# Integrated memory evaluation — {plan.run_id}",
        "",
        f"Manifest seal/source: valid; implementation drift: {'yes' if fingerprint_drift else 'no'}.",
        f"Executable: {str(plan.executable).lower()} (approved: false).",
        f"Missing gates: {', '.join(plan.missing_gates) if plan.missing_gates else 'none'}.",
        "",
        "## Planned bounds",
        f"- Batches: {batches}; global updates: {plan.global_count}.",
        f"- Logical generation results: {plan.generation_baseline}; with unified sidecar: {plan.generation_with_sidecar}.",
        f"- Per-model planned generation calls (one repetition): {plan.generation_call_counts_by_model or 'no model selected'}.",
        f"- Generation request cap: {plan.generation_request_cap if plan.generation_request_cap is not None else 'unset'}.",
        f"- Per-request output cap: {plan.output_cap if plan.output_cap is not None else 'unset'}.",
        f"- Distinct embedding-content upper bound: {plan.embedding_text_upper_bound}; embedding request-attempt cap: {plan.embedding_request_cap if plan.embedding_request_cap is not None else 'unset'}; submitted-text attempt cap: {plan.embedding_text_cap if plan.embedding_text_cap is not None else 'unset'}.",
        f"- Frozen embedding retries: {plan.embedding_policy.max_retries} retries after the initial attempt; owner confirmation required at the live gate.",
        "- Failure policy: stop before job retry; no automatic retry/replay or retry-wait loop. A future retry policy requires a new manifest/run scope.",
        "- Separate per-run authorization is required; file approval is always false.",
        "- DM generation, NPC generation, recall and probes are excluded.",
        "- This report does not provide a quality acceptance verdict.",
    ]
    if run_state is not None:
        state = run_state.get("state", "unknown")
        if run_state.get("manifest_seal") != plan.seal:
            state = "evidence/manifest mismatch"
        lines.extend(
            [
                "",
                "## Saved run evidence",
                f"- Run state: {state}.",
                f"- Campaign archive present: {str(campaign_archive_present).lower()}.",
            ]
        )
    return "\n".join(lines) + "\n"


def write_report(directory: Path | str) -> Path:
    plan = load_plan(directory, check_fingerprint=False, check_embedding_policy=False)
    drift = plan.implementation_fingerprint != _fingerprint(Path(__file__).resolve().parents[2])
    run_path = Path(directory) / "run.json"
    run_state = json.loads(run_path.read_text(encoding="utf-8")) if run_path.is_file() else None
    if run_state is not None and not isinstance(run_state, dict):
        raise ValueError("saved run state must be a JSON object")
    campaign_path = Path(directory) / "campaign.json"
    campaign_archive_present = False
    if campaign_path.is_file():
        campaign_archive = json.loads(campaign_path.read_text(encoding="utf-8"))
        if not isinstance(campaign_archive, dict):
            raise ValueError("saved campaign archive must be a JSON object")
        campaign_archive_present = True
    path = Path(directory) / "report.md"
    path.write_text(
        render_report(
            plan,
            fingerprint_drift=drift,
            run_state=run_state,
            campaign_archive_present=campaign_archive_present,
        ),
        encoding="utf-8",
    )
    return path
