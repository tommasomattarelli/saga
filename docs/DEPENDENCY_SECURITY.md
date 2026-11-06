# Dependency security

Reviewed **2026-11-06**, against `main` at `dae95e9`, on
`fix/security-alert-triage`. Results are point-in-time observations, not a
guarantee against future advisories. The [October review](archive/DEPENDENCY_SECURITY_2026_10_16.md)
is retained separately.

## Seven Dependabot alerts

| Alert | Package | Locked before → after | Exposure in SAGA |
|---|---|---|---|
| [197](https://github.com/tommasomattarelli/saga/security/dependabot/197) | certifi | 2026.2.25 → 2026.10.23 | Default HTTPX/Requests TLS trust for outbound AI calls, including local-only installations |
| [198](https://github.com/tommasomattarelli/saga/security/dependabot/198) | dnspython | 2.8.0 → 2.9.2 | Transitive email validator; Pydantic disables DNS deliverability checks, and no other application use was found |
| [200](https://github.com/tommasomattarelli/saga/security/dependabot/200) | langgraph | 1.2.3 → 1.2.14 | Vulnerable remote streaming is not used by SAGA's local StateGraph |
| [196](https://github.com/tommasomattarelli/saga/security/dependabot/196) | langgraph-checkpoint-postgres | 3.1.1 → 3.1.3 | Affected namespace stores are not instantiated; this is not a general PostgreSQL vulnerability |
| [202](https://github.com/tommasomattarelli/saga/security/dependabot/202) | follow-redirects | 1.16.1 → 1.16.2 | Node transport, not browser Axios; the advisory also excludes the exact Axios 1.20.0 combination |
| [201](https://github.com/tommasomattarelli/saga/security/dependabot/201) | vite | 6.4.4 → 6.4.5 | Docker publishes the dev server; denied files inside its allowed roots could be disclosed |
| [199](https://github.com/tommasomattarelli/saga/security/dependabot/199) | postcss-selector-parser | 6.1.4 → 6.1.5 | Build-time parsing of trusted frontend sources, not player-provided CSS |

The LangGraph update also locks `langgraph-sdk` 0.4.6,
`langgraph-checkpoint` 4.3.0 and the required `langchain-core` 1.4.7.
Direct LangGraph/Postgres and Vite minimum versions were raised to the patched
releases. Other dependencies were not broadly refreshed.

The independent Python audit additionally found four advisories in `pyasn1`
0.6.4, fixed together by the compatible 0.6.5 patch:
CVE-2026-119194, CVE-2026-119195, CVE-2026-119196 and CVE-2026-119197.

## Audit outcome

| Check | Result |
|---|---|
| Python audit, including development dependencies | No known vulnerabilities |
| npm audit, production dependencies only | No known vulnerabilities |
| npm audit, full lockfile | Seven moderate package entries from one remaining minimatch advisory |
| Original seven Dependabot findings | Patched versions are locked; GitHub resolves default-branch alerts after merge |

No audit exclusions, incompatible overrides or weakened dependency-review gates
were introduced. Dependency presence and application reachability are reported
separately; unreachable vulnerable packages were still patched where compatible.

### Remaining minimatch advisory

[GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249)
affects minimatch >=7,<11.0.1. TypeScript ESLint's parser installs a 10.x copy;
npm also reports its six parent packages, yielding seven entries, not seven
independent vulnerabilities. Even the reviewed upstream typescript-eslint 8.72.1
still requires minimatch `^10.2.2`; the patched major is outside that range.

The advisory requires attacker-controlled glob patterns and
`optimizationLevel >= 2`. The installed parser's
`useProgramFromProjectService.js` calls minimatch with `{ dot: true }`, leaving
the default optimization level at 1; SAGA does not enable its project service.
Lint configuration is repository-controlled, not supplied by gameplay or world
imports. No reachable runtime attack was identified through this chain.

The full audit intentionally remains nonzero. Reassess when upstream supports a
patched version or if the parser configuration/input trust changes; do not force
a cross-major override or downgrade the linter merely to clear the report.

### Earlier Tailwind findings

[Braces GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
was withdrawn on 2026-10-23 as not practically exploitable.
PostCSS selector parser received a 6.1.5 backport accepted by both Tailwind 3
and PostCSS Nested 6. Tailwind 4 is therefore not required to remediate these
findings; no React, Tailwind or Google SDK migration was performed.

## Regression evidence

- The TLS regression failed before the update because the emSign ECC G3 root was
  trusted and passes with the new CA bundle.
- The loopback-only Vite test reproduced `.env?raw` disclosure before the patch
  and now checks the deny rule with plain, raw and import queries.
- A two-server loopback test reproduced cross-realm custom-header disclosure
  before the follow-redirects patch and now verifies credential removal while
  preserving unrelated headers.
- `npm run test:security` typechecks and runs these real HTTP tests separately
  from browser-component tests; the CI frontend job runs it as well.
- Full frontend coverage remains above the original thresholds; no thresholds
  or exclusions were weakened.
- Full verification passed 1,218 backend unit tests (three Windows-only skips),
  301 PostgreSQL integration/playtest tests, 273 frontend tests and the two
  dependency HTTP regressions, plus Ruff, mypy, Vulture, ESLint, Knip and build.
- Frontend coverage: statements 92.22%, branches 86.23%, functions 91.36%,
  lines 93.28%; existing deprecation, generated-coverage lint and bundle warnings
  were not hidden or used to relax a gate.

The native installer serves a compiled SPA, not Vite. Docker remains a
development configuration using `--host` and published ports; network bindings
were not changed. Updating a checkout's lockfile does not patch already-running
installations: synchronize dependencies and restart the process, or rebuild and
recreate container environments that use the old packages. No paid AI calls or
credential rotation were performed.

## Recheck

```bash
cd backend
uv export --locked --format requirements-txt --no-hashes --no-emit-project \
  --output-file /tmp/opencode/saga-security-requirements.txt
uvx --python 3.12.14 pip-audit --disable-pip --no-deps \
  -r /tmp/opencode/saga-security-requirements.txt
cd ../frontend
bash ../scripts/with_node.sh npm audit --package-lock-only
bash ../scripts/with_node.sh npm audit --omit=dev --package-lock-only
bash ../scripts/with_node.sh npm run test:security
```

Use an existing writable temporary directory outside OpenCode; `/tmp/opencode`
is the session's scratch directory. The full npm audit currently exits nonzero
for the single minimatch advisory documented above.
