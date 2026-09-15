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
