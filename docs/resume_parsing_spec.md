# Resume Parsing Specification

**Purpose:** define exactly how a raw resume file (or pasted text) becomes structured data, and how the tool detects the formatting failures that break real ATS platforms. This document is the foundation every other spec depends on — `ats_scoring_spec.md` and `gap_analysis_spec.md` both assume the structured output this document defines.

---

## 1. Supported Inputs

- Pasted plain text (primary path — required for the zero-friction free layer per `product_requirements.md` §3).
- Uploaded `.pdf` (text-layer PDF only, not scanned/image PDF).
- Uploaded `.docx`.

**Explicitly unsupported in v1:** `.pages`, `.odt`, scanned/image PDFs, `.jpg`/`.png` resumes. This is not an arbitrary limitation — current ATS-formatting research is unanimous that these formats fail parsing on most real ATS platforms too, so declining to support them here is consistent with the product's honesty positioning, not a technical shortcut. If a user uploads one, the tool should say so plainly rather than attempting a low-quality OCR pass.

---

## 2. Extraction Pipeline (Stage by Stage)

1. **Raw text extraction.** PDF via a text-layer extraction library (e.g. `pdfplumber` or `pdfminer.six`), DOCX via `python-docx`. Both are the standard, widely-used choice for this exact task in current open-source resume parsers.
2. **Structural layout detection, run before any NLP.** This stage exists specifically to power the ATS parseability sub-score (see `ats_scoring_spec.md`). Detect:
   - Multi-column layouts (text blocks with overlapping vertical ranges but distinct horizontal ranges).
   - Tables (grid structures, including tables used for layout rather than data).
   - Text boxes and floating elements.
   - Non-standard or embedded/Type-3 fonts.
   - Headers/footers containing content the parser would not read as body text.
3. **Text cleaning and normalization.** Strip layout artifacts, normalize whitespace, resolve encoding issues.
4. **Section detection.** Identify standard resume sections (Summary, Experience, Education, Skills, Projects, Certifications) via header pattern matching against a known set of standard labels, plus a fallback for near-matches (e.g., "Technical Skills" or "Core Competencies" should still resolve to the Skills section).
5. **Entity extraction within sections**, using a hybrid approach (this combination — regex for structured fields, NER for names/dates, and a phrase-matcher against a curated skill dictionary — is the standard, proven pattern used across current open-source resume parsers, not a novel technique):
   - **Regex** for structured, pattern-predictable fields: email, phone number, dates.
   - **Named entity recognition** (e.g. spaCy) for person name, organization names, and locations.
   - **Phrase/entity-ruler matching** against the ML/DS skill taxonomy (defined in `gap_analysis_spec.md`) for skill extraction — this is where the domain-specific taxonomy actually gets used, not a generic skill list.
6. **Structured output**, in a schema aligned to the JSON Resume open standard (`basics`, `work`, `education`, `skills`, `projects`) — see `data_model.md` for the full schema. Aligning to an existing open standard rather than inventing a bespoke schema means the parser output is portable and independently reasoned-about.

---

## 3. ATS Parseability Check — What to Detect and Why

This check exists because formatting failures are a well-documented, measurable cause of real rejections, independent of content quality. Current research (multiple independent 2026 sources, cross-referenced) converges on the same failure modes:

| Failure mode | Why it breaks parsing | Platform sensitivity |
|---|---|---|
| Multi-column layout | Parsers read left-to-right, top-to-bottom in a single linear stream; a two-dimensional grid gets read straight across, producing scrambled, merged text ("text-layer scrambling") | Workday fails on this most severely; Greenhouse and Lever are more tolerant but still misread column order in many cases |
| Tables (including tables used only for visual layout) | Same root cause as columns — the parser cannot resolve a 2D grid into the correct reading order | Workday fails on tables in the large majority of cases tested by independent 2026 parser audits; older legacy systems (Taleo) fail even more consistently |
| Text boxes / floating elements | Content inside a text box is often skipped entirely, not just misordered | Consistent across nearly all major platforms |
| Non-standard/decorative fonts, icons, skill-bar graphics | Parsers extract the underlying text stream; decorative or icon-based elements (common in Canva-style templates) frequently have no extractable text at all | Workday and iCIMS are flagged as particularly strict here |
| Image-based/scanned PDF | No text layer exists at all | Universal failure across every platform |
| Inconsistent date formats | ATS platforms calculate tenure by parsing dates; inconsistent formats (mixing "2024" with "March 2024" with "3/24") can miscalculate or drop experience duration | Affects date-dependent screening logic across platforms |
| Non-standard section headers | Section-detection logic in ATS platforms matches against expected labels; a creatively-named section (e.g. "My Journey" instead of "Experience") may not be recognized at all | Affects section-based filtering broadly |

**Design implication for the checker:** the free-layer parseability score should flag each of these independently and by name (e.g., "Table detected in Skills section — may not parse correctly on Workday or legacy Taleo systems") rather than collapsing them into one opaque formatting score. This transparency requirement mirrors the positioning decided in `ats_proposal.md` §4: the core competitor complaint is opaque scoring, so every sub-score in this product must be explainable in plain language.

**Platform-specific severity note for the ATS platform selector (see `product_requirements.md` §5, item 2):** current research consistently ranks Workday as the strictest parser of the major platforms, particularly on tables and multi-column layouts. Greenhouse and Lever are comparatively more forgiving of simple tables but still penalize genuine multi-column layouts. This asymmetry is the direct justification for the platform selector feature — a single generic "ATS score" is a less accurate claim than a platform-aware one, and current competitors mostly do not differentiate by platform.

---

## 4. What This Spec Deliberately Does Not Solve

- **OCR for scanned resumes.** Out of scope, per §1 — declined explicitly, not silently degraded.
- **Layout reconstruction / visual re-rendering of the resume.** This is a text-and-structure extraction pipeline, not a document viewer.
- **Training a custom NER model from scratch.** Off-the-shelf NER (e.g. spaCy's pretrained pipeline) combined with the domain-specific phrase matcher is sufficient for this use case and avoids an unnecessary training/labeling effort; a custom-trained model is a plausible future improvement, not a v1 requirement.
