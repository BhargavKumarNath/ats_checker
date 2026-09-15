# Technical Architecture — System Blueprint

**Read this document last, after `product_requirements.md`, `resume_parsing_spec.md`, `job_description_analysis.md`, `gap_analysis_spec.md`, `ats_scoring_spec.md`, and `data_model.md`.** Those six documents define *what* the system must do and *what shape* its data takes. This document is the synthesis layer: it explains how those pieces fit together as one running system, and where you have real latitude to design the best possible implementation.

This is deliberately a high-level blueprint, not a step-by-step build script. The Tier 1 specs already pin down the parts that matter most, the scoring methodology, the taxonomy, the data shapes, the honesty constraints. Everything below this document's objectives and topology is a space for your own engineering judgment: language, frameworks, hosting, exact library choices, and implementation details are yours to decide using current best practice at the time you build. Where a decision is genuinely open, this document says so explicitly rather than pretending there's only one right answer.

---

## 1. System Objectives, Restated as Architecture Drivers

Every architectural decision in this system traces back to one of these, all established across the Tier 1 documents:

1. **The free path must be able to run at unlimited volume with near-zero marginal cost.** No per-request calls to a metered LLM or embedding API on the free path. This is not a cost optimization, it's the constraint that makes the entire $10k-site business model (see `ats_proposal.md`) actually work.
2. **The paid path is where real generative intelligence, and real cost, lives.** It should be architected as a genuine RAG system, not a thin prompt wrapper, because that grounding is the product's actual defensibility (see `ats_proposal.md` §4 and `data_model.md` §6).
3. **Every score and every generated explanation must be traceable back to a concrete cause**, whether a taxonomy cluster match, an embedding similarity, a parseability rule, or a retrieved corpus passage. Opacity is the single most-documented failure of every competitor researched (`ats_proposal.md` §4). Architect for traceability as a first-class concern, not an afterthought bolted on for the UI.
4. **The system must be low-maintenance by construction**, not by discipline. Prefer stateless, horizontally-scalable, mostly-precomputed components over anything that needs constant tending.

---

## 2. High-Level Topology

Think of the system as three tiers, matching the two-layer product model plus the shared foundation both layers read from:

```
                     ┌─────────────────────────────┐
                     │   Shared Foundation Layer     │
                     │  (built once, read by both)   │
                     │                                │
                     │  • Skill taxonomy store        │
                     │    (gap_analysis_spec.md)      │
                     │  • Resume/JD parsing pipeline   │
                     │    (resume_parsing_spec.md,     │
                     │     job_description_analysis.md)│
                     │  • Embedding inference           │
                     │    (self-hosted, CPU-friendly)   │
                     └───────────┬───────────────────┘
                                 │
              ┌──────────────────┴───────────────────┐
              │                                       │
   ┌──────────▼──────────┐               ┌────────────▼────────────┐
   │   Layer 1 Service     │               │   Layer 2 Service        │
   │   Free, instant,      │               │   Paid, deep, RAG-       │
   │   deterministic       │               │   grounded                │
   │                        │               │                           │
   │  Produces:             │               │  Consumes: Layer 1's      │
   │  ScoreResult            │               │  ScoreResult as input     │
   │  (data_model.md §5)      │               │                           │
   │                          │               │  Reads: retrieval corpus  │
   │  No metered API calls    │               │  (built once, reused per │
   │  in this path, ever      │               │  request)                 │
   │                          │               │                           │
   │                          │               │  Calls: an LLM API,       │
   │                          │               │  only here, only on       │
   │                          │               │  explicit paid request    │
   │                          │               │                           │
   │                          │               │  Produces: DeepReport     │
   │                          │               │  (data_model.md §6)       │
   └──────────────────────────┘               └───────────────────────────┘
```

**Why this shape, not a monolith:** Layer 1 and Layer 2 have fundamentally different cost, latency, and reliability profiles (sub-3-second and free, versus slower and metered). Treating them as separate services, even if deployed together initially, keeps the free-tier cost guarantee architecturally enforced rather than a convention someone could accidentally violate by adding an LLM call to the wrong code path. This separation is worth preserving even at small scale, because it is the mechanism, not the intention, that keeps the free layer sustainable.

---

## 3. The Shared Foundation Layer

This is what both Layer 1 and Layer 2 depend on, and it should be built and stabilized first.

- **Skill taxonomy store.** The structured form of `gap_analysis_spec.md`, per the `SkillCluster` shape in `data_model.md` §4. This should be an independently-versioned dataset, not inline code, since it's explicitly meant to grow over time (`gap_analysis_spec.md` §4). How it's stored (flat file, embedded database, whatever fits your chosen stack) is your call; that it's decoupled from application logic is not.
- **Resume/JD parsing pipeline.** Implements `resume_parsing_spec.md` and `job_description_analysis.md`, producing the `ParsedResume`, `ParseabilityReport`, and `ParsedJobDescription` objects defined in `data_model.md` §1–3. This pipeline is shared, called by Layer 1 on every free request and reused as-is by Layer 2 (Layer 2 should never re-parse from scratch, it builds on Layer 1's output).
- **Embedding inference.** A single embedding capability, self-hosted, used for both the fast Layer 1 similarity scoring (`ats_scoring_spec.md` §2) and the richer Layer 2 retrieval matching. Current benchmarking (see `ats_scoring_spec.md` §2) shows CPU-friendly, MiniLM-class models running in the low thousands of sentences per second, which is the kind of throughput that makes self-hosting genuinely cheaper than a metered embedding API at free-tier volume. Whether Layer 1 and Layer 2 use the exact same embedding model or two differently-sized models (a smaller one for the instant free path, a larger one for the higher-latency-tolerant paid retrieval) is a real, open design decision, current 2026 embedding benchmarks (MTEB) should be checked at build time rather than trusting this document's specific model names to still be state of the art.

---

## 4. Layer 1: Free-Tier Scoring Service

**Responsibility:** implement the full pipeline in `ats_scoring_spec.md` end to end, producing a `ScoreResult` (`data_model.md` §5) in under three seconds, with zero metered API calls.

**Design guidance, not a mandate:**
- This service should be stateless per request, no session, no required persistence, matching the no-signup requirement in `product_requirements.md` §3. Statelessness here is also what makes horizontal scaling trivial if traffic spikes, which is exactly the failure mode a search-intent-driven free tool needs to survive (`ats_proposal.md` principle 5).
- Favor a deployment model that scales toward zero cost at zero traffic and scales out cheaply under load, current cloud platforms all offer some flavor of this (serverless functions, autoscaling containers, scale-to-zero compute); the specific provider and mechanism is an implementation decision, not a constraint this document fixes.
- The embedding inference call inside this service is the one place latency matters most given the 3-second budget; benchmark actual latency against real resume/JD-length text before committing to a specific model size, rather than assuming the benchmarked numbers in `ats_scoring_spec.md` transfer exactly to your production setup.

---

## 5. Layer 2: RAG-Grounded Deep Report Service

**Responsibility:** implement the retrieval-then-generate flow described in `ats_proposal.md` §4 and `data_model.md` §6, producing a `DeepReport` grounded in the retrieval corpus, triggered only by explicit paid user action.

**What "state of the art" means here, concretely, based on current (2026) production RAG practice:**

- **Naive RAG (embed the query, retrieve top-k, stuff into a prompt) is a known-weak baseline** — current analysis of production RAG systems finds naive pipelines fail at retrieval roughly 40% of the time. The retrieval corpus in this system is small and domain-specific (the ML/DS taxonomy plus curated example bullets, per `ats_proposal.md` §4), which works in this product's favor, but retrieval quality should still be treated as the primary risk in this service, not an afterthought. If a generated explanation or rewrite is wrong, the far more likely cause is that retrieval surfaced the wrong context, not that the LLM reasoned badly on correct context, current practice explicitly recommends fixing retrieval before touching generation when quality issues appear.
- **Contextual grounding matters more than raw retrieval volume.** A published technique worth knowing (and worth considering here, not mandating): prepending short explanatory context to each corpus chunk before embedding it, so a chunk doesn't lose meaning when separated from its source, has been shown to meaningfully improve retrieval recall in production RAG systems. Given this system's corpus is curated and relatively small (taxonomy entries, example bullets, ATS platform quirks), applying this kind of care to how the corpus is chunked and embedded is likely worth more than architectural complexity elsewhere.
- **A reference architecture worth knowing, not necessarily copying wholesale:** current production RAG stacks commonly combine an orchestration layer, a vector store, a reranking step, and an evaluation framework (RAGAS is the current standard for automated RAG-quality metrics: faithfulness, answer relevance, context precision, context recall). Whether this system needs a full reranking stage given its narrow, curated corpus is a genuine judgment call, a small, well-curated corpus may retrieve well enough with similarity search alone. Evaluate rather than assume.
- **Every output must carry its grounding.** This is not optional, it's restated from `data_model.md` §6: an `explanation_text` or `suggested_rewrite` with no corresponding `retrieved_context` / `grounding_examples` is a defect, because ungrounded generation is exactly the "generic LLM output" failure mode this entire product is positioned against (`ats_proposal.md` §4).
- **Consider whether a single-shot retrieve-then-generate call is sufficient, or whether an agentic pattern (the system reasoning about what to retrieve, checking whether it has enough context, retrieving again if not) meaningfully improves quality for this task.** Current practice increasingly favors the latter for open-ended queries; this product's queries are fairly structured (score explanation, bullet rewrite for a known gap), so a simpler pattern may be entirely sufficient. This is a real design decision, not a foregone conclusion either way, make it deliberately.

**LLM choice for the generation step:** any current-generation capable model reached via API is appropriate here, since this is the one part of the system where a metered call is explicitly budgeted for (`product_requirements.md` §3). Model choice, prompt structure, and exact retrieval-count-per-request are implementation details left to your judgment.

---

## 6. The Cost Boundary as an Architectural Rule, Not Just a Guideline

Draw a hard line, in whatever way your chosen stack makes structurally enforceable (separate services, separate deployment units, a code-review rule, a dependency-injection boundary, whatever fits): **no code path reachable from a free-tier request may call a metered LLM or embedding API.** This single rule is what keeps `product_requirements.md`'s principle-4 and principle-5 commitments true under real traffic rather than true only in the design document. Treat any proposed feature that would violate it as needing to move to Layer 2, or be re-architected to use only the deterministic/self-hosted components in §3, not as a reason to relax the rule.

---

## 7. What This Document Deliberately Leaves Open

To be explicit about where your own judgment should lead, rather than this document's:

- Programming language and web framework.
- Specific hosting/cloud provider and deployment mechanism.
- Exact embedding model (beyond the size-class reasoning in §3 and `ats_scoring_spec.md`), current MTEB standings at build time should inform this, not this document's specific names.
- Vector storage mechanism for the Layer 2 corpus, given the corpus is small and curated, a lightweight solution may well outperform a heavyweight distributed vector database in both simplicity and cost, but that's a call to make against the actual corpus size once built.
- Whether Layer 1 and Layer 2 share a deployment unit initially (reasonable for a first launch) or are fully separate services from day one (reasonable if you want the cost boundary in §6 physically, not just logically, enforced).
- Exact chunking strategy, reranking presence/absence, and retrieval-count tuning for Layer 2, per the evaluation-over-assumption guidance in §5.
- Frontend framework and how Layer 1's instant result is rendered, this document has no opinion on that; `product_requirements.md` §3's "under 10 seconds, no explanation needed" constraint is the only binding requirement.

Build the best version of this system your own reasoning arrives at, within the objectives in §1 and the cost boundary in §6. Those are the parts that came from real research and real product positioning decisions across the other six documents; everything else here is a map of how the pieces relate, not a cage around how you build them.
