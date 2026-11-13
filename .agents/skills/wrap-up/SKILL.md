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
4. **Update `TODO.md`** — delete completed items, never unfinished work, and move/add the agreed next items into `## NOW / prossimi`. Keep NOW tight; push the rest to the backlog sections.
5. **Verify the tree** — outside an active ADR implementation workflow, run the full checks for both stacks from AGENTS.md's Essential Commands, including `mypy` and `knip`; use one-shot test runs. In an active ADR workflow, consult its workflow controller when available and follow its pause/completion gates: a pause may preserve known red or unverified checks without forcing a full rerun or WIP commit; full checks for both stacks remain mandatory before branch completion or delivery. Report failures and unverified checks explicitly; focused green checks never mean the full tree is green.
6. **Commit the docs** — persist confirmed CHANGELOG/TODO updates for actual shipped work, but do not create a docs-only session commit when those files are already accurate and unchanged. If committing, first **check you're not on `main`** (`git branch --show-current`); if you are, stop and branch before committing — session work lands via a feature branch + PR, never directly on `main` (AGENTS.md Session Protocol). Stage the changed session docs and commit as `docs(session): wrap-up`. Conventional Commits, no co-author/tool trailers (per AGENTS.md). Do not push — leave that to the user.

For an active ADR workflow pause, the interview and confirmation step still applies. Produce only a short conversation checkpoint grounded in Git state and the controller's automatic private Git metadata; do not create Markdown review, handoff, scratch, or temporary files, and do not manually rewrite machine state. Summarize what is done, what remains, and what is red or unverified.

Code changes from the session should already be committed one-per-logical-change during the session; this commit is only the closing doc/state update.
