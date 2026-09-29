"""FastAPI app: REST + SSE. Run: uv run uvicorn yokoten.api:app --reload"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from yokoten import __version__
from yokoten.config import settings

app = FastAPI(title="Yokoten API", version=__version__, description="Engineering lessons-learned copilot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "demo_mode": settings.demo_mode}
