# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models/hf

WORKDIR /app

# Dependencies first for layer caching. No secrets are copied or baked into the image.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY config ./config
COPY data/mappings ./data/mappings
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data /models/hf \
    && chown -R appuser:appuser /app/data /models
USER appuser

# Optional: bake the embedding model into the image (large: ~2.3 GB for bge-m3).
ARG PRELOAD_MODELS=false
RUN if [ "$PRELOAD_MODELS" = "true" ]; then \
      python -c "from sentence_transformers import SentenceTransformer as S, CrossEncoder as C; S('BAAI/bge-m3'); C('cross-encoder/ms-marco-MiniLM-L-6-v2')"; \
    fi

ENV PORT=8000 WEB_CONCURRENCY=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=4)"

# One worker per container by default: each worker loads its own embedding model (~2 GB RAM).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY} --proxy-headers"]
