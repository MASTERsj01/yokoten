# Yokoten task runner (Windows PowerShell 5.1+ / pwsh). Usage: .\tasks.ps1 <task> [args]
param([Parameter(Position = 0)][string]$Task = "help", [Parameter(ValueFromRemainingArguments)][string[]]$Rest)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

# Load .env into the process (HF_HOME, UV_CACHE_DIR, ... stay machine-local).
$envFile = Join-Path $Root ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$' } | ForEach-Object {
        if ($Matches[2].Trim()) { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2].Trim() }
    }
}
if (-not $env:UV_LINK_MODE) { $env:UV_LINK_MODE = "copy" }

function Invoke-Py { Push-Location $Backend; try { uv run --no-sync @args; if ($LASTEXITCODE) { throw "failed: $args" } } finally { Pop-Location } }
function Invoke-Npm { Push-Location $Frontend; try { npm.cmd @args; if ($LASTEXITCODE) { throw "failed: npm $args" } } finally { Pop-Location } }

switch ($Task) {
    "setup" { Push-Location $Backend; uv sync; Pop-Location; Invoke-Npm install }
    "data" { Invoke-Py yokoten gen-data @Rest }
    "ingest" { Invoke-Py yokoten ingest @Rest }
    "ask" { Invoke-Py yokoten ask @Rest }
    "public" { Invoke-Py yokoten public-data @Rest }
    "eval" { Invoke-Py yokoten eval @Rest }
    "backend" { Invoke-Py uvicorn yokoten.api:app --reload --port 8000 }
    "frontend" { Invoke-Npm run dev }
    "dev" {
        Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "backend"
        Invoke-Npm run dev
    }
    "share" {
        # Public demo from this laptop: read-only backend on :8001 + Cloudflare quick tunnel (new URL every start).
        $site = if ($Rest) { $Rest[0] } else { "https://yokoten-eight.vercel.app" }
        $cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
        if (-not $cf) {
            $cf = Join-Path $Root "var\bin\cloudflared.exe"
            if (-not (Test-Path $cf)) {
                New-Item -ItemType Directory -Force (Split-Path $cf) | Out-Null
                Invoke-WebRequest "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cf -UseBasicParsing
            }
        }
        $log = Join-Path $Root "var\tunnel.log"
        Remove-Item $log -ErrorAction SilentlyContinue
        Start-Process powershell -WindowStyle Minimized -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "share-backend", $site
        Start-Process $cf -WindowStyle Minimized -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://localhost:8001", "--logfile", "`"$log`""
        $url = $null
        for ($i = 0; $i -lt 60 -and -not $url; $i++) {
            Start-Sleep 2
            if (Test-Path $log) { $url = ([regex]"https://[a-z0-9-]+\.trycloudflare\.com").Match((Get-Content $log -Raw)).Value }
        }
        if (-not $url) { throw "no tunnel URL after 2 min - see $log" }
        $link = "$site/?api=$url"
        Set-Clipboard $link
        "Share this link (copied to clipboard; works while this laptop and both minimized windows run):`n  $link"
    }
    "share-backend" {
        $env:DEMO_MODE = "true"; $env:CORS_ORIGINS = $Rest[0]
        Invoke-Py uvicorn yokoten.api:app --port 8001
    }
    "test" { Invoke-Py pytest -q @Rest }
    "lint" { Invoke-Py ruff check .; Invoke-Py ruff format --check .; Invoke-Npm run lint }
    "fmt" { Invoke-Py ruff check --fix .; Invoke-Py ruff format . }
    "build" { Invoke-Npm run build }
    default {
        "Tasks: setup | data | ingest | public | ask ""question"" | eval | dev | backend | frontend | share [site] | test | lint | fmt | build"
    }
}
