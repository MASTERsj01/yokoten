# Decisions log

One line per decision: what, and why.

- 2026-09-30 — Plan-approval step skipped per the user's autonomy rules; the plan lives in docs/ARCHITECTURE.md.
- 2026-09-30 — Python 3.12 (installed) with `requires-python >=3.11,<3.13`; the uv lockfile pins every version.
- 2026-09-30 — CPU torch from the PyTorch CPU index on Linux and Windows: identical behaviour to the CPU-only hosted demo, avoids ~3 GB of CUDA wheels, and C: has <19 GB free. The code still auto-detects CUDA (`config.device()`).
- 2026-09-30 — uv cache and HF_HOME on D:\yokoten-cache (set in the machine-local .env, loaded by tasks.ps1 and config.py) to keep large artefacts off C:.
- 2026-09-30 — Task runner is `tasks.ps1` (PowerShell 5.1+/pwsh, no extra installs), per the user's Windows constraint.
- 2026-09-30 — FastAPI's native `EventSourceResponse` (fastapi 0.142) for SSE instead of sse-starlette: one fewer dependency.
- 2026-09-30 — The frontend calls the backend directly via `NEXT_PUBLIC_API_URL` + CORS (no Next rewrites), so SSE isn't buffered by a proxy on Vercel.
- 2026-09-30 — shadcn/ui with the Radix base and the Nova preset; brand colour is steel blue; the "横" monogram is original branding.
- 2026-09-30 — No LangGraph: the pipeline is a linear sequence of steps with one branch (SQL vs retrieval), and plain functions + LCEL are simpler to trace.
- 2026-09-30 — Source viewer renders PDF pages server-side (PyMuPDF → PNG with highlight rectangles) instead of pdf.js in the browser.
- 2026-09-30 — Fictional company "Norvane Automotive Systems" (4 plants, 10 components, 10 suppliers, 4 OEMs, all invented). 32 hand-written quality cases each drive a consistent set of documents (8D, lessons learned, test report, ECN, DFMEA row, FFA, supplier-quality status), so multi-hop questions have guaranteed answers.
- 2026-09-30 — Golden set is derived from the generator's ground truth, not written by hand: 129 questions across 10 categories (20 unanswerable = 15.5%), stratified 40/60 dev/test split, seed 42. Correctness uses "answer facts" (key strings with `|` alternatives, word-boundary matched) plus an optional LLM judge.
- 2026-09-30 — Retrieval gold is expressed as groups of acceptable doc IDs (one group per hop), so Recall@k = share of hops covered; this is independent of the chunking strategy being ablated.
- 2026-09-30 — Scans carry only DMS-style metadata in manifest.json (id, title, type, year, classification); part number, revision and material must come from OCR title-block parsing. A test enforces that OCR-question answers never appear in text documents.
- 2026-09-30 — PDFs rendered with PyMuPDF Story (HTML/CSS -> PDF), so no reportlab dependency; fonts for scans are matplotlib's bundled DejaVu, so generation is identical on Windows, Linux and in Docker. Output is byte-reproducible (fixed metadata dates, seeded RNGs).
- 2026-09-30 — The corpus (~40 MB) is gitignored and regenerated with `.\tasks.ps1 data` (~30 s); eval/golden.jsonl is committed.
