# Backend image. Build context = repo root.
#   docker build -f backend/Dockerfile .                      -> corpus generated + ingested on first start
#   docker build -f backend/Dockerfile --build-arg PREBUILD=1 . -> corpus, indexes and models baked in (fast cold start,
#                                                                 used for the Hugging Face Space)
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* && useradd -m -u 1000 app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_CACHE_DIR=/tmp/uv HF_HOME=/app/var/hf YOKOTEN_ROOT=/app \
    PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY data/glossary.json /app/data/glossary.json
COPY eval/ /app/eval/
RUN uv sync --frozen --no-dev && mkdir -p /app/var && chown -R app:app /app
USER app
ARG PREBUILD=0
RUN if [ "$PREBUILD" = "1" ]; then uv run --no-sync yokoten gen-data && uv run --no-sync yokoten ingest; fi
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync uvicorn yokoten.api:app --host 0.0.0.0 --port ${PORT}"]
