# Code scanning triage

Reviewed **2026-11-06** against default-branch commit `dae95e9` and its 14 open
CodeQL `py/path-injection` results. The reviewed application files are unchanged
on `fix/security-alert-triage`; this pass adds regression evidence rather than
rewriting working guards or teaching the analyzer a blanket sanitizer.

## Scope and verdict

All 14 results are false positives for the reported HTTP-input traversal paths.
The confinement was implemented in [PR #89](https://github.com/tommasomattarelli/saga/pull/89),
including commit `ff0df61`. CodeQL's reported flows cross custom slug validators,
enumeration-only lookup and whole-payload validation without establishing a
guard bypass. Authentication alone is not the basis for dismissal.

The library root (`SAGA_HOME` or the administrator's YAML configuration) and its
filesystem are trusted. Hostile route parameters, editor JSON and uploaded ZIP
members are not. This review does not claim race-free filesystem I/O against a
local process that can mutate the library between a check and a later access.
Protecting that separate local-writer threat would require a different design.

## Guard contracts

- `_slugify` replaces every character outside `[a-z0-9]` with a dash and then
  requires a portable kebab-case slug; it cannot emit separators or dot segments.
- `world_path` validates the requested slug and returns a matching real entry
  enumerated from the library, excluding linked roots and linked manifests.
- `_validate_paths` checks the target name and every filename-bearing slug and
  node-parent value before the writer creates directories or writes any file.
- `validate_world_tree` rejects symbolic links and Windows junctions before
  loading or writing a world; it includes optional files and asset directories.
- ZIP imports validate every original member path and reject link entries before
  extraction, then validate the loaded world and root slug before placement.

## Per-alert grounds

Locations below are relative to `backend/app/` at the reviewed commit.

| Alert | Location | Specific confinement evidence |
|---|---|---|
| [2](https://github.com/tommasomattarelli/saga/security/code-scanning/2) | `core/world_loader.py:50` | YAML reads follow gated world roots and enumerated entries after tree-link rejection |
| [3](https://github.com/tommasomattarelli/saga/security/code-scanning/3) | `core/world_loader.py:103` | Collection directory is a fixed-name child of the gated root |
| [4](https://github.com/tommasomattarelli/saga/security/code-scanning/4) | `core/world_loader.py:105` | Glob enumerates that fixed collection; user strings do not become patterns |
| [5](https://github.com/tommasomattarelli/saga/security/code-scanning/5) | `core/world_loader.py:119` | Required filenames are constants joined to a gated world root |
| [6](https://github.com/tommasomattarelli/saga/security/code-scanning/6) | `core/world_loader.py:152` | `nodes` is a constant child; linked trees are rejected first |
| [7](https://github.com/tommasomattarelli/saga/security/code-scanning/7) | `core/world_loader.py:161` | `scenario.yaml` is a constant child; linked optional files are rejected |
| [8](https://github.com/tommasomattarelli/saga/security/code-scanning/8) | `services/world_service.py:131` | Existence check uses `_slugify` output, with no separator or dot segment |
| [9](https://github.com/tommasomattarelli/saga/security/code-scanning/9) | `services/world_service.py:164` | Failed-create cleanup uses the same normalized slug under the library |
| [11](https://github.com/tommasomattarelli/saga/security/code-scanning/11) | `services/world_service.py:183` | Save gates the route slug with `world_path` before constructing its temporary source directory |
| [15](https://github.com/tommasomattarelli/saga/security/code-scanning/15) | `core/world_writer.py:68` | Every directory-bearing payload slug is validated before `_dump` can run |
| [24](https://github.com/tommasomattarelli/saga/security/code-scanning/24) | `core/world_writer.py:69` | Every filename-bearing payload slug is validated before the first write |
| [17](https://github.com/tommasomattarelli/saga/security/code-scanning/17) | `core/world_writer.py:101` | Target comes from normalization or gated lookup; writer validates before `mkdir` |
| [22](https://github.com/tommasomattarelli/saga/security/code-scanning/22) | `core/world_paths.py:27` | Flagged operation is itself the link-rejection check on a gated root |
| [23](https://github.com/tommasomattarelli/saga/security/code-scanning/23) | `core/world_paths.py:29` | Recursive enumeration checks that same gated tree for forbidden links |

## Verification

Existing regressions cover traversal/absolute paths, Windows devices and streams,
every writer collection, unreachable node parents, linked roots/contents, ZIP
members and API-level writes/campaign loading. The dedicated filesystem CI matrix
runs on Linux, macOS and Windows, including native junction cases on Windows.

This pass extends coverage to:

- all loader collection directories and the optional scenario file as symlinks;
- portable ZIP root names that fail the stricter world-slug grammar;
- real authenticated API creates with path-like display names, checking both
  successful normalization and failed-validation cleanup against an outside sentinel;
- hostile save slugs, checking that outside files and the existing world remain
  unchanged before any copy/deletion path can be taken.

Local targeted verification passed **110 unit tests** with three Windows-only
skips and **8 integration tests using real PostgreSQL**. This Linux run is not
presented as a new Windows/macOS execution. Per-alert GitHub dismissal comments
reference the corresponding guard and evidence; no rule-wide exclusion is added.

## Recheck

```bash
make test-infra-up
cd backend
uv run --locked python -m pytest --noconftest -q \
  tests/unit/security/test_dependency_regressions.py \
  tests/unit/core/test_world_path_security.py \
  tests/unit/services/test_world_archive_security.py
uv run --locked python -m pytest tests/integration/test_world_path_security.py -q
```

Future changes that weaken these guards or permit remotely selected library
roots require reopening the affected verdicts, not reusing these dismissals.
