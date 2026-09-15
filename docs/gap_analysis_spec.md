# Gap Analysis Specification — The ML/DS Skill Taxonomy

**This is the single most valuable document in the project.** Per `ats_proposal.md` §4, the entire competitive positioning rests on one fact confirmed by direct research: every existing ATS checker, including the ML/DS-adjacent ones already on the market (Resume Optimizer Pro, ATSAlign, QuickResumeAI, WisGrowth), explicitly does literal string matching and none model ML/DS-specific vocabulary equivalence at all. This taxonomy is what closes that gap. Treat it as living IP that should keep growing, not a one-time list.

---

## 1. Taxonomy Structure

Each entry is a **skill cluster**: one underlying competency, with multiple valid surface-form phrasings that should all score as a match against each other. This mirrors the structure used by established labor-market taxonomies (ESCO, O\*NET — see `job_description_analysis.md` §2) rather than being a novel format.

```
cluster_id: unique identifier
canonical_name: the primary display name
surface_forms: [list of phrasings that should all match this cluster]
role_track_weight: {MLE: 0-1, Applied Scientist: 0-1, Data Scientist: 0-1, ML Research: 0-1, Data Engineer: 0-1}
category: one of the six categories in §2
```

Matching against a cluster happens two ways, both feeding into the semantic score defined in `ats_scoring_spec.md`:
1. **Exact surface-form match** — fast, deterministic, catches the literal cases competitors already handle.
2. **Embedding similarity above threshold** — catches phrasings not in the explicit surface-form list, which is what makes this system genuinely semantic rather than a longer keyword list.

---

## 2. Taxonomy Categories and Seed Clusters

This is a **seed set** built from current (2026) research on what ML/DS/AI job postings actually require, cross-referenced across multiple independent sources analyzing hundreds of real job listings. It is explicitly not exhaustive — the taxonomy should grow as real resumes and JDs are run through the system and reveal gaps.

### Category: Core ML Foundations
- **Cluster: Deep learning frameworks** — surface forms: PyTorch, TensorFlow, JAX, Keras. (Research note: PyTorch appears in roughly 38% of current AI/ML engineering postings and roughly 85% of recent deep learning papers, making it the dominant but not exclusive framework — the cluster must not treat TensorFlow/JAX mentions as non-matches.)
- **Cluster: Fine-tuning / PEFT** — surface forms: LoRA, QLoRA, PEFT, parameter-efficient fine-tuning, adapters, fine-tuning. This is the flagship example cited throughout the research (`ats_proposal.md` §4) of the exact equivalence literal matchers miss.
- **Cluster: Distributed training** — surface forms: distributed training, data parallelism, model parallelism, multi-GPU training.

### Category: LLM / GenAI (highest-growth category per current research)
- **Cluster: Retrieval-augmented generation** — surface forms: RAG, retrieval-augmented generation, vector search, retrieval over a knowledge base. Current research explicitly flags this as "the dominant enterprise AI pattern in 2026" — a resume lacking any RAG-adjacent vocabulary is described as "effectively invisible" to hiring managers building GenAI products, making this one of the highest-value clusters in the taxonomy.
- **Cluster: Vector databases** — surface forms: Pinecone, Weaviate, Qdrant, pgvector, FAISS, vector database, vector store.
- **Cluster: RAG orchestration** — surface forms: LangChain, LlamaIndex, LangGraph, retrieval pipeline, chunking strategy, reranking, hybrid retrieval (BM25 + dense).
- **Cluster: RLHF / alignment fine-tuning** — surface forms: RLHF, DPO, reinforcement learning from human feedback, direct preference optimization, alignment fine-tuning.
- **Cluster: Prompt engineering** — surface forms: prompt engineering, prompt design, few-shot prompting, chain-of-thought.

### Category: Inference & Serving
- **Cluster: LLM serving engines** — surface forms: vLLM, TensorRT-LLM, Triton Inference Server, Ollama, TGI (Text Generation Inference).
- **Cluster: Quantization / compression** — surface forms: quantization, GPTQ, AWQ, model compression, distillation, pruning.
- **Cluster: Inference optimization** — surface forms: KV-cache optimization, batching, latency optimization, throughput optimization.

### Category: MLOps & Lifecycle
- **Cluster: Experiment tracking** — surface forms: MLflow, Weights & Biases, experiment tracking.
- **Cluster: Orchestration** — surface forms: Kubeflow, Airflow, Prefect, Ray, pipeline orchestration.
- **Cluster: Cloud ML platforms** — surface forms: AWS SageMaker, GCP Vertex AI, Azure ML.
- **Cluster: Containerization / deployment infra** — surface forms: Docker, Kubernetes, CI/CD for models, model registry.
- **Cluster: Monitoring** — surface forms: model monitoring, drift detection, data drift, production monitoring.

(Research note: current analysis of 2026 AI engineer postings found that 82% mention deployment or MLOps explicitly — a resume that stops at model training without any deployment-adjacent vocabulary under-signals for the majority of postings. This justifies weighting the MLOps category meaningfully for the MLE and Data Engineer role tracks specifically.)

### Category: Evaluation & Safety
- **Cluster: LLM evaluation frameworks** — surface forms: Ragas, DeepEval, LangSmith, offline evaluation, online evaluation.
- **Cluster: Safety / guardrails** — surface forms: guardrails, hallucination measurement, red-teaming, prompt-injection defense.

### Category: Classical Data Science
- **Cluster: Statistical modeling** — surface forms: statistical modeling, hypothesis testing, A/B testing, causal inference.
- **Cluster: Classical ML** — surface forms: scikit-learn, gradient boosting, XGBoost, LightGBM, random forest.
- **Cluster: Data engineering tooling** — surface forms: Spark, Polars, DuckDB, dbt, Airflow (cross-referenced with the Orchestration cluster above).

---

## 3. Role-Track Weighting

The same skill cluster should not carry equal weight across every role track — this is the direct justification for the role-track selector in `product_requirements.md` §5. Seed weighting guidance, to be refined once the system is tested against real postings:

| Category | MLE | Applied Scientist | Data Scientist | ML Research | Data Engineer |
|---|---|---|---|---|---|
| Core ML Foundations | High | High | Medium | High | Low |
| LLM / GenAI | High | High | Medium | High | Low |
| Inference & Serving | High | Medium | Low | Low | Medium |
| MLOps & Lifecycle | High | Medium | Low | Low | High |
| Evaluation & Safety | Medium | High | Low | High | Low |
| Classical Data Science | Low | Medium | High | Medium | Medium |

This table is a **starting hypothesis**, not a finished weighting scheme — it should be validated against a labeled set of real job postings per role track during the evaluation phase (see `evaluation_framework.md`, a Tier 2/3 document not yet written).

---

## 4. Maintenance Model

This taxonomy will go stale without deliberate upkeep — ML/DS tooling terminology changes faster than almost any other technical domain (RAG and LoRA-adjacent vocabulary barely existed in job postings three years before this document was written). Treat this as a living artifact:

- New clusters should be added whenever the free-layer scoring flags a resume/JD pair with a high volume of unmatched terms on both sides, since that's a direct signal of a taxonomy gap.
- Each cluster's surface-form list should expand whenever the semantic-similarity fallback (see §1) is repeatedly catching a phrasing that would be faster and more precise as an explicit surface form.

---

## 5. What This Spec Deliberately Does Not Solve

- **Non-ML/DS technical domains** (general backend, frontend, mobile). Explicitly out of scope, per `product_requirements.md` §4 — this taxonomy is intentionally narrow.
- **Soft skills / behavioral competencies.** This taxonomy is hard-skill-only by design; ESCO-style "attitudes" are not modeled here.
- **Seniority inference from skill list alone.** Handled separately in `job_description_analysis.md` §4 as a distinct signal, not part of this taxonomy.
