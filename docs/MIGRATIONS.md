# Database Migrations

SAGA uses Alembic for both fresh databases and upgrades. PostgreSQL 16 with
pgvector must be provisioned first; the application role needs permission to
create and alter application objects. Startup runs `alembic upgrade head` before
embedding recovery or background workers and stops on any migration error.

## Startup and online commands

An empty database is migrated automatically. A versioned database is upgraded
from its recorded revision. Startup never downgrades and refuses unknown or
newer revisions. A database with application objects but no Alembic revision is
not guessed or stamped; use one of the manual adoption profiles below.

Startup, adoption and online `alembic upgrade`, `downgrade`, `stamp` and `ensure_version` commands
share a PostgreSQL advisory lock and one explicit outer transaction. The default
wait is 30 seconds, set by `migrations.lock_timeout_seconds` in
`saga.config.yaml`. A timeout aborts the operation; it does not start the server
or retry in a loop. Direct online `stamp` is disabled; validated adoption is its
only supported use.

Offline `--sql` output is not a supported bootstrap or upgrade path. Historical
revisions include data transformations; use the online command against the
target PostgreSQL database.

## Adopt a known unversioned schema

Adoption is manual, validates the complete public application schema, and only
records a revision after an exact match. It does not repair objects, convert
JSONB data or drop anything. Extension-owned objects are excluded. Choose exactly
one profile:

```bash
cd backend
uv run --locked python -m app.migrations.adopt --profile current_post_pr1
uv run --locked python -m app.migrations.adopt --profile frozen_006
```

- `current_post_pr1` recognizes the frozen schema produced at
  `5e9206da28a0be1d8e669dcc72ed0af6a3525eac` and records revision
  `007_embedding_index`.
- `frozen_006` recognizes the frozen pre-embedding schema produced at
  `261ad5fb53003844efbe1d8097d9393469686291` and records revision
  `006_user_provider_settings`; the next startup runs 007 and 008.

Other unversioned schemas are unsupported. Back up first; a mismatch is a
refusal, not a repair plan. Inspect the reported difference and use a deliberate
forward migration or restore rather than editing the profile to fit the database.

## Destructive and irreversible boundaries

Revision 008 drops the historical `achievements` and `profile_stats` tables,
including their rows, without cascading to dependent objects. Back up data before
upgrading; an unexpected dependency makes the migration fail atomically. The
revision also refuses to invent null `memory_facts` timestamps. Downgrading 008
is intentionally unsupported because the retired rows cannot be reconstructed.

Other historical boundaries remain: 004 drops `templates`, 006 drops personal
provider settings on downgrade, and 007 drops its new embedding data on downgrade.
These downgrades are not lossless recovery; use a backup or a forward correction.

## Verification

Integration and playtest setup upgrades its isolated PostgreSQL database once
per suite and preserves `alembic_version` during per-test cleanup. Frozen schema
profiles are generated from the named Git commits using real PostgreSQL catalogs;
the tests compare the complete application schema and exercise the real revision
chain and 006-to-007 vector backfill.
