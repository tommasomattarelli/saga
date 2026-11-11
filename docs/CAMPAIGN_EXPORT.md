# Campaign Export

## Download

The authenticated `GET /api/export/{campaign_id}` returns a versioned JSON archive
for the campaign owner. Another user's campaign returns `404`. No campaign import
endpoint or new save/export UI is provided by ADR 0020 S5.

All reads use a dedicated PostgreSQL `REPEATABLE READ READ ONLY` transaction,
separate from the session used for authentication. Concurrent actions, restores,
and memory publication cannot mix different database snapshots in one archive.
Export neither waits for pending generation nor starts provider calls.

## Format version 1

`format_version` identifies the archive contract; `exported_at` is the database
transaction timestamp. The runtime schema is `CampaignExport` in
`backend/app/schemas/campaign_export.py`.

| Collection | Content |
|---|---|
| `campaign` | Current world/character/quest state, world baseline, language/persona, active history/memory pointers and epoch |
| `continuations`, `turns` | All retained branches and original transcripts, linked by immutable IDs |
| `turn_operations` | Recorded operation outcomes and per-operation deltas, with turn, ordinal, step and beat |
| `saves` | All immutable saves, their state snapshots and frozen history/memory references |
| `memory_policies`, `memory_states` | Frozen production rules and retained working-state cursors |
| `memory_batches`, `batch_turns` | Batch identities, predecessors and ordered source membership |
| `memory_summaries`, `global_checkpoints` | All published documents, including inactive historical checkpoints |
| `memory_facts`, `fact_sources` | Full fact metadata, entity attribution and immutable source references |
| `generations` | Recorded producer roles, versions through jobs, actual model/provider and available usage metadata |
| `jobs`, `job_attempts` | Diagnostic provenance, source IDs/hashes, states, cumulative attempts, retry cycles and sanitized errors |

Displayed `turn_number` is not an identity: branches may reuse it and interrupted
actions may leave gaps. Use turn UUIDs, parent links and membership ordinals.
Diagnostic job states describe the exported snapshot, not commands to execute.

Credentials, authorization records, execution/claim tokens, leases, retry schedule,
full job request envelopes and provider-specific vectors are not exported. Errors
use an allowlist of safe messages; unknown persisted errors become a generic
diagnostic sentence. Narrative and authored state remain the owner's original data.

Legacy nullable provenance and summaries are preserved as recorded. An absent
operation recording remains `null`, not a fabricated empty ledger. Export does not
convert old campaigns into the new playable history contract.

## Validate offline

From `backend/`:

```bash
uv run python -m scripts.validate_campaign_export /path/to/campaign.json
```

The command validates the format and internal references across all retained
branches, not only the active path. It needs no running database, credentials or
provider access, and does not import, resume or modify a campaign. Exit status is
`0` for a valid archive and `1` for an unreadable or invalid archive.

The export endpoint uses the same validator before returning data. An inconsistent
archive fails with structured error code `campaign_export_inconsistent`, rather
than silently dropping sources or returning a partial archive. Validation checks
structural integrity, not the narrative truth or quality of generated memories.
