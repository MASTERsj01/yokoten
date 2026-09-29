# Progress

Single source of truth for resuming. Current phase: **P2 Ingestion** (next).

- [x] Questions asked and answered (docs/SETUP_ANSWERS.md)
- [x] Project folder, git init, local identity, .gitignore, .env / .env.example
- [x] Plan written to docs/ARCHITECTURE.md (approval step skipped per autonomy rules)
- [x] P0 Setup — uv backend (FastAPI /api/health + test), Next.js 16 + shadcn shell (nav, dark mode, backend status), tasks.ps1, CI, Dockerfiles + compose, docs skeleton
- [x] P1 Data — seeded generator (231 docs: 105 PDF, 51 DOCX, 31 XLSX, 26 MD, 10 PNG drawings, 8 JPG inspection scans), manifest.json, eval/golden.jsonl (129 Q, 10 categories, dev 51 / test 78)
- [ ] P2 Ingestion
- [ ] P3 RAG core
- [ ] P4 Website
- [ ] P5 Evaluation
- [ ] P5b NHTSA recalls collection (approved licence: US public domain)
- [ ] P6 Next-level (K text-to-SQL → N access control → M SME verification)
- [ ] P7 Polish & ship

## Next step
Start P2: `backend/yokoten/ingest/` (loaders, OCR, chunkers, entities) + `retrieval/` (embeddings, FAISS/Chroma, BM25) + db.py.

## Half-finished work
None.
