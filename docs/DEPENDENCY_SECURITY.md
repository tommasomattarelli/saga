# Dependency security

Reviewed **2026-10-16**, against the reproducible-runtime baseline at `a77ac06`
(PR #90). Code checkpoint: `fb76468`, on `chore/dependency-security`.
These are point-in-time results, not a guarantee against future advisories.

## Audit outcome

| Audit | Before | After |
|---|---:|---:|
| Python packages affected, including development dependencies | 21 | 0 |
| npm affected packages, full installation | 48 | 7 |
| npm critical affected packages | 3 | 0 |
| npm affected packages with `--omit=dev` | 27 | 0 |

The seven remaining npm entries represent **two advisories**, propagated through
Tailwind 3's dependency tree, not seven independent vulnerabilities. Tools count
differently; these figures must not be added to the repository's Dependabot alert
count. GitHub's default-branch alerts update after the integration PR is merged.

No audit suppressions, dependency-review allowlists or incompatible dependency
overrides were added. The existing dependency-review high-severity gate remains.

## Remaining development-tool risks

### Braces: stack exhaustion

[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
affects Braces through 3.0.3; no patched release is available at this review.
Deeply nested brace patterns can exhaust the parser's stack and terminate the
Node.js process.

The remaining paths are Tailwind 3 → Chokidar → Braces and Tailwind 3 →
Fast-glob → Micromatch → Braces. npm consequently also flags the parent packages.

### PostCSS selector parser: CPU exhaustion

[GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf)
affects versions below 7.1.6. Crafted flat CSS selectors can cause quadratic
parsing time.

The remaining path is Tailwind 3 → PostCSS Nested 6 → PostCSS Selector Parser 6.
The fixed parser is outside the supported dependency range of this chain;
forcing a cross-major override was not accepted as a substitute for a migration.

### Exposure, mitigation and follow-up

These tools parse frontend source and build configuration. The configured
Tailwind inputs are `./index.html` and `./src/**/*.{ts,tsx}`; player actions,
world imports and authored NPC data are not supplied as CSS or glob patterns.
The accepted risk therefore concerns **untrusted source/build input**, rather
than a demonstrated attack through SAGA's gameplay API.

The frontend Docker image is still a development image and includes these tools.
The risk is **not** dismissed merely because npm labels the packages as
development dependencies.

Keep build inputs and development services restricted to trusted users, and
reassess this decision before introducing user-controlled CSS/glob compilation.
The owner accepted these two residual risks for this security pass. A dedicated
Tailwind 4 migration, followed by fresh audits and UI/build validation, remains
in `TODO.md`; it must verify removal of the vulnerable chains rather than assume
that changing the top-level major alone is sufficient.

## Compatibility boundaries

- Python 3.12.14 and Node 24.22.0 remain pinned.
- React 18, React-i18next 15, Tailwind 3 and Vite 6 remain on their existing major
  lines; Vitest and its coverage provider were migrated together to 4.1.
- The legacy icon wrapper was replaced with the same Game Icons collection
  through React Icons, removing its React 16/Webpack 4 tree.
- PyJWT replaces Python-jose; the retired ECDSA and RSA distributions and Jose
  stubs are absent from the lockfile. Pre-upgrade HS256 access/refresh tokens,
  new-token signatures, registration, login, expiry and token-type rejection
  are covered by real-PostgreSQL integration tests.
- The cryptography upgrade preserves the existing AES-256-GCM/HKDF key format;
  a ciphertext captured before the upgrade remains decryptable.
- Direct Anthropic integration and its SDK were removed with owner approval.
  Legacy `.env` keys are accepted but unused, encrypted historical keys are
  retained, and new Anthropic key updates are rejected before any other key is
  written. There is no automatic provider or credential fallback.
- OpenAI, Gemini and OpenRouter remain supported; OpenAI and Gemini SDK versions
  were not upgraded. Claude models require explicit OpenRouter configuration
  with an OpenRouter key. No paid AI requests were made.

## Verification

- [Code-checkpoint CI](https://github.com/tommasomattarelli/saga/actions/runs/38937395012):
  all checks passed, including Ruff, mypy, Vulture, TypeScript, Knip and the
  frontend coverage gate.
- Backend: 871 unit tests passed, three skipped; 67 integration/playtest tests
  passed with real PostgreSQL.
- Frontend: 220 tests passed across 41 files; lint, formatting and production
  build passed.
- Coverage: statements 91.43%, branches 85.06%, functions 90.79%, lines 92.30%.
  Original thresholds (90/82/78/90) and source exclusions were not weakened.
- Before the coverage work, Vitest 2 already failed the configured thresholds.
  Vitest 4 uses the newer AST-based V8 remapping; the added behavioral tests,
  not a threshold adjustment, made the gate pass.
- Both Docker images built. The [native installer smoke](https://github.com/tommasomattarelli/saga/actions/runs/38937392346)
  passed on Windows, Linux and macOS.

The suite still reports the pre-existing unawaited-AsyncMock warning and the
Starlette TestClient HTTPX deprecation introduced by the framework update;
neither was suppressed. The frontend bundle-size warning also remains.

## Recheck

Select the pinned Node before frontend commands. From the repository root:

```bash
cd backend
uv export --locked --format requirements-txt --no-hashes --no-emit-project \
  > /tmp/saga-requirements.txt
uvx --python 3.12.14 pip-audit --disable-pip --no-deps \
  -r /tmp/saga-requirements.txt
cd ../frontend
npm audit --package-lock-only
npm audit --omit=dev --package-lock-only
npm run test:coverage -- --run
```

The full npm audit exits nonzero for the documented residuals. Python and
runtime-only npm audits passed cleanly at the review date. Re-run all audits
before treating this snapshot as current.
