---
name: adr
description: Author or evolve an Architecture Decision Record for SAGA through a deep, structured interview. Use to create a new ADR, or to work on an existing WIP/Proposed one (e.g. "use /adr on 0009", "let's flesh out ADR 0010", "turn this into an ADR"). Interview-driven: the owner makes every call, the skill captures decisions, rejected alternatives, and open TODOs. Never edits an Accepted ADR — proposes a new one that supersedes it.
---

# /adr — author or evolve an Architecture Decision Record

ADRs live in `docs/adr/NNNN-kebab-title.md`. The method is a **deep interview** where the **project owner makes every decision** — the skill never decides architecture for them (CLAUDE.md principle 1). It mirrors how the real ADRs were built: structured interview → (optional) validation research → written record.

## 0. Pick the target

- **New decision** → next sequential number (scan `docs/adr/` and take the highest existing number + 1), kebab title.
- **Existing WIP/Proposed** (e.g. `0009`, `0010`) → **read it first**, then continue the interview from where it stands. **WIP and Proposed are editable** — refine decisions, resolve TODOs, harden direction.
- **Existing Accepted** → **STOP. Never edit an Accepted ADR.** Offer instead to write a **new ADR that supersedes it**, cross-referencing both. (Append-only — docs/README convention.)

## 1. The interview — the heart of this skill, go VERY deep

This must be **thorough — much more thorough than feels necessary.** A shallow ADR is worse than none: it launders an un-examined assumption into a "decision". Treat the interview as the real work; the written record is just its transcript.

### 1a. Frame the problem first

Before any option, establish: what exactly are we deciding; in which subsystem; what's at stake if we get it wrong; what binds it (self-hostable, BYOAK per-turn token cost, LangGraph/pgvector fit, std 14/15/19); and **what is explicitly out of scope** (which other ADR owns it). Decompose the decision into its **sub-questions** up front — these become the checklist you must close, so none is silently skipped.

### 1b. Per-decision loop

For every sub-question, one at a time, in order:
1. **State the problem precisely** — and why it isn't obvious.
2. **Lay out the realistic options** — 2-4 genuine candidates with their trade-offs, never strawmen. If you only see one option, say so and stress-test it rather than rubber-stamping.
3. **The owner decides.** Never assume, never pick silently, never "fill in the obvious." If the owner is unsure, give a recommendation *with* reasoning — but the call is theirs.
4. **Capture live** — the chosen option AND each rejected alternative **with the reason it lost** (this builds the Rejected-alternatives section in real time, while the reasoning is fresh).
5. **Tag the outcome** — **Decided** (settled), **Refined** (will be / was hardened by research), or **TODO / Open assumption** (consciously deferred to implementation, with a note on *what* must be resolved and *when*).

### 1c. Probe checklist — interrogate every non-trivial decision against ALL of these

Don't stop at the happy path. For each decision, actively ask:
- **Data/schema impact** — new tables, JSONB shape, migration (std 15); does it break existing saves?
- **Runtime cost** — per-turn token cost on BYOAK, latency, DB write pattern (recall 0008 C7: whole-column rewrite → TOAST write amplification). What scales badly?
- **Failure modes** — what happens on error? Fail-fast, structured errors (std 6)? Silent-corruption risk (0008 F7: silent name resolution rejected for reject-with-candidates)?
- **Config knobs (std 14)** — what tunable value must live in `saga.config.yaml`? Any open-ended loop/structure needing a hard cap (std 19)?
- **Cross-ADR / cross-decision contradictions** — does this conflict with another ADR *or with a decision already taken in this interview*? The 0008 interview caught A4-vs-F4 and D2-vs-F5 — **actively hunt for these** and resolve them with the owner, don't paper over them.
- **Grounding check — no claims from memory.** Every "X already exists / already does Y / is already handled" claim that becomes a *premise* MUST be verified with an actual grep/Read of the code first, never asserted from memory. Verify the right direction too: a *reader* of a field is not a *writer* of it, so confirm the specific path you're leaning on (the writer, the caller, the migration), not just that the field/name appears somewhere. If you can't point to it in the code, it's a TODO, not a Decided fact.
- **Reversibility** — how hard to undo later? Does it lock in a schema/dependency?
- **Testability (std 11)** — what integration test would prove this decision correct?
- **Security (std 16-18)** — if it touches auth/secrets/tokens.

### 1d. Interview discipline

- **One decision at a time. Never batch** a list of questions to "get through it faster" — batching loses the rejected-alternative reasoning.
- **If the owner decides fast, slow down.** Restate the consequence they may not have weighed, then re-confirm. A fast "sure, option B" on a load-bearing choice is a flag, not a finish.
- **Re-read periodically.** Every several decisions, re-scan the ones already taken and check the new one doesn't contradict them.
- **Distinguish Decided-now vs deferred-TODO explicitly, every time** — never let an unresolved point masquerade as decided.

### 1e. When is the interview done

Only when **every sub-question from 1a is either Decided/Refined or an explicit TODO** — no silent gaps — and the rejected alternatives + risks are captured. Depth over speed; a substantial ADR taking many rounds is normal and correct. If in doubt, it is not done — ask another question.

## 2. Validation research — only if genuinely needed

After the interview, judge whether any decision rests on a **fragile or contested assumption** (external prior art, a competitor claim, a performance assumption).
- **If yes and it matters** → offer a `/research` pass on exactly those fragile points before finalizing; fold the result back in, marking those items **Refined** and citing `scratch/research/<slug>.md`.
- **If not** → skip it and **state explicitly why** (e.g. "decisions stand on first principles and existing code; no external validation needed").

This step covers **external** fragility (prior art, competitor claims, performance assumptions). Fragile **internal** assumptions — "this code path already exists / behaves like X" — are NOT research questions: verify them inline during the interview via the 1c grounding check, not here. Step 2 passing is no excuse for an unverified internal premise.

## 3. Write the record — template scaled to the decision's size

Match the existing ADRs. **Always**: `# ADR NNNN — <title>`, a header (**Status**, **Date** — today's date, **Context items / sources**), **Context** (problem + why), **Decision(s)**, **Consequences** (Positive + Trade-offs).

**For a large decision, add** (0008-style): a **Decided/Refined/TODO** legend and tags; grouped decisions (A, B, C… with per-group TODOs); a **Decided vs Open** quick index; a **Rejected alternatives** section; **Consequences / risks**; **Relationship to other ADRs**; **Notes / sources** (link `scratch/research/`).

**Status** values: **WIP** (early, little decided yet — editable), **Proposed** (direction + decisions fixed, open TODOs remain, **may still be revised** — editable), **Accepted** (final, **frozen**). Write a status line as rich as the situation warrants (see 0008). When the interview has matured the ADR past where it stood, **confirm the status transition with the owner** (e.g. WIP→Proposed) — never bump it silently; the owner declares maturity, the skill doesn't.

## 4. Close out

- Cross-link `TODO.md` **only for near-term, actionable** follow-ups, and move/tick any existing TODO items the ADR closes. A **far-future** ADR — one gated behind a dependency (e.g. 0009 sits behind 0005) — keeps its implementation TODOs in **its own Decided-vs-Open index**, NOT in `## NOW`: don't pollute the active list with work that can't start yet. State explicitly that you left them in the ADR.
- Docs-as-code: propose a commit `docs(adr): add NNNN-<slug>` (or `docs(adr): expand NNNN …`); leave the commit to the user / `/wrap-up`.
- Never edit an Accepted ADR; WIP/Proposed stay open until the owner declares them Accepted.
