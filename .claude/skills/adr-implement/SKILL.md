---
name: adr-implement
description: Implement an already-designed ADR for SAGA — the half that starts where /adr stops. Runs the S0 pre-code design pass, sets up the sprint branch topology, drives each sprint TDD-first, and reconciles the ADR against what the code actually forced. Use when the owner says "implement ADR 0003", "let's do S2 of 0010", "start the 0012 sprints". NOT for designing: an undecided fork goes back to /adr.
---

# /adr-implement — build what an ADR decided

`/adr` ends at "propose a commit `docs(adr): add NNNN`". Everything after that lived only in
three branches of git history and nowhere in writing. This skill is that half.

The mode is the **opposite** of `/adr`: there the owner decides everything and the skill never
picks; here the skill decides constantly and writes code. The line between them is sharp — **if
you hit a genuine design fork, stop and hand it back to `/adr`**, don't resolve it in an
implementation commit.

## 0. Preconditions

- Status must be **Proposed** (design closed). **WIP** → not implementable, run `/adr` first.
  **Accepted** → already done; a change needs a superseding ADR.
- Check the ADR index for `Blocked by`. A gate that isn't met is a stop, not a warning.
- Read the ADR **in full**, not just its §7 plan — the plan omits constraints stated in the
  decisions.

## 1. S0 — the pre-code design pass

Never open an editor first. S0 is one commit and it pays for itself every time.

- **Ground the plan against live code.** The ADR was written before the code existed, so every
  "today the engine does X" in it is a *prediction*. Verify each one with grep/Read. In ADR 0003
  the plan called for rewiring an importance signal that turned out to read a key nothing ever
  writes — there was no behaviour to port, and the sprint shrank to a deletion.
- **Close the config-value TODOs.** Most Proposed ADRs defer numbers. Derive them where the ADR
  gives you the means (0003's difficulty ladder was solved backwards from three spreads §A3
  already declared verified), then put them to the owner with **AskUserQuestion** — options with
  `preview` blocks showing the actual YAML. Never invent a gameplay number silently.
- **Resize the sprints.** §7 plans are written at design time and routinely undershoot. Measure
  each sprint against the repo rule (a branch lands in six or seven commits at most) and **split
  along a seam**, not by count — 0003's S2 split into S2a (data layer, no new tool) and S2b
  (behaviour + removals). Say why in the ADR.
- **Commit**: `docs(adr): NNNN S0 design pass — <what it fixed>`, touching the ADR, `TODO.md`
  and `CHANGELOG.md` `### Internal`.

## 2. Branch topology

The convention used by 0005, 0008 and 0009 — one long-lived integration branch, one sub-branch
per sprint, **one PR at the end**:

```
main
 └── adr/NNNN-slug                     ← integration branch, off main
      ├── adr/NNNN-s1-<slug>  ──▸ merge: sprint-1 <title> (ADR NNNN)
      ├── adr/NNNN-s2-<slug>  ──▸ merge: sprint-2 <title> (ADR NNNN)
      └── …
 ◂── one PR → main (merge commit, never squash)
     then: docs(adr): flip NNNN to accepted on merge to main
```

Sprint merges are **local `--no-ff`**, no PR each. Commit subjects carry `(ADR NNNN Sn)`.
Sprints run **serially** unless two genuinely touch disjoint trees (a frontend-only sprint may
run alongside a backend one) — parallelism on a solo repo buys nothing and costs conflicts.

## 3. Per sprint

TDD first (std 1): the failing test before the implementation, integration on a real DB for core
flows (std 5/11). Then, before merging the sprint:

- **Green *and* playable.** Each sprint must leave the suite green **and the game runnable** —
  these are not the same check. ADR 0003's S1 was specified "backend, self-contained", but
  changing the dice payload broke a required Zod field in the frontend: the suite stayed green
  and the app would have rejected every turn. Grep the other stack for anything reading a
  contract you changed.
- **Run the suite repeatedly when randomness is involved.** A seeded engine hides order-dependent
  flakes. 0003's exchange test failed ~1 run in 5 because a drawn-HP mook sometimes died to the
  opening blow and so could not strike back — correct engine behaviour, wrong assumption in the
  test.
- **Don't force a cleanup commit.** If the sprint's own removals *are* the dead code, deleting
  them separately would leave the tree half-broken. Run the tools (`vulture`, `knip`), report
  honestly when they find nothing, and say where the real dead code went.

## 4. Reconcile the ADR — the step that only exists here

An ADR is a prediction about a codebase. Implementation is the only thing that tests it, and the
findings are worthless in your head: **0003 gates six other ADRs**, whose authors will read its
contracts as fact.

At the end of each sprint, run this checklist. Every one of these caught something real in 0003:

1. **Contract** — did a signature/field/shape in the ADR survive contact? (`heal(target, …)`
   could not express its own §B7b scene guard; it needed a `healer`.)
2. **False premise** — did an "already exists / already does X" claim turn out untrue? (the
   importance combat bonus reads a key nothing writes.)
3. **Vocabulary collision** — does a term mean something different in the code than in the ADR?
   (§B3 said the statblock is "mutable"; in this codebase that set means *writable by the LLM's
   `update_npc`* — the opposite of what the ADR wanted.)
4. **Missing guarantee** — did a mechanism the ADR leaned on actually provide what it assumed?
   (the 0009 F2 resolver alone can't do §B4's typo guard; it reports a misspelling exactly as it
   reports a new name.)
5. **Cross-ADR spill** — did the sprint touch a surface another ADR is gated on, or contradict
   one? Record it **there** (or in `TODO.md`), not only here.

Write the findings as a **dated implementation note** inside the ADR, next to the decision they
correct: `**Sn note (YYYY-MM-DD, implementation).** …`. State what the code forced and why —
a note records a constraint discovered, never a new decision. A design change found mid-sprint
is a `/adr` question, not a note.

Commit separately: `docs(adr): NNNN Sn note — <one line>` (precedent: `0d06660`).

## 5. Close out

- Owner playtest in a clean chat; fixes land on the integration branch.
- One PR → `main`, **merge commit** (the commit series is the point — never squash).
- `docs(adr): flip NNNN to accepted on merge to main`, and update the row in
  `docs/adr/README.md` (Status, Last movement).
- Prune the `TODO.md` items the ADR closed; leave what it opened.
