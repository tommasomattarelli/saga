---
name: adr
description: Author or evolve an Architecture Decision Record for SAGA through a deep, structured interview. Use to create a new ADR, or to work on an existing WIP/Proposed one (e.g. "use /adr on 0009", "let's flesh out ADR 0010", "turn this into an ADR"). Interview-driven: the owner makes every call, the skill captures decisions, rejected alternatives, and open TODOs. Never edits an Accepted ADR — proposes a new one that supersedes it.
---

# /adr — author or evolve an Architecture Decision Record

ADRs live in `docs/adr/NNNN-kebab-title.md`. The method is a **deep interview** where the **project owner makes every decision** — the skill never decides architecture for them (CLAUDE.md principle 1). It mirrors how the real ADRs were built: structured interview → (optional) validation research → written record.

## 0. Pick the target

- **New decision** → next sequential number (scan `docs/adr/`; today the next is `0012`), kebab title.
- **Existing WIP/Proposed** (e.g. `0009`, `0010`) → **read it first**, then continue the interview from where it stands. **WIP and Proposed are editable** — refine decisions, resolve TODOs, harden direction.
- **Existing Accepted** → **STOP. Never edit an Accepted ADR.** Offer instead to write a **new ADR that supersedes it**, cross-referencing both. (Append-only — docs/README convention.)

## 1. The interview — the heart of this skill, go VERY deep

This must be **thorough — much more thorough than feels necessary.** A shallow ADR is worse than none. One decision at a time:

1. **Frame the problem first** — what exactly are we deciding, in which subsystem, what's at stake, what constraints bind it (self-hostable, BYOAK token cost, LangGraph/pgvector fit, std 14/15/19).
2. **For every decision point, loop:**
   - State the problem precisely.
   - Lay out the **realistic options** (not strawmen) with their trade-offs.
   - **The owner decides.** Never assume, never pick silently, never "fill in the obvious."
   - **Immediately capture** the chosen option **and each rejected alternative WITH the reason it lost** — the Rejected-alternatives section is built here, live.
   - Tag the outcome: **Decided** (settled), **Refined** (hardened later by research), or **TODO / Open assumption** (consciously deferred to implementation).
3. **Probe relentlessly** — don't stop at the happy path. Push on: edge cases, failure modes, interactions with *other* ADRs and subsystems, per-turn cost, config knobs that should exist (std 14), and **contradictions between decisions already taken** (the 0008 interview caught A4-vs-F4 and D2-vs-F5 conflicts — actively hunt for these and resolve them with the owner).
4. **Keep going until the decision space is genuinely exhausted.** Depth over speed. If the owner is deciding fast, slow down and surface the consequences they may not have weighed. Ask follow-ups. It is normal for a substantial ADR to take many rounds.

## 2. Validation research — only if genuinely needed

After the interview, judge whether any decision rests on a **fragile or contested assumption** (external prior art, a competitor claim, a performance assumption).
- **If yes and it matters** → offer a `/research` pass on exactly those fragile points before finalizing; fold the result back in, marking those items **Refined** and citing `scratch/research/<slug>.md`.
- **If not** → skip it and **state explicitly why** (e.g. "decisions stand on first principles and existing code; no external validation needed").

## 3. Write the record — template scaled to the decision's size

Match the existing ADRs. **Always**: `# ADR NNNN — <title>`, a header (**Status**, **Date** — today's date, **Context items / sources**), **Context** (problem + why), **Decision(s)**, **Consequences** (Positive + Trade-offs).

**For a large decision, add** (0008-style): a **Decided/Refined/TODO** legend and tags; grouped decisions (A, B, C… with per-group TODOs); a **Decided vs Open** quick index; a **Rejected alternatives** section; **Consequences / risks**; **Relationship to other ADRs**; **Notes / sources** (link `scratch/research/`).

**Status** values: **WIP** (early, little decided yet — editable), **Proposed** (direction + decisions fixed, open TODOs remain, **may still be revised** — editable), **Accepted** (final, **frozen**). Write a status line as rich as the situation warrants (see 0008).

## 4. Close out

- Cross-link `TODO.md` if the ADR opens follow-up items or moves existing ones (the TODO has ADR-follow-up sections).
- Docs-as-code: propose a commit `docs(adr): add NNNN-<slug>` (or `docs(adr): expand NNNN …`); leave the commit to the user / `/wrap-up`.
- Never edit an Accepted ADR; WIP/Proposed stay open until the owner declares them Accepted.
