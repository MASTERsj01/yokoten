# Stage a Hugging Face Space (Docker SDK) for the backend in var\hf-space. Does NOT push anything.
# Usage: .\scripts\prepare_hf_space.ps1 -FrontendOrigin https://yokoten.vercel.app
param([string]$FrontendOrigin = "https://yokoten.vercel.app")
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $root "var\hf-space"
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null
foreach ($p in "backend", "eval") {
    robocopy (Join-Path $root $p) (Join-Path $out $p) /E /XD .venv __pycache__ .pytest_cache .ruff_cache /NFL /NDL /NJH /NJS | Out-Null
}
New-Item -ItemType Directory -Force (Join-Path $out "data") | Out-Null
Copy-Item (Join-Path $root "data\glossary.json") (Join-Path $out "data\glossary.json")
# Space image: corpus + indexes + models baked in, read-only demo mode, CORS for the Vercel frontend
$docker = (Get-Content (Join-Path $root "backend\Dockerfile") -Raw) -replace "ARG PREBUILD=0", "ARG PREBUILD=1"
$docker = $docker -replace "PYTHONUNBUFFERED=1 PORT=8000", "PYTHONUNBUFFERED=1 PORT=8000 DEMO_MODE=true AUTO_INGEST=false CORS_ORIGINS=$FrontendOrigin"
# models are baked in by the prebuild step: at runtime never block on the Hub
$docker = $docker -replace "EXPOSE 8000", "ENV HF_HUB_OFFLINE=1`nEXPOSE 8000"
[IO.File]::WriteAllText((Join-Path $out "Dockerfile"), $docker.Replace("`r`n", "`n"))
$readme = @"
---
title: Yokoten API
emoji: 🏭
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
license: mit
short_description: Engineering lessons-learned RAG copilot (API)
---

Backend of Yokoten - see the GitHub repository for the source, the web UI and the evaluation report.
Set GROQ_API_KEY (and optionally GOOGLE_API_KEY) as Space secrets.
"@
[IO.File]::WriteAllText((Join-Path $out "README.md"), $readme.Replace("`r`n", "`n"))
Write-Host "Staged Space in $out. Push it with the commands in docs/DEPLOYMENT.md."
