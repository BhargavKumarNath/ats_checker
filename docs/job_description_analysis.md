# Job Description Analysis Specification

**Purpose:** define how a pasted job description is turned into the same kind of structured, comparable data that `resume_parsing_spec.md` produces from a resume, so the two can actually be compared rather than just both existing.

---

## 1. Why This Needs Its Own Spec, Not Just "Reuse the Resume Parser"

A job description is a different genre of text from a resume: it mixes required skills, "nice to have" skills, seniority signals, role-track signals, and company boilerplate in unstructured prose, with no consistent section structure to lean on the way resumes have (Experience, Education, Skills). Academic labor-market NLP research treats job-description skill extraction as its own established task, not a variant of resume parsing — this document follows that framing.

---

## 2. Grounding in an Established Skill Taxonomy Standard

Rather than inventing an ad hoc skill list, this system's taxonomy work (detailed fully in `gap_analysis_spec.md`) should be structured the way existing labor-market research structures theirs: as a hierarchical taxonomy that text spans get matched against, not a flat keyword list.

Two real-world precedents worth knowing before building this:

- **ESCO** (European Skills, Competences, Qualifications and Occupations) — a published, open, multilingual taxonomy of roughly 13,900 discrete skill concepts, structured hierarchically from broad categories down to granular, individually-matchable skills. Multiple published research systems (SkillMatch, SkillSpan, and others) use ESCO as ground truth for what counts as a "skill" versus ordinary prose.
- **O\*NET** — the U.S. Department of Labor's occupational taxonomy, structured around Detailed Work Activities, task statements, and abilities, and commonly used as the U.S.-side equivalent to ESCO in labor-market NLP research.

**Design implication:** this product does not need to adopt ESCO or O\*NET wholesale (they're general-purpose across all occupations, and this product is deliberately narrow to ML/DS/AI). But the *structure* is worth copying: a hierarchical taxonomy of skill concepts, each with multiple valid surface-form phrasings, that spans of text get matched against — this is exactly the architecture `gap_analysis_spec.md` should follow for the ML/DS-specific taxonomy, and it is a proven pattern, not a novel one.

---

## 3. How Skill Extraction From a Job Description Actually Works (Established Method)

Current labor-market NLP research converges on a two-stage approach, and this system should follow the same shape:

**Stage 1 — Skill-sentence classification.** Not every sentence in a job description names a skill; many are boilerplate ("we are an equal opportunity employer"), responsibility descriptions without a concrete skill, or company culture text. The first stage filters for sentences that plausibly contain a skill or requirement.

**Stage 2 — Semantic matching against the taxonomy.** Skill-bearing sentences are compared, via embedding cosine similarity (the same embedding approach used in `ats_scoring_spec.md` for resume-to-JD matching), against the canonical phrasings in the taxonomy. This is the same mechanism that solves the "LoRA vs. parameter-efficient fine-tuning" equivalence problem identified as the core competitive gap in `ats_proposal.md` §4 — it is not a separate technique, it is the same semantic-matching engine applied to a different input.

This two-stage shape (classify, then semantically match) is directly validated by published skill-extraction research (e.g. weak-supervision approaches using ESCO as ground truth), which found this approach outperforms simpler token-level or syntactic-pattern baselines. Build to this shape rather than a simpler literal-keyword pass — a literal pass is exactly the approach every existing ATS-checker competitor already uses and is the documented source of their biggest complaint (see `ats_proposal.md` §4).

---

## 4. Fields to Extract From a Job Description

| Field | Extraction approach | Used by |
|---|---|---|
| Required (hard) skills | Two-stage classify-and-match against the taxonomy | `ats_scoring_spec.md` — primary match input |
| Preferred / "nice to have" skills | Same as above, distinguished via a lightweight rule pass on qualifying language ("preferred," "bonus," "a plus") | `ats_scoring_spec.md` — weighted lower than required skills |
| Role track signal | Keyword and phrase pattern matching against the role-track categories defined in `gap_analysis_spec.md` (MLE / Applied Scientist / Data Scientist / ML Research / Data Engineer) | `product_requirements.md` §5, item 3 — powers the role-track selector's default/suggested value |
| Seniority signal | Pattern matching on years-of-experience phrases and title-level language (e.g. "Staff," "Senior," "II," "III") | Deep report only (Layer 2) — not required for the free-layer score |
| ATS platform hint (optional) | Not extracted from the JD text itself; this is a user-provided input via the platform selector, not inferred | `resume_parsing_spec.md` §3 |

---

## 5. What This Spec Deliberately Does Not Solve

- **Company/culture-fit inference.** Out of scope entirely — this product scores skill and keyword alignment, explicitly not "culture fit" or "will this person succeed here," consistent with the honesty positioning in `product_requirements.md` §6.
- **Salary or compensation-band extraction.** Not relevant to the scoring task.
- **Live job-board scraping or integration.** The user pastes the JD manually, as established in `product_requirements.md` §4 — this spec assumes clean pasted text as input, not a scraper.
- **Multi-JD aggregate analysis** (e.g., "what do postings for this role generally require"). This is a plausible future feature but is not required for the core matching flow and would need its own spec if pursued.
