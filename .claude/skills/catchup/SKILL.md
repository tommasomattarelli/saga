---
name: catchup
description: Reconstruct SAGA session state at the start of a working session — reads CHANGELOG [Unreleased] + TODO.md ## NOW, reconciles against recent git history to surface drift, and proposes the next steps. Read-only and fast. Use at the start of a session, when returning after a break, or whenever you ask "where were we / what's next". Append `deep` to also load the README and architecture docs.
---

# /catchup — reconstruct session state

The Start half of the Session Protocol. **Read-only**: never write files, never run tests, never commit. Output is a tight briefing, not an essay.

## Steps

1. **Read what shipped** — `CHANGELOG.md`, the `[Unreleased]` section only.
2. **Read what's next** — `TODO.md`, the `## NOW / prossimi` section only (ignore the long-tail backlog below it unless nothing is in NOW).
3. **Check git reality** — `git log -15 --oneline` and `git status --short`. Note the current branch.
4. **Drift check (light)** — cross the recent commits against `[Unreleased]`:
   - commits whose work has no matching CHANGELOG entry → flag as "undocumented".
   - `## NOW` items that the commits suggest are already done → flag as "looks done, not ticked".
   - uncommitted changes in `git status` → mention them.
   Keep this to what's genuinely mismatched; if aligned, say "doc ↔ git aligned" in one line.
5. **Deep mode (only if invoked as `/catchup deep`)** — also read `README.md` and `docs/AGENTIC_ARCHITECTURE.md` for re-grounding after a long break. Skip by default — these are static and bloat the briefing.

## Output

A short briefing, in this shape:

- **Dove siamo** — 2-4 righe dal CHANGELOG `[Unreleased]` + branch corrente.
- **Drift** — solo se c'è qualcosa di disallineato (commit non documentati / item NOW già fatti / modifiche non committate). Altrimenti una riga "doc ↔ git allineati".
- **Prossimi passi** — 2-3 item dalla sezione `## NOW`, proposti da confermare. Non scegliere tu: proponi.

Stop there. Do not start working on the proposed steps — wait for the user to pick one.
