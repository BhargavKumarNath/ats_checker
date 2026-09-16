# Build Plan — Living Context File

**Purpose:** this is the handoff document for the build. A future session (any model) should be able to read this file alongside the Tier 1/2 specs in `docs/` and continue the build without re-deriving decisions. Read order: `CLAUDE.md` → the seven spec docs → this file → the **Status log** at the bottom.

The Tier 1/2 specs are binding. This file records (a) how they were interpreted where they were open or ambiguous, (b) the engineering decisions made in the space `technical_architecture.md` §7 leaves open, (c) the phased roadmap, and (d) per-phase status notes.

Written 2026-09-15. Decisions confirmed by the project owner on 2026-09-15 (see §4).

---

## 1. Understanding of the system

**The business model is the architecture.** Two layers, not a feature tier. Layer 1 exists to rank for search intent and run at unlimited volume for free. Layer 2 exists to make money. The only thing that keeps both true is a hard rule: **no metered call (LLM or embedding API) is reachable from a free-tier request.**

### Shared foundation (built first, read by both layers)

- **Skill taxonomy.** Hierarchical clusters (ESCO-shaped), each with surface forms, category, and per-role-track weights. Stored as a versioned dataset, never inline code. This is the project's IP and is expected to grow.
- **Parsing pipeline.** Resume (pasted text / PDF / DOCX) → a JSON-Resume-shaped `ParsedResume` plus a separate `ParseabilityReport`. JD → `ParsedJobDescription` with requirement lines tagged required/preferred and a role-track signal. Layer 2 never re-parses; it consumes Layer 1's output.
- **Self-hosted embedding inference**, CPU-friendly.

### Layer 1 (free) produces a `ScoreResult` in under 3 seconds

Three decomposable components (`ats_scoring_spec.md`):

1. **Semantic match** — line-level cosine similarity: each JD requirement finds its best-matching resume bullet; average across requirements, weighted required vs preferred.
2. **Taxonomy overlap** — deterministic cluster lookup (exact surface form, with an embedding-similarity fallback) on both sides; percentage of JD clusters found in the resume, weighted by required/preferred and by role-track weight.
3. **Parseability** — named pass/fail checks with per-platform severity, never a single opaque number.

Draft blend: `0.45 × semantic + 0.35 × taxonomy + 0.20 × parseability`. Explicitly a hypothesis, to be tuned. Every matched and unmatched skill is shown with evidence, no paywall. The score is described only as keyword and skill alignment — never interview odds.

### Layer 2 (paid) is a real RAG system

Triggered only by explicit paid action. Retrieves from a small curated corpus (taxonomy with rich phrasings, strong/weak bullet examples by category, ATS platform quirks), then generates explanations and rewrites. Every explanation carries `retrieved_context`; every rewrite carries `grounding_examples`; a `readability_flag` marks keyword stuffing. Missing grounding is a defect, not an output. One-time fee or credit pack, never a subscription.

---

## 2. Spec interpretations (ambiguities resolved, stated explicitly)

None of these block the build, but each is an interpretation rather than something the specs pin down. If a future spec revision contradicts one, the spec wins.

1. **Parseability for pasted text.** Five of the seven checks (multi-column, tables, text boxes, fonts, image-based PDF) are only detectable in PDF/DOCX. For pasted text, only `inconsistent_dates` and `non_standard_section_headers` are assessed. The others are reported as `not_assessed` (a third status alongside pass/fail), never as pass. The UI tells the user that uploading a file gives a fuller check. The 0.20 parseability weight applies over assessable checks only.
2. **Where the embedding fallback lives.** `gap_analysis_spec.md` §1 says cluster matching "feeds into the semantic score"; `ats_scoring_spec.md` §3 puts it in taxonomy overlap. Decision: it lives in **taxonomy overlap**. The semantic score stays pure line-level cosine so the two components remain independent, which is the stated reason they are separate.
3. **Role-track weights.** `gap_analysis_spec.md` §3 gives High/Medium/Low per *category*; `data_model.md` §4 wants a 0–1 float per *cluster*. Mapping: High = 1.0, Medium = 0.6, Low = 0.3, applied as cluster defaults from the category table, overridable per cluster in the YAML.
4. **Cosine → 0–100 calibration.** Raw cosine between matched lines on small models sits in a narrow band. The semantic score uses a linear rescale with a floor and ceiling (tunable constants, documented in code), tuned on fixture pairs. Not a fixed `cos × 100`.
5. **JD stage-1 "skill-sentence classification" with no LLM.** On the free path this is rule-based: bullet/list structure, requirement verbs ("experience with", "proficiency in", "familiarity with"), taxonomy surface-form hits, and exclusion of boilerplate (EEO, benefits, company blurb). A tiny self-hosted classifier over embeddings is an allowed later upgrade; it must stay self-hosted.
6. **Embeddings in data-model objects.** `data_model.md` puts `embedding: vector` inside `ParsedResume` and `ParsedJobDescription`. These fields are internal. They never appear in API responses or persisted report JSON.
7. **"generic" ATS platform.** `product_requirements.md` lists a "generic" option in the selector; `data_model.md` severity keys are workday/greenhouse/lever/ashby. "generic" = show the max severity across the four named platforms.
8. **Parseability score numeric form.** Checks are pass/fail, but the blend needs a 0–100. Score = 100 − Σ(penalty per failed check), penalty scaled by the selected platform's severity (high = 25, medium = 15, low = 5), floored at 0. Constants are tunable.

---

## 3. Engineering decisions (the space `technical_architecture.md` §7 leaves open)

| Area | Decision | Why |
|---|---|---|
| Language / tooling | Python 3.12, `uv` for env and lockfile, `ruff` lint+format, `pytest`, `mypy` (strict on `core`) | Every required library (spaCy, sentence-transformers, pdfplumber, python-docx) is Python-native. A second language buys nothing. |
| Backend | FastAPI. One deployable at launch. Three packages under `src/atsc/`: `core` (foundation), `free` (Layer 1), `deep` (Layer 2). | Async, Pydantic models map 1:1 to `data_model.md`, trivially containerised. |
| Cost-boundary enforcement (three independent guards) | (1) `import-linter` contract: `core` and `free` may never import `anthropic`, `httpx`-to-metered clients, or `atsc.deep`. (2) A CI test walks the import graph of the free endpoint and asserts no metered client is reachable. (3) The Layer 1 web process runs with no `ANTHROPIC_API_KEY` in its environment; Layer 2 generation runs in a separate worker process. Additionally, the Layer 1 e2e test blocks network sockets. | Makes `technical_architecture.md` §6 structural, not a convention. |
| Frontend | Server-rendered Jinja2 + htmx, hand-written CSS, no JS framework, no build step. **Confirmed by owner 2026-09-15.** | Two textareas and a result panel. SEO landing pages per role and per platform need crawlable HTML. Lowest-maintenance surface possible (principle 4). |
| Layer 1 embedding model | `BAAI/bge-small-en-v1.5` (33M params, 384-dim) via ONNX Runtime, int8-quantised. **To be benchmarked in Phase 3** against `all-MiniLM-L6-v2` and `ibm-granite/granite-embedding-small-english-r2` on real-length resume/JD inputs on CPU before locking in. | Current (Sept 2026) MTEB standings: MiniLM-class models are the only ones that fit a 3s CPU budget. bge-small beats MiniLM on retrieval at similar speed. Quality comes from the taxonomy, not the model. |
| Layer 2 embedding model | `Qwen/Qwen3-Embedding-0.6B`; fallback `BAAI/bge-m3`. | Strongest sub-1GB open model at time of writing. Latency tolerance is high; corpus is small. |
| Taxonomy storage | YAML, one file per category, in `taxonomy/`. Validated by Pydantic at load. Compiled at startup into a spaCy `PhraseMatcher` plus a precomputed surface-form embedding matrix. | Human-editable, diffable, reviewable in PRs. Growing it is a data change, not a code change. |
| Layer 2 vector store | **No vector database.** Corpus embeddings shipped as a `.npy` matrix + JSON chunk metadata, loaded in-process. Hybrid retrieval: BM25 (`rank_bm25`) + dense, fused by reciprocal rank fusion. Contextual prefix prepended to each chunk before embedding. | Corpus will be hundreds to low thousands of chunks. A vector DB is operational weight for zero benefit at that size. Re-evaluate above ~50k chunks. |
| Reranker | None at launch. Evaluated in Phase 8 against a small labelled retrieval set. | Spec says evaluate rather than assume. |
| Runtime LLM (Layer 2) | **`claude-sonnet-5` by default. Confirmed by owner 2026-09-15.** Configurable via `ATSC_DEEP_LLM_MODEL` env var (settings object), never hardcoded. Official `anthropic` Python SDK, adaptive thinking, structured output (`output_config.format`) into the `DeepReport` schema so grounding fields are schema-required, streaming, server-side refusal fallbacks enabled. | Cost per report matters more than marginal quality for a structured, schema-constrained generation task. Structured output makes "no grounding" impossible to emit rather than something to catch after. |
| Generation pattern | Single-shot retrieve-then-generate, one call per report section (explanations; rewrites). | Queries are structured, not open-ended. Agentic retrieval is a later upgrade only if the retrieval eval shows gaps. |
| Payments and identity | Stripe Checkout, one-time payment. No accounts. Webhook mints a report token; report lives at a signed URL, also emailed. | Matches the no-subscription, no-signup positioning. |
| Persistence | Layer 1: none (stateless). Layer 2: Postgres (managed, e.g. Neon) for purchases, jobs, report output. SQLite for local dev/tests via SQLAlchemy. | Report generation takes tens of seconds → needs a job table and a worker. SQLite breaks with two instances. |
| Hosting | Docker image on Fly.io, one always-on shared-CPU machine, autoscale on load. Portable to Cloud Run unchanged. | Cold-starting spaCy + an embedding model blows the 3s budget, so true scale-to-zero is wrong here. One warm machine is ~$5–7/month. |
| Visual design | **Swiss, unconditionally.** 12-column grid, 8px baseline. Self-hosted Inter (tabular numerals) for UI, IBM Plex Mono for quoted evidence. Palette: near-black `#111` on off-white paper `#F5F4F0`, one grey scale, a single red `#E30613` used only for failed checks, unmatched required skills, and the paid CTA. Score is a large numeral — no gauge, no ring, no progress bar. Hairline-ruled tables for matched/unmatched lists. No icons, gradients, shadows, or illustration. Print stylesheet ships with v1. | Every result should read like a typeset audit sheet. Fits the transparency positioning. If in doubt, remove. |

### Repository layout (target)

```
ats_checker/
  CLAUDE.md
  docs/                      # specs + this file
  taxonomy/                  # YAML skill clusters, one file per category
  corpus/                    # Layer 2 retrieval corpus (curated, versioned)
  src/atsc/
    core/                    # shared foundation: taxonomy, parsing, embeddings, models
    free/                    # Layer 1 scoring service + routes
    deep/                    # Layer 2 retrieval, generation, payments, worker
    web/                     # FastAPI app factory, templates, static
  tests/
    fixtures/                # generated resumes/JDs (PDF, DOCX, text)
  scripts/                   # benchmarks, corpus build, fixture generation
  Dockerfile
  pyproject.toml
```

---

## 4. Owner decisions on record

- **2026-09-15** — Frontend: server-rendered HTML + htmx, no JS framework.
- **2026-09-15** — Layer 2 runtime LLM: `claude-sonnet-5` default, configurable via env/config, not hardcoded.
- **2026-09-15** — Git: commit and push to `origin` (`https://github.com/BhargavKumarNath/ats_checker.git`, branch `main`) at the end of every roadmap phase once that phase's tests pass, with a descriptive message referencing the phase. This authorisation is scoped to phase-end commits in the build sessions that follow this plan.
- **2026-09-15** — Proceed autonomously through the roadmap; stop only for genuine spec ambiguities, not routine implementation choices.

---

## 5. Roadmap

Each phase ends with its own tests passing, a status note appended to §6, and a commit + push.

1. **Scaffold.** Repo layout, `pyproject.toml`, `uv.lock`, ruff/mypy/pytest config, Dockerfile, `import-linter` cost-boundary contract, GitHub Actions CI, settings module (incl. `ATSC_DEEP_LLM_MODEL`). Populate the Commands section of `CLAUDE.md`.
2. **Taxonomy dataset and matcher.** Seed YAML from `gap_analysis_spec.md` §2. Loader + Pydantic validation, exact surface-form matcher, embedding-similarity fallback. Golden tests for the four required equivalence classes (LoRA↔PEFT, RAG↔vector search, PyTorch↔deep learning framework, quantization↔model compression).
3. **Embedding service.** Benchmark the three candidate models on CPU with real-length inputs; lock one in and record the numbers here. Latency test asserts a full two-page resume + JD embeds inside budget.
4. **Resume parsing.** Text path first: cleaning, section detection, regex + spaCy entities, taxonomy skill extraction. Then PDF/DOCX extraction with the structural checks. Fixtures generated programmatically (tables, two columns, text boxes, decorative fonts, image-only PDF, inconsistent dates, creative headers). One test per failure mode.
5. **JD analysis.** Rule-based requirement-line extraction, required/preferred tagging, role-track and seniority signals.
6. **Scoring engine.** Three components, blend, `ScoreResult` with evidence and fixed disclaimer. E2E test: fixture pair scores in < 3 s with zero network calls (socket-blocking fixture).
7. **Web layer.** Two-box page, result panel, platform + role-track selectors, per-role and per-platform landing pages, disclaimer copy. Swiss design system. Deploy Layer 1 to Fly. **Shippable free product.**
8. **Layer 2 corpus and retrieval.** Curate example bullets and platform quirks, chunk with contextual prefixes, embed, hybrid retrieval. Small labelled retrieval eval; decide on reranker from the numbers.
9. **Layer 2 generation.** Claude (configurable model) with structured output into `DeepReport`, grounding enforced by schema, readability flag via a deterministic readability metric, rewrite diff download.
10. **Payments and delivery.** Stripe Checkout, webhook, job worker, report page, email link.
11. **Deferred.** Multi-JD comparison; taxonomy growth loop from unmatched-term logs.
12. **Public launch readiness.** README, license, in-process rate limit on `/score`, retention job for `report_jobs`. Closes the code-side items of the §7 checklist; deployment and secrets stay owner actions.

---

## 6. Status log

Append one entry per completed phase: what was built, what's left, anything decided that wasn't in the original docs.

### Phase 1 — Scaffold (complete, 2026-09-15)

**Built:** `pyproject.toml` (uv, hatchling, ruff, mypy strict, pytest), `uv.lock`, package skeleton `src/atsc/{core,free,deep,web}`, `atsc.config.Settings` (env prefix `ATSC_`, `deep_llm_model` defaulting to `claude-sonnet-5`), `atsc.web.app.create_app()` with `/healthz`, multi-stage `Dockerfile` (verified: builds and serves), GitHub Actions CI (ruff, format, mypy, lint-imports, pytest), `.env.example`, `.gitignore`. `CLAUDE.md` Commands section populated.

**Cost boundary guards in place:** (1) import-linter contracts in `pyproject.toml`: `core/free/web` may not import `anthropic`, `atsc.deep.generation`, `atsc.deep.worker`; `core` may not import any layer. Verified the contract fires on a planted violation. (2) `tests/test_cost_boundary.py` imports the web app in a fresh interpreter and asserts no metered module is in `sys.modules`. (3) Documented: web process runs without `ANTHROPIC_API_KEY`; `Settings` deliberately does not model that key.

**Decided (not in original docs):** `httpx2` replaces `httpx` for the Starlette test client (Starlette deprecated the old one). Docker installs the project non-editable. Package name is `atsc`.

**Left for later phases:** everything functional. No taxonomy, parsing, embedding or UI yet.

### Phase 2 — Taxonomy dataset and matcher (complete, 2026-09-15)

**Built:** `taxonomy/` dataset: `categories.yaml` (per-category default weights) + six category files, 32 clusters, 431 surface forms. Seed clusters from `gap_analysis_spec.md` §2 plus additions that real ML/DS postings need (transformer architectures, CV, NLP, LLM APIs, agents, embeddings, feature stores, model evaluation, Python stack, SQL, viz/BI). `atsc.core.models` (`Category`, `RoleTrack`, `SkillCluster`), `atsc.core.taxonomy.load_taxonomy()` (Pydantic-validated, duplicate-id and missing-weight errors, category defaults with per-cluster override), `atsc.core.embedding.Embedder` Protocol, `atsc.core.matcher.ClusterMatcher` (exact regex matching: case-insensitive, hyphen/space/"&" tolerant, word-boundary anchored; embedding fallback via `match_phrases` behind the Protocol). Golden tests: all four required equivalence classes resolve to one cluster from both phrasings. Matcher timing: ~33 ms on a 7k-char text.

**Decided (not in original docs):** taxonomy path resolves from `$ATSC_TAXONOMY_DIR`, else `<repo>/taxonomy`; Docker sets the env var and installs the project editable. A surface form may map to several clusters (Airflow, Databricks) and the matcher returns all of them. Canonical names are included as surface forms where they are natural phrasings ("deep learning framework"). Python and SQL clusters override the Classical DS category weights (Python = 1.0 on every track). Cluster ids are stable identifiers: never rename once shipped.

**Left:** the embedding fallback is only tested against a fake embedder; Phase 3 adds the real model and a golden test for an unlisted phrasing. The similarity threshold (default 0.80) is a placeholder until Phase 3 measures real cosine distributions.

### Phase 3 — Embedding service (complete, 2026-09-15)

**Built:** `atsc.core.embedding.LocalEmbedder` (fastembed / ONNX Runtime, CPU, lazy load, L2-normalised float32 output, `dim` property) and `get_default_embedder()` singleton (model from `$ATSC_EMBEDDING_MODEL`, cache from `$ATSC_MODEL_CACHE_DIR`). Benchmark script `scripts/bench/embedding_bench.py` with labelled pairs `scripts/bench/pairs.json`. Docker image bakes the model in at build; verified a container embeds with `--network none` in 0.69 s including load. Real-model golden tests for the fallback added.

**Model locked in: `BAAI/bge-small-en-v1.5`** (33M params, 384-dim, 67 MB). Benchmark (CPU, ONNX, 80-line batch, 4 threads): bge-small 270 ms / AUC 0.965; all-MiniLM-L6-v2 668 ms / AUC 0.985; arctic-embed-s 233 ms / AUC 0.970 but compressed similarity range; nomic-v1.5-Q 535 ms / AUC 0.968. Granite-small-r2 was dropped without benchmarking: not available in the ONNX runtime library, and running it would pull PyTorch into the free-tier image. Thread scaling for bge-small: 1 thread 907 ms, 2 threads 482 ms, 4 threads 260 ms per 80 lines. **Hosting consequence: Fly machine must be shared-cpu-2x or better.** Embedder uses `min(4, cpu_count)` threads.

**Calibration inputs for Phase 6:** on labelled pairs, bge-small positive cosine mean 0.735 (min 0.549), negative mean 0.545 (max 0.715). Semantic-score rescale floor/ceiling should start around 0.50 / 0.85.

**Finding on the embedding fallback (gap_analysis_spec.md §1 method 2):** with a 33M model, short unlisted phrasings do not separate cleanly by cosine (correct hits at 0.77–0.80, wrong-but-plausible hits at 0.78–0.81). Default `similarity_threshold` raised to **0.85** so the fallback is high-precision only. The real fix for recall is taxonomy growth (add the phrasing as a surface form), exactly as §4 of that spec prescribes. Several of my own "unlisted" probes turned out to contain exact surface forms, which is itself evidence the surface-form lists are the workhorse.

**Left:** nothing for this phase. A dependency-footprint test guards against torch entering the free image.

### Phase 4 — Resume parsing (complete, 2026-09-15)

**Built:** `atsc.core.parsing` package: `text.py` (cleaning, bullet glyphs, mojibake), `dates.py` (date tokens with style family text/numeric/year, ranges, normalisation to `YYYY-MM`/`YYYY`/`present`), `sections.py` (alias + word-level fuzzy header detection; ALL-CAPS unknown lines are "creative" headers), `entities.py` (basics via regex with spaCy PERSON fallback; work entries from date-headed blocks with title/company split; education; skills with category-prefix stripping and cluster matching; projects), `checks.py` (platform severity table, the two text-level checks, `build_report` always emitting all eight checks), `pdf.py` (pdfplumber: column gutter + shared-row detection, ruled tables, symbol/Type 3/unmapped-glyph fonts, image-only, contact info in repeated margins), `docx_reader.py` (body-order paragraphs and tables, `w:txbxContent` text boxes, `w:cols` sections, header/footer parts, symbol fonts), facade `parse_resume_text` / `parse_resume_file` with byte-sniffed format and `UnsupportedFormatError` carrying the plain-language decline. `atsc.core.nlp` spaCy singleton (NER only, lazy). Models added to `atsc.core.models` for `data_model.md` §1–2. Fixture generator `scripts/make_fixtures.py` produces 11 PDF/DOCX fixtures (committed). Timings: text 7 ms, clean PDF 55 ms, two-column PDF 170 ms, DOCX 21 ms.

**Decided (not in original docs):**
- `header_footer_content` added as an eighth check name: it is in `resume_parsing_spec.md` §2's detection list but missing from `data_model.md`'s enum.
- Check status has a third value `not_assessed`; pasted text leaves six layout checks unassessed. PDFs leave `text_box_detected` unassessed (not distinguishable in a text stream).
- `SkillEntry.matched_clusters` is a list, not the spec's scalar: a surface form can belong to two clusters.
- `inconsistent_dates` is judged over work-experience ranges only; year-only education dates are conventional and not penalised.
- Content inside DOCX tables, text boxes and headers **is** extracted and scored, and the check explains the risk. Simulating the drop would make the score confusing ("why is my email missing?") rather than instructive.
- PDF text uses pdfplumber's linear extraction as-is, so two-column resumes are scored on the scrambled text an ATS would see.
- `non_standard_font` fails only on evidence of unreadable text: symbol/icon fonts (ZapfDingbats, Wingdings, FontAwesome), Type 3 fonts, or >1% glyphs without a Unicode mapping. Merely unusual families are not penalised: they extract fine.
- Title-case unknown lines are never section headers (job titles look identical); only ALL-CAPS unknown lines are. Inside an experience section a caps line followed within two lines by a date range is treated as an employer name, not a header.
- Lines of the form `Label: items` or containing commas are never headers.
- spaCy NER is a fallback only (name when the first lines don't look like a name; ORG tie-break for title/company). The small model mislabels "Austin, TX", so regex/structure lead.

**Left:** borderless (whitespace-aligned) tables in PDFs are not detected; only ruled tables are. Certifications are parsed into `raw_text` only (no data-model field). Both are noted, not blockers.

### Phase 5 — JD analysis (complete, 2026-09-15)

**Built:** `atsc.core.jd.parse_job_description(text, *, matcher=None) -> ParsedJobDescription`. Stage 1 (skill-sentence classification) is rule-based, per interpretation 5: the first non-empty line is the title and is never a requirement; short heading lines switch a section mode (required / preferred / responsibilities / boilerplate) via alias regexes ("Minimum qualifications", "Nice to have", "What you'll do", "Benefits", "About <Company>"…); bullets are one unit each, prose paragraphs are split into sentences; a unit is kept when it sits in a required/preferred section, or in a responsibilities section *and* names a taxonomy cluster, or (no section context) names a cluster or contains a requirement verb ("experience", "proficiency", "familiarity", "years", "degree"…). Boilerplate lines (EEO, benefits, work authorisation, company blurb, hybrid/remote policy) are always dropped. Stage 2 runs the exact cluster matcher over each kept unit into `matched_clusters`. Required/preferred: section mode, overridden per line by qualifying language ("preferred", "a plus", "bonus", "nice to have", "not required", "would be great", "ideally"). Role track: title-line pattern hits weighted 5×, body hits 1×, per track; ties or zero → `"unclear"`. Seniority: title-level words (intern / junior / mid / senior / staff / principal, with I / II / III / IV mapping to junior / mid / senior / principal and "lead", "head of" mapping to staff), else banded from the minimum years asked (<2 junior, 2–4 mid, 5–7 senior, 8+ staff), else `"unclear"`. Models `Requirement` and `ParsedJobDescription` added to `atsc.core.models` for `data_model.md` §3; `embedding` is excluded from serialisation like the resume side. Two fixtures: a sectioned MLE/LLM posting and a headerless prose Data Scientist posting. 22 tests, 94 total.

**Decided (not in original docs):**
- `Requirement.matched_clusters` is a list (same reasoning as `SkillEntry`).
- `ParsedJobDescription.years_experience: int | None` added beside `seniority_signal` so the deep report can quote the number; `seniority_signal` itself stays a string with a fixed vocabulary (intern, junior, mid, senior, staff, principal, unclear).
- `role_track_signal` uses the `RoleTrack` enum values (`mle`, `data_scientist`, …) or the literal `"unclear"`, not the spec's display strings; display mapping is a UI concern.
- Responsibility lines that name a concrete skill ("deploy LLM features using RAG and vector databases") are kept as *required* requirements: the spec excludes only "responsibility descriptions without a concrete skill", and these lines are exactly what the resume's bullets should be matched against.
- Spec §3 stage 2 says taxonomy matching is semantic (embedding). On the JD side exact surface-form matching is used, with the embedding fallback available by passing an embedder-equipped `ClusterMatcher`; the default matcher is exact-only so the free path never pays the model load twice. Consistent with interpretation 2 (fallback lives in taxonomy overlap).

**Left:** no learned stage-1 classifier (allowed later, must stay self-hosted). Multi-JD aggregation is out of scope per spec §5. Next: Phase 6 scoring engine.

### Phase 6 — Scoring engine (complete, 2026-09-15)

**Built:** `atsc.core.scoring.score(resume, report, jd, *, role_track=None, platform=None, embedder=None, matcher=None) -> ScoreResult`, plus the three components as separately testable functions. **Semantic match** (`semantic_match`): every resume line (work bullets, project bullets, skill entries; raw-text lines as a fallback when parsing produced none) and every JD requirement is embedded; each requirement takes its best resume line by cosine; the cosine is rescaled linearly between `COSINE_FLOOR`/`COSINE_CEILING` and clipped per requirement; required lines weigh 1.0 and preferred 0.5; the score is the weighted mean. Each requirement's best line and similarity is returned as a `RequirementMatch`. **Taxonomy overlap** (`taxonomy_overlap`): JD clusters are the union of `Requirement.matched_clusters` (a cluster named by any required line counts as required); resume clusters come from bullets and skill entries, with the embedding fallback applied to skill phrases the exact matcher left unmatched; each JD cluster weighs `role_track_weight[track] × (1.0 required | 0.5 preferred)`; score = matched weight / total weight. Output carries cluster id, canonical name and one evidence line from each side. **Parseability** (`parseability_score`): 100 − Σ penalty over failed checks, penalty by the selected platform's severity (high 25 / medium 15 / low 5), generic = max severity across the four platforms, floored at 0. **Blend**: 0.45 / 0.35 / 0.20, rounded. `ScoreResult`, `ScoreComponents`, `MatchedSkill`, `UnmatchedSkill`, `RequirementMatch` and the fixed `DISCLAIMER` added to `atsc.core.models`. `warm()` loads the model and the surface-form matrix; the Dockerfile's build-time check now calls it. Verified inside the image with `--network none`: warm 0.94 s, score 15 ms. Fixture pair (clean resume × MLE/LLM JD): 79 overall (semantic 63, taxonomy 88, parseability 100), 116 ms after warm-up. 21 tests, 115 total; the e2e test blocks socket connections and asserts < 3 s.

**Decided (not in original docs):**
- **Query instruction prefix.** bge models are trained with `"Represent this sentence for searching relevant passages: "` on the query side for asymmetric retrieval. JD requirements are embedded with it; resume lines are not. On the fixture pair it fixed visibly wrong best-line picks (the LoRA requirement now matches the LoRA bullet rather than an MLflow bullet). It lowers cosines by ≈0.04, so the calibration was re-fitted on `scripts/bench/pairs.json` with the prefix applied: positives mean 0.694, negatives mean 0.514; **floor 0.47, ceiling 0.82** maps them to ≈64 / ≈15 (same spread the plain 0.50/0.85 calibration had). Supersedes the Phase 3 note's 0.50/0.85 starting values.
- Per-requirement clipping before averaging, so one very strong match cannot compensate several misses.
- Preferred weight 0.5 in both components (the JD spec only says "weighted lower").
- Role-track weighting uses the selector value, else the JD's `role_track_signal`, else uniform 1.0 (no track ⇒ no re-weighting). `ScoreResult.role_track` reports which was applied.
- Additive fields on `ScoreResult`: `unmatched_preferred_skills`, `requirement_matches`, `role_track`, `platform`. They serve the transparency requirement and do not change the spec'd fields.
- A JD naming no taxonomy cluster scores 0 on taxonomy overlap; a JD yielding no requirement lines scores 0 on semantic match. The UI (Phase 7) must say why rather than show a bare 0.
- The embedding fallback runs only on unmatched *skill-section phrases*, not on bullets or JD sentences: the 0.85 phrase threshold is meaningless on full sentences.

**Left:** weights and calibration are hypotheses until the evaluation framework exists (spec §5). Skill-entry lines like "PyTorch" often win as best line for a requirement, which is correct evidence but terse; the UI may prefer to show the longest of near-tied lines. Next: Phase 7 web layer.

### Phase 7 — Web layer (complete, 2026-09-15)

**Built:** Server-rendered Jinja2 + htmx, no build step. `atsc.free.service` is the pure Layer 1 request handler (validation → parse → score; `SubmissionError` carries a status and a plain-language message) and `atsc.free.presentation` holds labels and view models (role/platform names, one label and one-sentence explanation per parseability check, per-platform notes, category weights per track derived from the taxonomy's actual cluster weights). `atsc.web.routes` holds the HTTP layer: `GET /` (two-box form), `POST /score` (multipart: pasted text or file, JD text, platform, role track; returns the result fragment for htmx requests and the full page otherwise, so the flow works with JavaScript off), `GET /roles/{track}` and `GET /ats/{platform}` (crawlable landing pages with the form pre-selected), `GET /how-it-works` (weights, calibration constants and penalties read from the scoring module, never retyped), `GET /report` (honest placeholder until Phase 10), `GET /healthz`. `create_app(warm=...)` runs `scoring.warm()` in the lifespan so the first request pays nothing; `ATSC_WARM_ON_START=0` and `create_app(warm=False)` skip it (tests). Settings: `max_upload_bytes` (2 MB, enforced by reading limit+1 bytes) and `warm_on_start`. Static: `site.css`, self-hosted htmx 2.0.10, Inter variable and IBM Plex Mono Regular with licences. `fly.toml`: one always-on `shared-cpu-2x` / 2 GB machine, health check on `/healthz`. Verified through the running server: two-column PDF × MLE JD renders in 1.03 s end to end. Screenshots reviewed at 1280 px and 400 px. 24 web tests; 139 total.

**Design system (build_plan §3 "Visual design", as implemented):** paper `#F5F4F0`, ink `#111`, grey text `#5F5E5A`, hairline `#C8C6BF`, red `#E30613`. Inter for everything with tabular numerals; IBM Plex Mono only inside `<q>` for quoted evidence. Type scale 14 / 16 / 18 / 22 / 28 / 40 px; the score numeral is `clamp(120px, 18vw, 200px)` and is the only large element on any page. 12-column grid, 24 px gutters, collapses to one column under 800 px. Every table is hairline-ruled with an ink rule at head and foot. Red appears in exactly three places: a failed check's status, the names of missing *required* skills (heading turns red only when the count is non-zero), and the paid CTA. Print stylesheet hides the masthead, form, CTA and hero and sets black on white. Copy is sentence case, no all-caps labels, no icons, no arrows. Headline: "Your resume against one ML job description, scored line by line."

**Decided (not in original docs):**
- Layering: `free` may not import `web`; `web` imports `free` and `core`. Templates live in `web`, service logic in `free`, so a future JSON API can reuse `free.service` unchanged.
- Validation errors return 422 (413 for oversized files) as HTML; htmx is configured via `htmx-config` to swap on every status so the message lands in the result panel. Non-htmx requests get the full page with the message in place of the result.
- Minimum input sizes: 200 characters of resume text, 100 of JD text. Below that the message says what is missing rather than scoring garbage.
- A file that parses to under 200 characters (image-only PDF) is refused with the image-PDF explanation instead of scoring near zero.
- Evidence quotes are clipped to 160 characters for display with an ellipsis; the full line still drove the score. Two-column PDFs otherwise show five-line scrambled quotes, which is honest but unreadable.
- Role-track default option is "Detect from the posting"; the result states which weighting was applied and where it came from.
- The pasted-text result says how many checks were not assessed and asks for the real file, per interpretation 1.
- SEO pages are data-driven (severity table, category weights), not marketing copy, so they stay true when the tables change.

**Left:** no rate limiting yet (add at the Fly proxy or a small in-process limiter before public launch). No per-check "location" for PDF tables beyond page number. Next: Phase 8 Layer 2 corpus and retrieval.

### Phase 8 — Layer 2 corpus and retrieval (complete, 2026-09-15)

**Built:** `corpus/` (curated, versioned, no model-generated text): six `bullets/<category>.yaml` files with 67 strong bullet examples (at least two per cluster, each naming a method, a scale and an outcome, with a one-line "why it works") and 16 weak→stronger rewrite pairs; `platforms.yaml` with 13 platform behaviours, every one cited to `resume_parsing_spec.md` §3; `guidance.yaml` with 10 writing-guidance entries including keyword density versus readability. `atsc.deep.corpus.load_corpus()` validates every file with Pydantic, refuses unknown cluster ids, derives one equivalence chunk per taxonomy cluster at load time ("Fine-tuning / PEFT is also written as: LoRA, QLoRA, …") so the corpus never drifts from the matcher, and gives every chunk a contextual prefix (technical_architecture.md §5). 138 chunks total. `atsc.deep.retrieval.CorpusIndex`: in-process dense matrix (self-hosted embedder, bge query instruction on the query side) plus BM25 (`rank-bm25`), fused by reciprocal rank fusion (k = 60, 50 candidates per side); filters by kind, cluster and platform; `dense` / `sparse` / `hybrid` modes; `evaluate()` computes recall@k and MRR over a labelled set. `tests/fixtures/retrieval_eval.json`: 28 labelled queries across all five chunk kinds. `scripts/bench/retrieval_bench.py` compares models and modes. Settings: `deep_embedding_model` (default `BAAI/bge-base-en-v1.5`). 15 tests.

**Numbers (28 queries, recall@5 / MRR):**

| model | dense | sparse | hybrid | query |
|---|---|---|---|---|
| bge-small-en-v1.5 | 0.89 / 0.76 | 0.96 / 0.66 | 0.96 / 0.73 | 4 ms |
| bge-base-en-v1.5 | 0.96 / 0.79 | 0.96 / 0.66 | 0.96 / 0.75 | 11 ms |

The single hybrid miss was a corpus gap (a Spark bullet that only said "PySpark"), fixed in the corpus rather than the retriever. Thresholds in the test: recall@5 ≥ 0.85, MRR ≥ 0.6.

**Decided (not in original docs):**
- **No reranker at launch.** Hybrid recall@5 is 0.96 on a 138-chunk corpus; a reranker would add a model for no measurable gain. Re-run the bench when the corpus passes ~1k chunks.
- **Layer 2 embedding model is `BAAI/bge-base-en-v1.5`, not Qwen3-Embedding-0.6B / bge-m3.** Neither runs in the ONNX runtime (fastembed 0.8) the project standardised on; adding PyTorch to the worker just for embeddings is operational weight the numbers do not justify. bge-base beats bge-small on dense recall (0.96 vs 0.89) and MRR, which is what matters as the corpus grows; the cost is 210 MB and 7 ms per query, both irrelevant on the paid path. Supersedes §3's model row.
- Zero-signal documents get no rank on either side (BM25 score 0, cosine ≤ 0), so RRF cannot promote a document that neither retriever found.
- Corpus rule (README): a rewrite pair's stronger version must be plausibly true of the weak one. The report must never coach a claim the candidate cannot back.
- The Layer 2 model is not baked into the Layer 1 web image; the worker image (Phase 10) gets it.

**Left:** corpus breadth. 67 bullets across 32 clusters is a seed; the growth loop (Phase 11) should add bullets where retrieval returns only the equivalence chunk. Next: Phase 9 generation.

### Phase 9 — Layer 2 generation (complete, 2026-09-15)

**Built:** `atsc.deep.models` (`Explanation`, `RewriteSuggestion`, `DeepReport` per `data_model.md` §6; `retrieved_context` and `grounding_examples` are `min_length=1`, so an ungrounded object cannot exist). `atsc.deep.generation` is the only module that imports the Anthropic SDK (positive-control test added to `test_cost_boundary.py`). Two structured-output calls per report via `client.messages.parse` with a Pydantic `output_format`, adaptive thinking, and a cached system prompt: one for explanations (every matched skill, every unmatched required skill, every failed parseability check), one for rewrites (up to six weakest resume bullets, chosen from `requirement_matches` below 70 with at least six words). Retrieval per item: the cluster's equivalence chunk plus its top strong bullets; platform quirks filtered to the selected platform for failed checks; strong bullets and rewrite pairs for the target requirement's clusters plus the keyword-density guidance for rewrites. **Grounding mechanism:** the model never writes grounding text. It receives numbered context items `[C1]…` and returns `context_ids` / `example_ids`; the code maps ids back to the verbatim corpus text. Empty or unknown ids raise `GroundingError` and the report is not produced. `atsc.deep.readability`: Flesch reading ease plus taxonomy-mention density; `readability_flag` is true when density rises by more than 0.02 and either reading ease drops by 10+ points or density exceeds 0.20. Fabrication guard: a rewrite that introduces a number absent from the original bullet is dropped. `atsc.deep.diff.rewrite_diff` emits a changed-lines-only diff with a note on flagged rewrites. `scripts/deep_report_smoke.py` runs one real report from the fixtures (spends tokens; owner-run). 16 tests, 170 total.

**Decided (not in original docs):**
- Model comes from `Settings.deep_llm_model` (`claude-sonnet-5`, owner decision) and is passed into the generator; the module never names a model.
- Parseability findings are explained too, with `cluster_id = "check:<check_name>"`, grounded in the cited platform chunks. `data_model.md` §6 only lists skill explanations; this is additive and uses the same object.
- Rewrites are only offered for existing weak bullets, never invented for missing skills: the corpus rule "never coach a claim the candidate cannot back" applies to generation as well.
- `output_config.effort` is left at the API default rather than lowered: `messages.parse` sets `output_config.format` itself and the two cannot be verified to combine without a live call. Revisit in the smoke run.
- Refusals (`stop_reason == "refusal"`) surface as `GenerationRefusedError`; truncation as `GenerationError`. Neither produces a partial report.
- No live API call has been made. There is no credential on the build machine, and a metered call is the owner's to trigger; run `scripts/deep_report_smoke.py` once with a key to confirm prompt behaviour before Phase 10 wires payments.

**Left:** prompt quality is unvalidated against the real model (see smoke script). Next: Phase 10 payments, worker and delivery.

### Phase 10 — Payments, worker and delivery (complete, 2026-09-15)

**Built:** `atsc.deep.handoff`: the result page carries the full scored inputs (`JobInputs`: parsed resume, parseability report, parsed JD, score result) as a compressed, checksummed payload in the checkout form, so the free check stays stateless and nothing is stored until the buyer clicks. `atsc.deep.db`: SQLAlchemy 2.0 `report_jobs` table (`awaiting_payment → queued → running → done | failed`), `JobStore` with idempotent `mark_paid` and a `claim_next` that uses `SKIP LOCKED` so several workers can share one Postgres. `atsc.deep.payments`: Stripe Checkout Session in `payment` mode with the price id from settings and the job id as `client_reference_id`; webhook verified with `StripeClient.construct_event`. `atsc.deep.email`: SMTP sender, log sender (default), recording sender (tests). `atsc.deep.worker` (`python -m atsc.deep.worker`): polls, generates one report at a time with the configured model, records failures on the job, emails the private link; the only process that holds `ANTHROPIC_API_KEY`. `atsc.web.report`: `POST /report/checkout` (decode payload → create job → redirect to Stripe), `POST /stripe/webhook`, `GET /report/{token}` (unpaid / generating with htmx polling / failed / done), `GET /report/{token}/status` fragment with `HX-Redirect` when finished, `GET /report/{token}/diff` download. Report page renders every explanation and rewrite with its grounding passages under a disclosure, flags stuffed rewrites in red, shows the fixed disclaimer. Settings: `database_url`, `public_base_url`, `stripe_*`, `smtp_*`, `email_from`, `worker_poll_seconds`, `payments_enabled`. `fly.toml` gains a `worker` process group; the Dockerfile bakes the Layer 2 embedding model so both groups share one image (1.62 GB, verified offline). 14 tests, 184 total.

**Decided (not in original docs):**
- Report tokens are 256-bit random strings stored on the job; the URL is the credential. No signing library and no accounts, matching the no-signup positioning.
- The price is a Stripe Price id in settings, never an amount in code.
- Stripe Checkout collects the buyer's email; the webhook stores it and the worker emails the link after generation. If SMTP is unset the link is logged, which is the local-dev behaviour.
- `mark_paid` only moves `awaiting_payment` jobs, so replayed webhooks are harmless.
- A failed generation leaves the job `failed` with the error text; the page tells the buyer to reply to the receipt for a refund. Refunds are manual at this stage.
- One image for web and worker. The 210 MB Layer 2 model rides along in the web image; splitting images can wait until size matters.
- The free layer's cost boundary is unchanged: the web process imports the job store and Stripe, never the generator; `tests/test_cost_boundary.py` still passes on the import graph.

**Left (owner actions before public launch):** create the Stripe product and price, set the three Stripe secrets and `ATSC_PUBLIC_BASE_URL`, point `ATSC_DATABASE_URL` at Postgres, set `ANTHROPIC_API_KEY` for the worker group only, configure SMTP, run `scripts/deep_report_smoke.py` once, add rate limiting on `/score`. Retention policy for stored inputs and reports is not implemented (suggest deleting jobs 30 days after completion). Next: Phase 11 (deferred items).

### Phase 11 — Deferred items (growth loop complete, multi-JD deferred, 2026-09-15)

**Built:** taxonomy growth loop per `gap_analysis_spec.md` §4. `atsc.free.growth.candidate_terms` takes the unmatched skill-section phrases from the resume and, from JD requirement lines that matched no cluster and start with a requirement lead-in ("experience with", "proficiency in", …), the comma/or/and-separated fragments of up to three words. Anything with a digit or "@", longer than 40 characters, or in a small noise list is dropped. `GrowthLog` counts terms in a SQLite table (term, count) at `ATSC_GROWTH_LOG_PATH`; unset means off, which is the default. When on, the footer says so. `scripts/growth_report.py` prints the top terms; a term near the top is a candidate surface form or missing cluster. 6 tests, 190 total. `CLAUDE.md` Commands section lists the worker, smoke, bench and growth commands.

**Deferred, deliberately:** multi-JD comparison. `product_requirements.md` §5 item 6 defers it "until Layer 1 and Layer 2 are working and validated"; Layer 2 has not yet run against the real model (see Phase 9). The free flow is stateless per request, so the natural shape is one resume held client-side and N postings scored in sequence on one page; nothing in the current design blocks it.

**Decided (not in original docs):**
- The growth log is aggregate-only and opt-in so the footer's "nothing stored" stays true by default, and becomes "terms counted in aggregate" only when the owner turns it on.
- Prose requirement sentences without a lead-in are not mined; they are rarely skill lists and would leak sentence fragments.

### Phase 12 — Public launch readiness (complete, 2026-09-16)

**Built:** `README.md` as the public front door: pitch, the two layers in plain terms with the component weights table, quickstart, status line (free layer standalone, paid layer awaits owner-side Stripe/Postgres/key/SMTP configuration), pointer to this file. Two screenshots in `docs/screenshots/` taken from the app running locally against the test fixtures (form at 1280 px; the score sheet for the clean resume × MLE JD pair, 79/100); no live URL is claimed. `LICENSE` (MIT) declared in `pyproject.toml`; htmx's BSD Zero Clause notice added next to the font licences. `atsc.web.ratelimit`: `SlidingWindowLimiter` (per key, at most N hits in any W seconds, idle keys pruned) and `RateLimitMiddleware`, pure ASGI, installed in `create_app` so the limit is visible in the import graph; limited to `POST /score`; a blocked request gets 429 with `Retry-After` and either the error fragment (htmx) or the full page. Settings `score_rate_limit` (30), `score_rate_window_seconds` (600), `client_ip_header` (empty; `fly.toml` sets `Fly-Client-IP`). `JobStore.purge` plus `atsc.deep.retention` (`python -m atsc.deep.retention`, `--dry-run`, `--finished-days`, `--abandoned-days`) and the `scripts/purge_jobs.py` wrapper; not imported by the web or worker processes. 15 tests, 205 total. Four scoped commits, one per task.

**Decided (not in original docs):**
- The limiter trusts no forwarding header unless the owner names one in `ATSC_CLIENT_IP_HEADER`. Without that, `X-Forwarded-For`-style headers are ignored, so a direct client cannot buy fresh buckets by inventing them. On Fly the proxy sets `Fly-Client-IP` and the config names it.
- Limiter state is per process. One always-on web machine is the plan; with more machines the effective limit multiplies by their count, which is still bounded. A shared store would add a dependency to the free path for no present need.
- Default budget 30 checks per 10 minutes per client: a person iterating on one resume does perhaps ten; a scraper does far more. `ATSC_SCORE_RATE_LIMIT=0` disables it (tests and local dev).
- Retention deletes two classes, not one: finished (`done`/`failed`) jobs after 30 days, and `awaiting_payment` jobs after 7 days. An abandoned checkout still holds a resume, and a Stripe Checkout session expires within 24 hours, so an unpaid job a week old can never be paid. `queued`/`running` jobs are never touched.
- The retention CLI is a module rather than only a script so the Fly scheduled machine can run it from the existing image, which does not copy `scripts/`.
- MIT: nothing in `docs/` constrains licensing, and the bundled third-party assets (OFL fonts, 0BSD htmx) are compatible.

**Left (owner actions, all configuration):** see §7. Nothing in this phase changed the cost boundary: `lint-imports` reports both contracts kept, `ANTHROPIC_API_KEY` remains unset, and no live model call has been made.

## 7. Launch checklist (owner actions)

Everything below is configuration or a paid action; the code path for each is built and tested.

1. Stripe: create the product and one-time price; set `ATSC_STRIPE_SECRET_KEY`, `ATSC_STRIPE_PRICE_ID`, `ATSC_STRIPE_WEBHOOK_SECRET`; point the webhook at `POST /stripe/webhook`.
2. Fly: `fly launch` with `fly.toml`; set `ATSC_PUBLIC_BASE_URL`; attach Postgres and set `ATSC_DATABASE_URL`; set `ANTHROPIC_API_KEY` as a secret and confirm it is reachable only from the `worker` process group (the web group must not have it: cost-boundary guard 3).
3. Email: set `ATSC_SMTP_*` and `ATSC_EMAIL_FROM`, or leave unset to log links during a soft launch.
4. Run `scripts/deep_report_smoke.py` once with a key and read the output: prompt behaviour, effort level and cost per report are unvalidated until then.
5. Rate limiting is built (Phase 12) and on by default. Confirm `ATSC_CLIENT_IP_HEADER=Fly-Client-IP` is set on Fly (it is in `fly.toml`) so buckets key on the real client, and adjust `ATSC_SCORE_RATE_LIMIT` / `ATSC_SCORE_RATE_WINDOW_SECONDS` if the defaults (30 per 10 minutes) prove wrong.
6. Schedule the retention job (Phase 12): `fly machine run <image> --schedule daily "python -m atsc.deep.retention"` with `ATSC_DATABASE_URL` set, or an equivalent cron. Defaults delete finished jobs after 30 days and abandoned checkouts after 7; run with `--dry-run` first.
7. Optional: set `ATSC_GROWTH_LOG_PATH` and review `scripts/growth_report.py` weekly to grow `taxonomy/`.
