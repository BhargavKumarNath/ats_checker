# Data Model Specification

**Purpose:** define the shape of every structured object that moves between the components described in `resume_parsing_spec.md`, `job_description_analysis.md`, `gap_analysis_spec.md`, and `ats_scoring_spec.md`. Field names below are illustrative; exact naming is an implementation detail, but the structure and relationships are not.

---

## 1. Parsed Resume Object

Aligned to the **JSON Resume** open standard rather than a bespoke schema — a deliberate choice established in `resume_parsing_spec.md` §2, step 6. JSON Resume is an established, community-maintained, MIT-licensed standard already used across the resume-tooling ecosystem, so aligning to it means the parser's output is independently understandable and potentially interoperable with other tools, rather than a one-off format only this system understands.

```
ParsedResume {
  basics: {
    name: string
    email: string
    phone: string
    location: string
  }
  work: [
    {
      company: string
      position: string
      start_date: string (ISO-8601-like, per JSON Resume convention)
      end_date: string | "present"
      bullets: [
        {
          raw_text: string
          embedding: vector          # computed per ats_scoring_spec.md §2.1
          matched_clusters: [cluster_id]   # populated after taxonomy lookup, gap_analysis_spec.md §1
        }
      ]
    }
  ]
  education: [ { institution, degree, dates } ]
  skills: [
    {
      raw_text: string              # as it literally appears in the resume
      matched_cluster: cluster_id | null   # gap_analysis_spec.md §1
    }
  ]
  projects: [ { name, description, bullets: [...] } ]   # same bullet structure as work
}
```

**Relationship to other specs:** `bullets[].matched_clusters` is populated by the taxonomy lookup described in `ats_scoring_spec.md` §3. `bullets[].embedding` is the input to the semantic match computation in `ats_scoring_spec.md` §2.1. This object is the direct output of the pipeline in `resume_parsing_spec.md` §2.

---

## 2. Structural/Parseability Metadata Object

Separate from the resume content object above — this is metadata *about* the document's formatting, not its content, produced by `resume_parsing_spec.md` §3.

```
ParseabilityReport {
  file_format: "pdf" | "docx" | "pasted_text"
  checks: [
    {
      check_name: "multi_column_layout" | "table_detected" | "text_box_detected"
                  | "non_standard_font" | "image_based_pdf" | "inconsistent_dates"
                  | "non_standard_section_headers"
      status: "pass" | "fail"
      location: string              # e.g. "Skills section", for user-facing specificity
      platform_severity: {
        workday: "high" | "medium" | "low" | "n/a"
        greenhouse: "high" | "medium" | "low" | "n/a"
        lever: "high" | "medium" | "low" | "n/a"
        ashby: "high" | "medium" | "low" | "n/a"
      }
    }
  ]
}
```

**Why `platform_severity` is per-check rather than a single platform-wide score:** the research in `resume_parsing_spec.md` §3 establishes that different platforms fail on different formatting issues (Workday is uniquely severe on tables; other platforms are more tolerant). A flat per-platform score would lose that specificity — this structure preserves it.

---

## 3. Parsed Job Description Object

```
ParsedJobDescription {
  role_track_signal: "MLE" | "Applied Scientist" | "Data Scientist" | "ML Research"
                      | "Data Engineer" | "unclear"     # job_description_analysis.md §4
  seniority_signal: string                               # deep report only, Layer 2
  requirements: [
    {
      raw_text: string
      requirement_type: "required" | "preferred"
      embedding: vector
      matched_cluster: cluster_id | null
    }
  ]
}
```

**Relationship to other specs:** `requirements[]` is the JD-side input to the semantic match aggregation in `ats_scoring_spec.md` §2.1. `role_track_signal` feeds the taxonomy weighting table in `gap_analysis_spec.md` §3.

---

## 4. Skill Taxonomy Object

The stored form of the taxonomy defined conceptually in `gap_analysis_spec.md`.

```
SkillCluster {
  cluster_id: string
  canonical_name: string
  category: "Core ML Foundations" | "LLM / GenAI" | "Inference & Serving"
            | "MLOps & Lifecycle" | "Evaluation & Safety" | "Classical Data Science"
  surface_forms: [string]
  role_track_weight: {
    MLE: float (0-1)
    applied_scientist: float (0-1)
    data_scientist: float (0-1)
    ml_research: float (0-1)
    data_engineer: float (0-1)
  }
}
```

This is the object every taxonomy lookup in `ats_scoring_spec.md` §3 and `gap_analysis_spec.md` §1 reads against. It should be stored as a standalone, independently-editable dataset (not hardcoded inline in scoring logic), since `gap_analysis_spec.md` §4 establishes this as a living artifact expected to grow.

---

## 5. Score Output Object

The final structured result returned to the user, combining all of the above.

```
ScoreResult {
  overall_score: int (0-100)
  components: {
    semantic_match_score: int (0-100)
    taxonomy_overlap_score: int (0-100)
    parseability_score: int (0-100)
  }
  matched_skills: [
    { cluster_id, canonical_name, resume_evidence: string, jd_evidence: string }
  ]
  unmatched_required_skills: [
    { cluster_id, canonical_name, jd_evidence: string }
  ]
  parseability_issues: [ ParseabilityReport.checks entries with status = "fail" ]
  disclaimer: string   # fixed text per ats_scoring_spec.md §6 — score measures
                        # alignment, not interview odds
}
```

**This is the object that directly enables the transparency requirement running through every other spec** — `matched_skills` and `unmatched_required_skills` are what let the free layer show "actual matched and unmatched terms," per `product_requirements.md` §3, rather than an opaque single number.

---

## 6. Deep Report Object (Layer 2, Paid)

```
DeepReport {
  score_result: ScoreResult                # the free-layer result this builds on
  explanations: [
    {
      cluster_id: string
      explanation_text: string             # e.g. "matched 'LoRA' in your resume to
                                            # 'parameter-efficient fine-tuning' in the JD"
      retrieved_context: [string]          # the retrieval-corpus entries that grounded
                                            # this explanation, per ats_proposal.md §4
    }
  ]
  rewrite_suggestions: [
    {
      original_bullet: string
      suggested_rewrite: string
      readability_flag: bool               # true if this rewrite would increase keyword
                                            # density at the cost of readability —
                                            # product_requirements.md §5, item 5
      grounding_examples: [string]         # retrieved strong-bullet examples this
                                            # suggestion was grounded in, not freely generated
    }
  ]
}
```

**This object is what makes Layer 2 a RAG system rather than a generic LLM wrapper** — every `explanation_text` and `suggested_rewrite` must carry a `retrieved_context` / `grounding_examples` trail back to the retrieval corpus. An explanation or rewrite with no grounding entries should be treated as a pipeline defect, not a valid output.

---

## 7. What This Spec Deliberately Does Not Solve

- **Persistence/database schema.** This document defines the shape of data as it moves through the pipeline, not how (or whether) it's stored. Storage decisions belong in `technical_architecture.md` (a Tier 2 document, written after these Tier 1 specs are complete).
- **API request/response formats.** Also a `technical_architecture.md` concern, not a data-model concern.
