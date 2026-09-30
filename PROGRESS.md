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
- [ ] P5 Evaluation — harness/metrics/report/API/dashboard done; first run stopped (gate calibration over-fit, fixed); FINAL run in progress -> var/eval2.log (public-data ingest, then `yokoten eval --gen-limit 40` with local Qwen because no API keys)
- [ ] P5b NHTSA recalls — converter + CLI (`.	asks.ps1 public`) + separate index + public eval done; ingest running in the same background job
- [ ] P6 — K/N/M implemented + integration tests green (37 passed); UI for K/N/M not yet driven in the browser
- [ ] P7 Polish & ship

## Next step
1. Wait for `eval-exit=` in var/eval2.log (~3 h: ablations ~50 min, generation 3 configs x 40 Q + 16 SQL-experiment Q with local LLM, OCR ~10 min). Rerun is cheap: ablation summaries cached in var/eval_cache, LLM calls cached in SQLite.
2. Then: set RuntimeConfig defaults to the chosen config (chunking + calibrated threshold), `yokoten eval --report-only` if needed, check docs/EVALUATION_REPORT.md + README results block, drive /eval, K (SQL table), N (role switcher), M (verify) in Chrome with scripts/ui_drive.py, commit P5 + P6.
3. P7: INTERVIEW_PREP.md + RESUME_BULLETS.md (numbers from eval/results/latest.json only), fill PRESENTATION_OUTLINE results, CI check, Docker (not installed -> BLOCKERS), final commit.

## Half-finished work
None uncommitted except the running eval.
