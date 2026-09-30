# Yokoten — AI knowledge copilot for engineering lessons learned

RAG chatbot + hybrid semantic search + evaluation harness over a synthetic Tier-1 automotive engineering corpus.
Portfolio project. The spec lives in `docs/PROJECT_BRIEF.md` + `docs/SETUP_ANSWERS.md` (both **local-only, gitignored,
confidential**: never commit them or quote the JD). The plan is in `docs/ARCHITECTURE.md`; status is in `PROGRESS.md`.

## Working mode
Autonomous: don't ask the user, don't wait between phases. Stop only for a missing secret, account creation / push /
deploy, unapproved data downloads, or anything destructive outside C:\dev\yokoten. Log decisions in `docs/DECISIONS.md`,
blockers in `BLOCKERS.md`. Per phase: build → lint + tests green → run the app and verify → commit → update PROGRESS.md.

## Commands (PowerShell, from repo root)
```
.\tasks.ps1 setup      # uv sync + npm install
.\tasks.ps1 data       # generate synthetic corpus + golden set
.\tasks.ps1 ingest     # build indexes
.\tasks.ps1 dev        # backend :8000 (new window) + frontend :3000
.\tasks.ps1 test | lint | fmt | build | eval
.\tasks.ps1 ask "question"
```
Backend alone: `cd backend; uv run --no-sync uvicorn yokoten.api:app --reload`. OpenAPI docs are at /docs.

## Where things live
- `backend/yokoten/` — config, db, api, cli, datagen/, ingest/, retrieval/, rag/, evaluation/
- `backend/prompts/` — versioned prompts + CHANGELOG
- `frontend/src/app/*` — pages; `frontend/src/lib/api.ts` — API client (`NEXT_PUBLIC_API_URL`)
- `var/` — runtime state (SQLite, indexes, renders, LLM cache), gitignored
- `data/corpus/` — generated corpus (gitignored); `eval/golden.jsonl` — golden set (committed)

## Conventions / gotchas learned
- Windows PowerShell 5.1: no `utf8NoBOM`, no `&&`. Write files with the Write tool; for scripted edits use Git Bash or Python.
- PowerShell function names are case-insensitive: a function named `Npm` that calls `npm` recurses forever (hence `Invoke-Npm`).
- `.env` holds HF_HOME / UV_CACHE_DIR on D: (C: is low on disk). tasks.ps1 loads .env into the process; config.py sets HF_HOME before any HF import.
- Library versions are newer than training data: transformers 5.x, sentence-transformers 6.x, LangChain 1.x, pandas 3, OpenCV 5, Next.js 16, FastAPI 0.142 (native SSE via `fastapi.sse.EventSourceResponse`). Check the installed source/docs before using an API. Next.js docs are bundled in `frontend/node_modules/next/dist/docs/`.
- Use `import pymupdf` (not `fitz`).
- To verify servers from the shell, use Git Bash background processes + curl, then kill listeners on ports 8000/3000.
- Ruff line length is 110.
- Bash tool: backslash escapes inside heredoc'd Python (e.g. "\n" in replacement strings) can arrive as real newlines - use the Edit tool for code containing escapes.
- Tests use an isolated VAR_DIR (tests/conftest.py); test_e2e ingests a ~40-doc subset (no NER/OCR). The LLM answer test is skipped unless GROQ_API_KEY or YOKOTEN_TEST_LLM=local.
- No API keys yet: llm.resolve() falls back groq -> gemini -> ollama -> local (Qwen2.5-1.5B on CPU, ~20-60 s/answer, rarely cites). Warm local model: `yokoten ask "..." --provider local`.
- Background ingest: run python with output redirected; use `python -u` or check SQLite `document.status` for progress (stdout is buffered).
- Stop servers with PowerShell (`Get-NetTCPConnection -LocalPort 3000 -State Listen | % { Stop-Process -Id $_.OwningProcess -Force }`); `taskkill` from Git Bash fails silently and a stale `next start` then serves old chunks (page never hydrates).
- UI verification: build + `npm run start`, backend on :8000, then `cd backend; uv run --no-project --with playwright python ../scripts/ui_drive.py <out_dir> < steps` (drives installed Chrome; prints console/page errors). CORS only allows :3000.
- Eval: `.	asks.ps1 eval --gen-limit 40` (~3 h on CPU with the local LLM). Ablation summaries cached in var/eval_cache (key includes index_version), LLM calls cached in SQLite `llmcache` - reruns are cheap. `--report-only` re-renders docs/EVALUATION_REPORT.md + README results block from eval/results/latest.json.
- Indexes are per (chunking, embedding model, collection set); NHTSA recalls live in collection `public_recalls` (`.	asks.ps1 public`).
- Never edit prompt files while an eval is running (they are read at call time).
