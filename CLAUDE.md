# CLAUDE.md

## What this is
An ATS resume checker for ML/DS/AI engineering roles. Free instant scoring layer + paid RAG-grounded deep report. Full spec lives in `docs/`, read it before writing code:

`product_requirements.md` → `resume_parsing_spec.md` → `job_description_analysis.md` → `gap_analysis_spec.md` → `ats_scoring_spec.md` → `data_model.md` → `technical_architecture.md`

These docs are binding. This file is not a summary of them, it's the rules that sit above them.

## Non-negotiables
<important>
1. **No metered API call (LLM or embedding) may ever be reachable from a free-tier request.** Free layer = self-hosted embeddings + deterministic lookups only. This is the whole business model. Violating it silently is the single worst mistake you can make in this repo.
2. **Never claim the score predicts interview odds.** It measures keyword/skill alignment. Nothing more, ever, in UI copy, logs, or docs.
3. **Every AI-generated explanation or rewrite must carry its retrieval grounding.** No `retrieved_context` / `grounding_examples` = treat it as a bug, not a valid output.
</important>

## Design direction
**Swiss design aesthetics, unconditionally.** Grid-based layout, strong typographic hierarchy, generous whitespace, restrained near-monochrome palette, no decorative clutter, no gradients-for-the-sake-of-it, no illustration filler. Every screen should look like it could be printed. If in doubt, remove an element rather than add one.

## Autonomy
`technical_architecture.md` §7 lists what's intentionally left open (language, framework, hosting, vector store, chunking strategy, etc.). Use your own judgment there, check current best practice rather than trusting any stale specifics in the docs. Don't ask permission for decisions in that list, decide and note why.

## Working style
- Read the relevant `docs/` file before touching a component it governs. Don't guess at the scoring formula, the taxonomy structure, or the data shapes, they're already specified.
- Write and run your own tests as you build. Don't report something as done without verifying it.
- If a Tier 1 spec is ambiguous or contradicts another, stop and flag it rather than silently picking one interpretation.
- Keep commits scoped and buildable, not one giant unreviewable drop.

<!-- maintainer note: fill in real build/test/lint commands here once the stack is chosen. this section is the highest-value part of the file once it exists, don't leave it empty for long. -->
## Commands
_TBD — populate once the tech stack is chosen in the first build session._
