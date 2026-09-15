# Product Requirements — ML/DS ATS Resume Checker

**Audience note:** this document defines what to build and what NOT to build. Treat every boundary below as a hard constraint, not a suggestion. Scope creep into adjacent features (a resume builder, a job board, an application tracker) is the single biggest risk to shipping this on schedule.

---

## 1. One-Sentence Definition

A free-to-use, no-signup tool that scores how well a resume matches a job description using real semantic understanding of ML/DS/AI engineering terminology, plus an optional paid deep report that explains the score and rewrites weak sections, grounded in a retrieval corpus rather than generic LLM output.

---

## 2. Governing Constraint: The $10k Website Principles

This product must satisfy five principles established from a reference set of profitable single-page tools (10MinuteEmail.com, DisPrices.com, WeirdOrConfusing.com, HackerTyper.com, TheUselessWeb.com, DownForEveryoneOrJustMe.com — full detail in `ats_proposal.md`). Every requirement below is written to satisfy these five constraints, and any feature request that violates one of them needs explicit justification before being added:

1. **Zero friction, instant utility.** No signup, no explanation, result in under 10 seconds.
2. **Universal problem, not niche.** The base action ("check my resume against this job") must rank for broad search intent, not just an ML-specific audience.
3. **Traffic from search intent, not marketing.** The product must be built to rank for specific, high-volume queries, not to be discovered virally.
4. **Low maintenance as a consequence of narrow scope.** The free path must have near-zero marginal cost per use, no paid API calls on the free tier.
5. **Volume-based monetization on the free layer.** The free layer must work identically whether used once or a million times; per-user depth is what the paid layer sells, not the free layer.

---

## 3. Two-Layer Architecture (Requirement, Not Optional Design Choice)

### Layer 1 — Free, instant, deterministic (satisfies principles 1, 4, 5)

**Inputs:** pasted resume text (file upload as a convenience, not a requirement) and pasted job description text.

**Output, in under 3 seconds, no LLM call in this path:**
- A single overall match score (0–100).
- A semantic match sub-score (embedding similarity between resume and JD — see `ats_scoring_spec.md`).
- A skill taxonomy overlap sub-score (deterministic lookup against the ML/DS taxonomy — see `gap_analysis_spec.md`).
- An ATS parseability sub-score (structural scan for tables, columns, non-standard fonts, file format issues — see `resume_parsing_spec.md`).
- A visible list of matched and unmatched skills/keywords, in plain text, not hidden behind a paywall.

**Hard requirement:** nothing in this layer may call a paid third-party API per request. Embedding inference must run on a self-hosted or locally-run model (see `ats_scoring_spec.md` for the specific model recommendation). This is what keeps the free tier sustainable at any traffic volume — the constraint that makes principle 4 and principle 5 actually true rather than aspirational.

### Layer 2 — Paid, deep, RAG-grounded (where the actual differentiation and revenue live)

**Trigger:** an explicit user action ("Get detailed report"), never automatic.

**Output:**
- An explanation of *why* each match or gap was scored the way it was, citing the specific taxonomy equivalence used (e.g., "matched 'LoRA' in your resume to 'parameter-efficient fine-tuning' in the job description").
- Specific rewrite suggestions for weak or missing sections, grounded in retrieved example bullet phrasings from the corpus, not free-generated LLM text.
- A flag on any suggestion that would increase keyword density at the cost of readability (directly answers the "you can win the scanner and lose the recruiter" complaint documented in the competitor research).

**Pricing model requirement:** one-time fee or a small credit pack, explicitly NOT a recurring subscription. This is a direct, deliberate response to documented Trustpilot complaints about Jobscan's auto-renewal practices and its BBB C- rating — see `ats_proposal.md` §4 for the full competitor research. Trust, not just price, is the differentiator here.

---

## 4. Explicit Scope Boundaries (What NOT to Build in v1)

- **No resume builder or template generator.** This is a checker, not an authoring tool. A "download rewritten resume" feature is out of scope; a "download a diff of the specific lines flagged" feature is in scope (see §5).
- **No job search, job board, or application tracking.** Single-purpose tool per principle 1 and 3.
- **No user accounts required for the free layer.** Optional accounts may exist later for the paid layer's report history, but the free layer must work with zero account creation.
- **No support for languages other than English in v1.** The ML/DS taxonomy is English-only at launch; multilingual is a post-MVP consideration, not a v1 requirement.
- **No real-time re-scraping of live job boards.** The user pastes a job description manually; the product does not integrate with LinkedIn/Indeed APIs in v1.
- **No general-purpose (non-ML/DS) role support in v1.** The taxonomy and role-track selector are ML/DS/AI-specific by design (this is the differentiation — see `ats_proposal.md` §4 for why generic SWE checkers already exist and don't solve this). Expansion to other engineering disciplines is a post-MVP roadmap item, not a v1 requirement.

---

## 5. In-Scope Features, Priority Order

1. Core two-box (resume + JD) free scoring flow — described in §3, Layer 1.
2. ATS platform selector (Workday / Greenhouse / Lever / Ashby / generic) — surfaces platform-specific parsing warnings, since these platforms fail differently (see `resume_parsing_spec.md`).
3. Role-track selector (ML Engineer / Applied Scientist / Data Scientist / ML Research / Data Engineer) — reweights the taxonomy per track, since these roles value different vocabulary clusters (see `gap_analysis_spec.md`).
4. The paid deep report — described in §3, Layer 2.
5. Anti-keyword-stuffing flag, bundled into the deep report.
6. Multi-JD comparison — paste one resume, compare against several target postings in one session. Deferred until Layer 1 and Layer 2 are working and validated; not a launch blocker.
7. Downloadable rewrite diff (before/after of flagged lines only, not a full resume export).

---

## 6. Success Criteria

- Layer 1 returns a result in under 3 seconds for a typical two-page resume against a typical job description, with zero external paid API calls.
- The semantic matching layer correctly identifies at least the following ML/DS equivalence classes without exact string overlap: LoRA ↔ parameter-efficient fine-tuning, RAG ↔ retrieval-augmented generation ↔ vector search, PyTorch ↔ deep learning framework, quantization ↔ model compression. (Full equivalence set in `gap_analysis_spec.md`.)
- The ATS parseability check correctly flags at minimum: multi-column layouts, tables, non-standard fonts, and image-based PDFs — the four failure modes most consistently documented across current ATS-formatting research (see `resume_parsing_spec.md` for sourcing).
- The product never presents the score as a prediction of interview odds. Every score explanation must be scoped to "keyword and skill alignment," matching the honesty positioning established in `ats_proposal.md` §4 as the direct counter to Jobscan's most-repeated criticism.
