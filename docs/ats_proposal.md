# ATS Checker — Project Proposal

## 1. The $10k Website Pattern (Source Material)

A breakdown of six single-page websites that generate meaningful passive revenue, used as the founding reference case for this project.

- **10MinuteEmail.com** — Provides temporary email addresses. ~1.1 million monthly visitors, estimated ~$2,450/month via display advertising.
- **DisPrices.com** — Helps users find deals on discs. Reported ~$5,000/month, updates automatically, minimal maintenance.
- **WeirdOrConfusing.com** — Recommends unusual Amazon products. Combines display ads and Amazon affiliate links, estimated ~$4,200/month.
- **HackerTyper.com** — A "fake hacking" simulator for entertainment. Generates revenue through job board listings and affiliate links for cybersecurity roles.
- **TheUselessWeb.com** — A hub directing users to other random "useless" websites. Estimated ~$13,000/month.
- **DownForEveryoneOrJustMe.com** — A tool to check if a website is offline. The most profitable example, estimated 39,000+/month from advertising.

**Key takeaway from the source material:** success with one-page websites relies less on the site's size and more on the uniqueness of the idea and the quality of execution. Simple tools or niche content can achieve massive traffic and financial success.

**Core strategies identified in the source material:**

- **Solving a Specific Problem or Utility** — each site performs a singular, focused task (temporary email, uptime check, a specific simulator).
- **Monetization Diversity** — display advertising (RPM-based), affiliate marketing (Amazon Associates), or specialized directories/referrals (e.g. HackerTyper's job board and cybersecurity affiliate links).
- **Low Maintenance** — automated content or simple, static designs requiring minimal ongoing effort from the owner.

---

## 2. Why These Sites Actually Work

Stripped of the "one page" framing, that's an implementation detail, not the reason.

1. **Zero friction, instant utility.** No signup, no explanation needed, you land on the page and the tool does the one thing in under 10 seconds. Friction kills traffic-driven monetization because ad revenue and affiliate clicks both depend on volume, not depth of engagement.

2. **The problem is universal, not niche.** "Is this website down for everyone or just me" isn't a niche question, basically every internet user has typed some version of that search at some point. That's the actual engine behind the $39k/month number. It's not a good idea, it's a question millions of people already google.

3. **The traffic source is search intent, not marketing.** None of these get discovered through social media or content marketing. They rank for a specific, high-volume search query, and the query itself brings the visitor already wanting exactly that thing. This is why "solve one specific problem" matters more than "solve it well", you're optimizing for matching a search query, not for depth.

4. **Low maintenance is a consequence, not a goal.** Because the tool does one narrow thing, there's little to break and little to update. That's what makes the revenue passive rather than a second job.

5. **Monetization rides on volume, so the tool itself doesn't need to be valuable per-use, it needs to be used constantly.** A million people checking a temp email once and leaving is worth more in ad RPM than a smaller group of engaged power users.

---

## 3. Why an ATS Checker

Five one-page tool ideas were originally brainstormed against these principles (AI text detector, shadowban checker, password/breach checker, resume ATS checker, universal file converter), and researched for real competition and demand signal. The ATS checker was selected over the others for three reasons:

- **Proven willingness to pay.** The market leader, Jobscan, charges $49.95/month and has real paying customers. This isn't a speculative monetization model, the category already generates revenue at scale.
- **A genuine, underserved niche.** Every existing free tier is stingy (Jobscan: 3–10 scans/month; SkillSyncer: 1/week), and every tech-specific competitor targets generic software engineering, not ML/DS/AI roles specifically.
- **Direct personal fit.** This plays to an actual unfair advantage: an ML/data science background capable of building genuine semantic matching (rather than the keyword-string-matching every competitor still uses), combined with being an active job-seeker in exactly this niche, meaning the pain points are lived, not guessed at.

It was chosen over a from-scratch modern Overleaf alternative (also researched and validated as a real pain point, but a much larger, longer-horizon SaaS build) as the near-term priority project, given the timeline and the goal of reaching first revenue quickly.

---

## 4. Competitive Research

### What the research surfaces about competitors, Jobscan specifically (the market leader)

- **The match score doesn't reliably predict outcomes.** A Reddit user scored 98% and was rejected within an hour. Another logged 100 applications and got callbacks at match rates as low as 51%, meaning the score has weak correlation with what it claims to predict. Critics, including a hiring manager, say real ATS platforms "work nothing like Jobscan."
- **It's literal keyword matching, not semantic.** Users report it doesn't recognize word tense variants or exact-term differences ("Node.js" vs "NodeJS" may not score the same). This pushes people toward keyword stuffing to game the score, which then hurts readability for the actual human reviewer, a tension multiple reviews flag directly.
- **Pricing and trust problems.** $49.95/month, 3 to 4x the category. Documented Trustpilot complaints about auto-renewal without notice and charges after cancellation. BBB rating of C-.
- **Thin free tier.** 3 to 10 scans/month, enough to try it, not enough to actually iterate on a resume.

### What was found on tech-specific competitors (the important part)

Software-engineer-specific ATS checkers already exist (Resume Optimizer Pro, ATSAlign, QuickResumeAI, WisGrowth). So "SWE-specific" isn't unclaimed. But look at how every single one of them describes their own method: "exact keyword matches," "mention those exact terms," "ATS systems score frequency." They are all explicitly, proudly doing literal string matching. None claim real semantic understanding. And none of them are ML/DS-specific, they're generic backend/full-stack SWE, with zero handling for the vocabulary problem that's actually worse in ML than plain software engineering: a resume that says "fine-tuned a transformer with LoRA" and a job description that says "parameter-efficient fine-tuning experience" are describing the same skill in different words, and a literal matcher scores that as a miss.

### The state-of-the-art angle, concretely

1. **Real semantic matching, not string matching.** Use embeddings to recognize that "RAG," "retrieval-augmented generation," and "vector search over a knowledge base" are the same underlying competency. This is a real, buildable technical advantage, and it's the single most-repeated complaint about every competitor in the research.

2. **ML/DS-specific keyword taxonomy, not generic tech.** PyTorch/TensorFlow equivalence, quantization/distillation/pruning as a cluster, MLOps tooling (MLflow, Kubeflow, SageMaker), LLM-specific terms (RAG, LoRA, RLHF, vLLM). None of the existing tools model this domain at all.

3. **Transparency over a black-box score.** Given that the core complaint about every competitor is "the score doesn't predict what happens," don't just output a number. Show the actual matched and unmatched terms, and be explicit that the score measures keyword/skill alignment, not interview odds. A scoped, honest claim beats an inflated one that gets publicly debunked on Reddit.

4. **Simulate actual parser behavior** (Workday, Greenhouse, Lever, Ashby column/table parsing failures) rather than a generic heuristic. This is checkable and demonstrable, and it's the concrete promise several competitors make but Jobscan's own reviewers say doesn't hold up.

5. **Content quality signal alongside keyword matching**, so the tool doesn't just reward stuffing. Flag when a suggestion would hurt readability. This directly answers the "you can win the scanner and lose the recruiter" complaint that shows up in the research repeatedly.

6. **Fair access model.** Given the auto-renewal and hidden-pricing complaints are a real, documented trust problem for the category leader, a generous free tier and transparent one-time or simple pricing is itself a differentiator, not just a nice-to-have.

**Positioning:** not "another ATS checker," but the first one built around real semantic matching for a domain (ML/DS/AI) where literal keyword tools structurally fail.

---

## 5. Proposed System Design (Draft — architecture to be refined later)

> This section is a first-pass plan for how the product could be structured to satisfy both the $10k-site principles and the "state of the art" positioning above. It is intentionally a draft. The actual architecture, tech stack, and implementation details will be worked out separately before building.

### The core tension, and how it's resolved

The five site principles describe a static, no-signup, single-purpose page. A state-of-the-art RAG-powered ML/DS resume analyzer sounds like the opposite: deep, stateful, and paid. The resolution is to build it as **two layers**, not one, where the free layer earns the traffic and the RAG layer earns the money.

### Layer 1: The Front Door (free, honors the five principles literally)

- Two text boxes: paste resume, paste job description. No file upload required (though optionally allowed), no signup, no account.
- Click once, get a score in under 3 seconds.
- The score computation must **not** call an LLM at request time, since that breaks principle 4 (low maintenance, near-zero marginal cost) and principle 5 (needs to survive volume). Instead:
  - **Semantic match score** — precomputed sentence embeddings (a small, fast open-source embedding model, not an API call) compared via cosine similarity between resume and job description. Cheap, instant, no LLM cost per request.
  - **Skill taxonomy overlap** — a curated, hand-built ML/DS synonym graph (PyTorch ~ TensorFlow ~ deep learning framework, LoRA ~ parameter-efficient fine-tuning, RAG ~ retrieval-augmented generation ~ vector search) checked deterministically against both texts. A lookup table, not an LLM call, so it's free to run at any volume.
  - **ATS parseability check** — a deterministic structural scan (multi-column detection, tables, images, non-standard section headers) simulating how Workday/Greenhouse/Lever/Ashby actually extract text. Regex and layout analysis, not ML at all.
- This layer is what ranks for "free resume checker" and "ATS score checker for data scientists", the high-volume search-intent traffic. It's genuinely free to run at scale because nothing in it calls a paid API per request.

### Layer 2: The RAG-Powered Deep Report (paid, where "state of the art" and the revenue live)

This is the honest use of RAG: grounded, specific feedback rather than generic LLM output, which is what makes it defensible against the "opaque score, generic advice" complaint that plagues every competitor.

**Retrieval corpus** (built once, reused for every user):

- The same ML/DS skill taxonomy from Layer 1, but richer, with example phrasings from real strong ML resumes for each skill cluster.
- ATS platform-specific parsing quirks and documented failure modes (per platform, since Workday and Greenhouse fail differently).
- A curated set of strong vs. weak bullet-point examples by category (model deployment, research, MLOps, data pipelines).

**Flow:** when a user requests the deep report (the paid action), the system retrieves the taxonomy entries and example bullets relevant to their specific resume/JD pair, feeds those retrieved facts plus the resume and JD into an LLM, and asks it to explain matches, flag genuinely missing skills, and suggest rewrites, grounded in the retrieved examples rather than the model inventing generic advice. This directly fixes the two loudest competitor complaints from the research: the score is explainable (you can see exactly which retrieved equivalence justified each match), and the suggestions are specific to ML/DS phrasing, not generic "add more keywords."

### Additional Features (priority order)

1. **Role-track selector** (MLE / Applied Scientist / Data Scientist / ML Research / Data Engineer), each with its own taxonomy weighting, since these roles genuinely value different vocabulary.
2. **ATS platform selector**, showing platform-specific parsing warnings rather than a generic one.
3. **Anti-keyword-stuffing flag** — if a suggested edit would hurt readability score, say so. Directly answers the "you can win the scanner and lose the recruiter" complaint.
4. **Multi-JD comparison** — paste your resume once, compare against several target postings (useful when applying to multiple MAANG-style roles at once).
5. **Downloadable rewrite diff** — not a full resume builder, just a clear before/after of the specific lines the report flagged.

### Traffic and Monetization Structure, Mapped to the Five Principles

- **Principle 2 (universal problem):** the free layer is generic enough ("check my resume against this job") to rank for broad searches, not just ML-niche ones. The ML/DS specialization shows up once the user sees the platform selector and role tracks, not as a barrier to entry.
- **Principle 3 (search intent, not marketing):** build dedicated landing pages per role and per platform ("ATS checker for machine learning engineers," "ATS checker for Workday"), since those are exactly the long-tail queries competitors aren't targeting with real semantic matching behind them.
- **Principle 5 (volume-based revenue):** the free layer carries ads and functions as the volume engine. The RAG deep report is the paid conversion point. A one-time fee or small credit pack fits better than a subscription, given the documented backlash against Jobscan's $49.95/month and auto-renewal complaints, undercutting that trust problem is itself a differentiator.
- **Principle 4 (low maintenance):** only the paid path touches an LLM API, so ongoing cost scales with paying users, not free traffic, which is the actual constraint that makes the free layer sustainable at volume.

### Summary

A genuinely zero-friction, ad-supported front door built on cheap deterministic and embedding-based scoring, sitting in front of a real RAG system that is the actual product differentiation and the actual revenue.
