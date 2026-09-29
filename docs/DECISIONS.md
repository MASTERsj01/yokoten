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
