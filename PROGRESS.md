# Progress

Single source of truth for resuming. Current phase: **P4 Website** (next).

- [x] Questions asked and answered (docs/SETUP_ANSWERS.md)
- [x] Project folder, git init, local identity, .gitignore, .env / .env.example
- [x] Plan written to docs/ARCHITECTURE.md (approval step skipped per autonomy rules)
- [x] P0 Setup — uv backend (FastAPI /api/health + test), Next.js 16 + shadcn shell (nav, dark mode, backend status), tasks.ps1, CI, Dockerfiles + compose, docs skeleton
- [x] P1 Data — seeded generator (231 docs: 105 PDF, 51 DOCX, 31 XLSX, 26 MD, 10 PNG drawings, 8 JPG inspection scans), manifest.json, eval/golden.jsonl (129 Q, 10 categories, dev 51 / test 78)
- [x] P2 Ingestion — loaders, OCR (EasyOCR; Tesseract auto-detected), 4 chunkers, entities + NER, FMEA rows, embeddings cache, FAISS flat/hnsw + Chroma + BM25 + RRF; `yokoten ingest` / `yokoten search`. Full ingest: 231 docs, 2,221 parent-child chunks, 45 figures, 84 FMEA rows, OCR mean conf 0.891, ~8 min on CPU (first run incl. model downloads)
- [x] P3 RAG core — condense/expand/filters/zero-shot intent → hybrid retrieval → cross-encoder rerank → relevance gate → small-to-big + revision awareness → versioned prompt → streamed answer → NLI sentence check → confidence → trace. Providers groq/gemini/ollama/local (+SQLite LLM cache). SSE /api/chat, /api/search, documents, traces, feedback; `yokoten ask`. Verified with provider=local (no keys yet): correct answers, gate abstention, SSE streaming; 24 tests
- [ ] P4 Website
- [ ] P5 Evaluation
- [ ] P5b NHTSA recalls collection (approved licence: US public domain)
- [ ] P6 Next-level (K text-to-SQL → N access control → M SME verification)
- [ ] P7 Polish & ship

## Next step
P4 website: /chat (SSE, citations, source viewer, trace panel, feedback), /search (facets, highlights, scores), /library (+ upload, [id] view with chunks/OCR before-after), /onboarding (digest API needed), /eval (needs P5 results API), /settings, landing /.

## Half-finished work
None.
