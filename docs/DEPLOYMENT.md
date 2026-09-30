# Deployment

Target: **frontend on Vercel**, **backend on a Hugging Face Space (Docker, free CPU)**, running in read-only demo mode
with per-IP rate limits. Nothing here runs automatically - each step below is done by the repository owner.

## 1. Backend — Hugging Face Space

> Since 2026 Hugging Face requires a **PRO subscription** for Docker (and Gradio) Spaces, including on free CPU
> hardware - creating one on a free account returns `402 Payment Required`. Only static Spaces stay free.

1. Create a Hugging Face account with PRO and a new **Space**: SDK *Docker*, hardware *CPU basic*,
   name e.g. `yokoten-api`.
2. In the Space settings → *Variables and secrets*, add the secret `GROQ_API_KEY` (and optionally `GOOGLE_API_KEY`).
3. Stage the Space folder locally (copies the backend, bakes corpus + indexes + models into the image at build time,
   sets `DEMO_MODE=true` and CORS for the Vercel URL):
   ```powershell
   .\scripts\prepare_hf_space.ps1 -FrontendOrigin https://<your-vercel-app>.vercel.app
   ```
4. Push it (needs `git` + a Hugging Face access token with write scope):
   ```powershell
   cd var\hf-space
   git init -b main; git add -A; git commit -m "Yokoten API"
   git remote add origin https://huggingface.co/spaces/<hf-user>/yokoten-api
   git push -u origin main
   ```
   The first build takes ~20-30 min (dependency install, corpus generation, OCR, embedding). The API is then at
   `https://<hf-user>-yokoten-api.hf.space` (OpenAPI docs at `/docs`).

Free Spaces sleep after ~48 h without traffic; the frontend shows a *"backend is waking up"* message while it
restarts.

## 2. Frontend — Vercel

1. Push the repository to GitHub (`yokoten`).
2. On vercel.com (sign in with GitHub) → *Add New Project* → import the repo → **Root Directory: `frontend`**.
3. Environment variables:
   - `NEXT_PUBLIC_API_URL` = `https://<hf-user>-yokoten-api.hf.space`
   - `NEXT_PUBLIC_GITHUB_URL` = `https://github.com/mastersj01/yokoten`
   - `NEXT_PUBLIC_DEMO_VIDEO_URL` = embed URL of the demo video (optional)
4. Deploy. Put the Vercel URL into the Space's CORS origin (step 1.3) if it differs.

## 3. Demo-mode guarantees

`DEMO_MODE=true` makes uploads, deletes, re-indexing, settings changes and SME verification return 403, and limits
POST requests to `RATE_LIMIT_PER_MIN` (default 20) per client IP. Chat, search, the library, onboarding and the
evaluation dashboard stay available.

## 4. One-command local Docker run

```bash
cp .env.example .env            # add GROQ_API_KEY (optional)
docker compose up --build       # UI :3000, API :8000; first start generates + ingests the corpus (~10 min on CPU)
docker compose --profile ollama up --build   # also starts a local Ollama server
```
On Windows with 15 GB RAM, cap WSL2 memory in `%UserProfile%\.wslconfig`:
```
[wsl2]
memory=8GB
processors=6
```
