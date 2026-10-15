---
name: wrap-up
description: >-
  Close a SAGA working session — infers what was done from git, confirms with the user, then updates CHANGELOG [Unreleased], prunes completed TODO.md items, runs the full checks for both stacks, and commits the docs. The End half of the Session Protocol. Use when finishing a session, before stepping away, or when the user says "chiudiamo / wrap up / siamo a posto".
---

# $wrap-up — close the session, persist state

The End half of the Session Protocol, and the inverse of `$catchup`. **Interview first, write second** — never assume what shipped or what's next.

## Steps

1. **Infer what happened** — `git log` of commits made this session (those not on `origin/main`, plus `git status`/`git diff --stat` for uncommitted work). Build a short draft: what was done, what looks finished, what's still open.
2. **Confirm with the user** — present that draft and ask: is this what shipped? what moves into `## NOW`? what drops to the backlog? **Do not write anything until the user confirms or corrects.** Ask only the questions you actually need.
3. **Update `CHANGELOG.md`** — add the confirmed work under `[Unreleased]`: user-facing bullets in `### Highlights` with an area tag, maintenance work in `### Internal`. Follow AGENTS.md's one-sentence, approximately 30-word cap.
4. **Update `TODO.md`** — delete completed items, and move/add the agreed next items into `## NOW / prossimi`. Keep NOW tight; push the rest to the backlog sections.
5. **Verify the tree** — run the full checks for both stacks from AGENTS.md's Essential Commands, including `mypy` and `knip`; use one-shot test runs. Run additional CI checks when the changes require them. Report failures and any environment workaround explicitly; do not declare a green session while a required check fails.
6. **Commit the docs** — first **check you're not on `main`** (`git branch --show-current`); if you are, stop and branch before committing — session work lands via a feature branch + PR, never directly on `main` (AGENTS.md Session Protocol). Then stage `CHANGELOG.md` + `TODO.md` (and any other doc touched here) and commit as `docs(session): wrap-up`. Conventional Commits, no co-author/tool trailers (per AGENTS.md). Do not push — leave that to the user.

Code changes from the session should already be committed one-per-logical-change during the session; this commit is only the closing doc/state update.
