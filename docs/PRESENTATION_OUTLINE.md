# Presentation outline (~10 slides, 10 minutes)

Audience: engineering / IT managers and the internship panel. Tone: problem-first, evidence-heavy, honest about
limits. All numbers come from `docs/EVALUATION_REPORT.md` (same run as the README).

1. **The problem** — New engineers spend hours finding past failures, lessons and test data scattered across 8Ds,
   FMEAs, test reports, design reviews and scans; repeated failures are the expensive result. *(One photo-free slide:
   a timeline "same failure mode, two projects, two years apart".)*
2. **What Yokoten does** — Ask in plain English → cited answer, or "not in the knowledge base". Live demo cue
   (30 s): root-cause question → click citation → highlighted page.
3. **The data** — Fictional Tier-1 supplier, 231 documents in 6 formats (incl. noisy scans), generated from 32
   engineering cases so every cross-document question has a known answer; 129-question golden set (dev/test);
   optional real NHTSA recalls collection.
4. **Architecture** — Ingestion (loaders, OpenCV + OCR, 4 chunkers, embeddings, FAISS/Chroma/BM25) → RAG pipeline
   (condense, expand, filters, intent, hybrid retrieval, rerank, gate, small-to-big, versioned prompt, NLI check) →
   FastAPI + Next.js. Every step is in the trace.
5. **Trust by design** — citations to page + passage; relevance gate calibrated on dev; sentence-level NLI
   verification; revision awareness; prompt-injection-aware prompt; role-based access (also enforced in SQL).
6. **How it was evaluated** — metric definitions (Recall@k, MRR, nDCG, faithfulness, abstention, hallucination
   rate), dev/test split, greedy one-variable ablations, LLM-as-judge from a different model family when available.
7. **Results** — headline table from the report + the ablation chart; call out which design choices moved the needle
   and which did not (e.g. embedding model differences disappear behind the reranker).
8. **Where it fails** — 3 real failure cases from the error analysis (OCR single-character fields, list questions
   that need every document, small-model citation behaviour) and the fix for each.
9. **Scaling inside a real company** — PLM/DMS connectors, SSO + document ACLs, on-prem GPU LLM, feedback → golden
   set, weekly regression eval (docs/FUTURE_WORK.md).
10. **What I would do in the internship** — week-by-week: connect one real document source, build a 100-question
    golden set with SMEs, run the same eval, pilot with 5 new engineers, measure time-to-answer before/after.

Backup slides: prompt changelog (v1 → v2), latency breakdown per stage, OCR before/after images, text-to-SQL example.
