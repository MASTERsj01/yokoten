# Progress

Single source of truth for resuming. Current phase: **done locally** - remaining items need the user (BLOCKERS.md).

- [x] Questions asked and answered (docs/SETUP_ANSWERS.md)
- [x] Project folder, git init, local identity, .gitignore, .env / .env.example
- [x] Plan written to docs/ARCHITECTURE.md (approval step skipped per autonomy rules)
- [x] P0 Setup — uv backend (FastAPI /api/health + test), Next.js 16 + shadcn shell (nav, dark mode, backend status), tasks.ps1, CI, Dockerfiles + compose, docs skeleton
- [x] P1 Data — seeded generator (231 docs: 105 PDF, 51 DOCX, 31 XLSX, 26 MD, 10 PNG drawings, 8 JPG inspection scans), manifest.json, eval/golden.jsonl (129 Q, 10 categories, dev 51 / test 78)
- [x] P2 Ingestion — loaders, OCR (EasyOCR; Tesseract auto-detected), 4 chunkers, entities + NER, FMEA rows, embeddings cache, FAISS flat/hnsw + Chroma + BM25 + RRF; `yokoten ingest` / `yokoten search`. Full ingest: 231 docs, 2,221 parent-child chunks, 45 figures, 84 FMEA rows, OCR mean conf 0.891, ~8 min on CPU (first run incl. model downloads)
- [x] P3 RAG core — condense/expand/filters/zero-shot intent → hybrid retrieval → cross-encoder rerank → relevance gate → small-to-big + revision awareness → versioned prompt → streamed answer → NLI sentence check → confidence → trace. Providers groq/gemini/ollama/local (+SQLite LLM cache). SSE /api/chat, /api/search, documents, traces, feedback; `yokoten ask`. Verified with provider=local (no keys yet): correct answers, gate abstention, SSE streaming; 24 tests
- [x] P4 Website — landing, chat (SSE, citations, source viewer, trace, feedback, sessions), search (facets, highlights, scores), library (+upload, per-doc view, OCR before/after), onboarding digest, settings, eval dashboard shell; verified in Chrome via scripts/ui_drive.py (light/dark/mobile)
- [x] P5 Evaluation — `yokoten eval` (ablations on dev, retention-constrained gate calibration, generation x3 configs, SQL on/off, validated faithfulness checker, uncached latency benchmark, OCR engines, public set) -> eval/results/latest.json, docs/EVALUATION_REPORT.md, README results, /eval dashboard. Headline (test): R@5 98.4%, MRR 93.2%, correctness 74.3%, faithfulness 74.1%, hallucination 28.9% (local 1.5B model).
- [x] P5b NHTSA recalls — 1,500 campaigns in collection `public_recalls` (separate index), 20-question public eval (R@5 70%).
- [x] P6 — K text-to-SQL (analytical correctness 62.5% vs 12.5% without), N role-based access (retrieval/search/library/SQL, header switcher), M SME verify/correct + boosting + feedback analytics; verified in Chrome.
- [x] GitHub: https://github.com/MASTERsj01/yokoten (public, topics, CI on push)
- [x] P7 Polish (local) — README (results from the run, keyword → code table), ARCHITECTURE, DECISIONS, EVALUATION_REPORT, DEMO_SCRIPT, PRESENTATION_OUTLINE, FUTURE_WORK, RESUME_BULLETS, INTERVIEW_PREP, DEPLOYMENT, LICENSE; Docker files + HF Space staging script (unverified: Docker not installed); deployment/push waiting for approval

## Next step
Waiting on the user (BLOCKERS.md): API keys → re-run `.	asks.ps1 eval --gen-limit 40 --provider groq`; Docker → verify `docker compose up --build`; go-ahead for Vercel / HF Space deployment. Optional after that: J (CLIP visual similar-defect finder) as a stretch goal.

## Half-finished work
None.
