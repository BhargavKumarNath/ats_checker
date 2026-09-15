# ATS Scoring Specification

**Purpose:** define exactly how a resume and a job description become a single score, and every sub-score behind it. This is the document that prevents an autonomous build session from inventing an arbitrary, unexplainable formula — the core complaint against every existing competitor, per `ats_proposal.md` §4, is precisely that their scoring is opaque and doesn't correlate with real outcomes. Every decision below is made in direct response to that finding.

---

## 1. Non-Negotiable Constraint: No LLM Call in the Free-Tier Scoring Path

Per `product_requirements.md` §3, the free layer must be free to run at any volume. This rules out calling a paid LLM API (e.g. Claude, GPT) per scoring request. The entire scoring pipeline below is built from three components, none of which require a per-request paid API call:

1. Semantic embedding similarity (self-hosted model, run locally or on inexpensive commodity compute).
2. Deterministic taxonomy lookup (a lookup table, effectively free).
3. Deterministic structural/regex analysis (effectively free).

The LLM only enters the picture in the paid Layer 2 deep report, as established in `product_requirements.md` §3.

---

## 2. Component 1: Semantic Match Score

**Method:** compute sentence/document embeddings for the resume text and the job description text (or, more precisely, for individual bullet points and requirement lines — see §2.1), then compare via cosine similarity.

**Embedding model recommendation, with reasoning:** current (2026) benchmarking of open-source embedding models on the MTEB (Massive Text Embedding Benchmark) leaderboard identifies a real trade-off relevant to this product's constraints:

- **BGE-M3** — strong multilingual, hybrid dense/sparse/multi-vector retrieval in one model, but explicitly benchmarked as slower than MiniLM-class models — a real cost at free-tier volume.
- **Qwen3-Embedding** family — currently leads MTEB benchmarks for quality, but the larger variants are heavier than this product's free-tier latency and compute budget can likely absorb at scale (Layer 1 must return a result in under 3 seconds per `product_requirements.md` §6).
- **all-MiniLM-L6-v2 class models** — a compact (~22M parameter), 384-dimension architecture, benchmarked at roughly 5,000–14,000 sentences/second on CPU, 4–5x faster than larger models like all-mpnet-base-v2, explicitly positioned in current research as the choice "for teams without GPU access or applications running in resource-constrained environments."

**Recommendation for the free-tier Layer 1 path:** a MiniLM-class model (or a comparably-sized, comparably-fast successor available at implementation time — check current MTEB standings before finalizing, since this space moves quickly). The latency and CPU-only-friendly profile directly matches the free layer's constraints (§1 above, and `product_requirements.md`'s low-maintenance principle). Quality is good enough for this task, since the comparison is against a curated, domain-narrow taxonomy (`gap_analysis_spec.md`), not open-domain retrieval — the taxonomy does the precision work, the embedding model just needs to be fast and directionally correct.

**A larger model (BGE-M3 class or better) is appropriate for Layer 2**, where latency tolerance is higher (it's a paid, explicitly-requested deep report, not an instant free check) and retrieval quality against the richer RAG corpus matters more.

### 2.1 What Gets Embedded

Not the full documents as single blobs — that produces a coarse, low-information similarity score. Instead:
- Each resume bullet point / experience line is embedded individually.
- Each requirement line extracted from the job description (per `job_description_analysis.md` §4) is embedded individually.
- The semantic match score is computed as an aggregate (e.g., for each JD requirement, find the best-matching resume line by cosine similarity; average across all requirements, weighted by required vs. preferred per `job_description_analysis.md` §4).

This line-level approach is what enables the "matched and unmatched terms" transparency feature required in `product_requirements.md` §3 — a single document-level score cannot be decomposed back into which specific lines drove it.

---

## 3. Component 2: Skill Taxonomy Overlap Score

**Method:** deterministic lookup of extracted resume skills (from `resume_parsing_spec.md` §2, step 5) and extracted JD skills (from `job_description_analysis.md` §4) against the cluster structure defined in `gap_analysis_spec.md`. A match occurs when both resume and JD contain a surface form (or an embedding-similar phrase, per the fallback in `gap_analysis_spec.md` §1) mapping to the same cluster.

**Output:** percentage of JD-required and JD-preferred clusters found in the resume, weighted by the required/preferred distinction and by the role-track weighting table in `gap_analysis_spec.md` §3.

**Why this is a separate component from semantic match, not folded into it:** the taxonomy lookup is precise and explainable by cluster name ("matched: Retrieval-augmented generation"), while the embedding score is a continuous similarity number that's harder to attribute to one cause. Keeping them separate is what makes the final score decomposable and explainable — directly serving the transparency requirement established throughout this project.

---

## 4. Component 3: ATS Parseability Score

**Method:** direct output of the structural scan defined in `resume_parsing_spec.md` §3 — multi-column detection, table detection, font/encoding checks, date-format consistency, section-header recognition. Deterministic, not similarity-based.

**Output:** a checklist-style result (pass/fail per check, per platform if a platform is selected), not a single opaque number — matching the per-issue transparency requirement in `resume_parsing_spec.md` §3.

---

## 5. Combining the Three Components Into One Score

**Draft formula (to be tuned against the evaluation framework once real test data exists — do not treat these weights as final):**

```
overall_score = (0.45 × semantic_match_score)
              + (0.35 × taxonomy_overlap_score)
              + (0.20 × parseability_score)
```

**Reasoning for this weighting, stated explicitly so it can be challenged and revised:**
- Semantic match and taxonomy overlap together (0.80 combined) dominate the score, since content/skill alignment is the primary thing a JD-matching tool should measure.
- Parseability is weighted lower (0.20) but never zero — a resume with perfect content but a table-based layout genuinely will fail to parse on Workday, so it must move the score, but it should not be able to single-handedly overwhelm a strong content match.
- These weights are a starting hypothesis. Per `evaluation_framework.md` (a document not yet written, planned for after this system has working test data — see `roadmap.md`), the weighting should eventually be validated against labeled outcome data, not just decided a priori. State this plainly to end users if asked, consistent with the honesty positioning in `product_requirements.md` §6.

---

## 6. The Explicit Honesty Constraint

Per `product_requirements.md` §6 and the competitor research in `ats_proposal.md` §4: **the score must never be presented as a prediction of interview odds or hiring outcomes.** The UI copy, the scoring explanation, and any documentation must describe the score as "keyword and skill alignment with this specific job description" — nothing more. This is a direct, deliberate response to the single most damaging documented criticism of the market leader (a user scoring 98% and being rejected within an hour; another getting callbacks at scores as low as 51%, showing weak score-to-outcome correlation). Overclaiming here would reproduce the exact failure mode this product is positioned against.

---

## 7. What This Spec Deliberately Does Not Solve

- **A trained, learned scoring model** (e.g., a model trained on labeled resume/outcome pairs to predict interview likelihood). Explicitly rejected, not just deferred — see §6. This product measures alignment, not predicts outcomes, by design.
- **Real-time simulation of a specific company's actual ATS configuration.** The parseability check simulates known, documented platform-level parsing behavior (Workday, Greenhouse, etc.), not a specific employer's custom field-mapping rules, which are not observable from outside.
