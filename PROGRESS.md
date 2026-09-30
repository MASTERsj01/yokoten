# Progress

Single source of truth for resuming. Current phase: **P5 Evaluation** (eval run in progress).

- [x] Questions asked and answered (docs/SETUP_ANSWERS.md)
- [x] Project folder, git init, local identity, .gitignore, .env / .env.example
- [x] Plan written to docs/ARCHITECTURE.md (approval step skipped per autonomy rules)
- [x] P0 Setup — uv backend (FastAPI /api/health + test), Next.js 16 + shadcn shell (nav, dark mode, backend status), tasks.ps1, CI, Dockerfiles + compose, docs skeleton
- [x] P1 Data — seeded generator (231 docs: 105 PDF, 51 DOCX, 31 XLSX, 26 MD, 10 PNG drawings, 8 JPG inspection scans), manifest.json, eval/golden.jsonl (129 Q, 10 categories, dev 51 / test 78)
- [x] P2 Ingestion — loaders, OCR (EasyOCR; Tesseract auto-detected), 4 chunkers, entities + NER, FMEA rows, embeddings cache, FAISS flat/hnsw + Chroma + BM25 + RRF; `yokoten ingest` / `yokoten search`. Full ingest: 231 docs, 2,221 parent-child chunks, 45 figures, 84 FMEA rows, OCR mean conf 0.891, ~8 min on CPU (first run incl. model downloads)
- [x] P3 RAG core — condense/expand/filters/zero-shot intent → hybrid retrieval → cross-encoder rerank → relevance gate → small-to-big + revision awareness → versioned prompt → streamed answer → NLI sentence check → confidence → trace. Providers groq/gemini/ollama/local (+SQLite LLM cache). SSE /api/chat, /api/search, documents, traces, feedback; `yokoten ask`. Verified with provider=local (no keys yet): correct answers, gate abstention, SSE streaming; 24 tests
- [x] P4 Website — landing, chat (SSE, citations, source viewer, trace, feedback, sessions), search (facets, highlights, scores), library (+upload, per-doc view, OCR before/after), onboarding digest, settings, eval dashboard shell; verified in Chrome via scripts/ui_drive.py (light/dark/mobile)
- [ ] P5 Evaluation — harness/metrics/report/API written; full run started (`yokoten eval --gen-limit 40`, local LLM because no keys) -> var/eval.log
- [ ] P5b NHTSA recalls collection (approved licence: US public domain)
- [ ] P6 Next-level (K text-to-SQL → N access control → M SME verification)
- [ ] P7 Polish & ship

## Next step
1. Wait for var/eval.log to show `eval-exit=0` (ablations -> calibration -> generation x3 configs x 40 Q with local Qwen -> OCR). If it crashed, fix and rerun `.	asks.ps1 eval --gen-limit 40` (LLM calls are cached, so reruns are cheap).
2. Check eval/results/latest.json + docs/EVALUATION_REPORT.md, verify /eval page renders, run full tests, commit P5.
3. P6: K (rag/sql.py written, not wired: route intent=analytical -> text-to-SQL, trace.data.sql, UI table), N (role switcher in header; retrieval already filters by X-Role), M (SME verify/correct + boosting + feedback analytics).

## Half-finished work
rag/sql.py + prompts/sql_v1.md exist but are not wired into the pipeline yet (deliberately: P5 baseline first).
