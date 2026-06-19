---
name: research
description: Research any topic for SAGA — a framework, a code pattern, a competitor's feature, a Reddit/forum feature-request, a library trade-off. Wraps the built-in deep-research engine, frames the question for SAGA, writes a cited report to scratch/research/, and returns a tight summary. PURE research — it does not decide, does not adopt findings, does not write an ADR. Use when the user says "research X", "look into X", "compare X vs Y", "what do other projects do about X".
---

# /research — investigate a topic for SAGA (pure research)

Produces evidence, not decisions. Orchestration-agnostic: works standalone (exploratory) or as a validation step before an ADR. Never adopt findings silently — surface options and divergences (CLAUDE.md principle 1).

## Steps

1. **Frame for SAGA** — take the topic from the arguments. If it's vague, ask 2-3 scoping questions before searching (which subsystem/decision does it touch? what would a useful answer let us decide? any constraints — self-hostable, cost, LangGraph/pgvector fit?). Don't assume scope.
2. **Run the engine** — invoke the built-in `deep-research` skill (via the Skill tool) with the framed question as its args. It fans out web searches, fetches sources, adversarially verifies claims, and returns a cited report. Don't reimplement this.
3. **Persist to scratch** — write the report to `scratch/research/<slug>.md` (kebab-case slug from the topic). This dir is gitignored and disposable — the durable output is a later ADR, not this file. If a related research file already exists there, extend it rather than duplicate.
   - Keep citations/links inline so claims are traceable.
   - Mark the **fragile points** explicitly (weakest assumptions, contested claims, gaps) — these are what a later decision or validation pass must scrutinize.
4. **Summarize** — return a tight summary in chat: the key findings, the trade-offs, and the fragile points. A few lines, not the whole report.

## Boundaries

- **Do not decide.** No "we should adopt X". Present the option space and the evidence.
- **Do not write an ADR** and do not prompt to derive one. When the research is decision-grade, the report in `scratch/research/<slug>.md` is ready to feed `/adr` — mention that path in one line and stop.
- For SAGA-specific competitor/repo analysis, the same scratch/research/ home and "ask before adopting" discipline apply.
