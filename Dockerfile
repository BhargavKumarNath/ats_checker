# Layer 1 web process. Models are baked in at build time so a warm instance
# never downloads at request time. Layer 2 worker uses the same image with a
# different command and, unlike the web process, an ANTHROPIC_API_KEY.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/
WORKDIR /app

FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

FROM deps AS app
COPY src ./src
COPY taxonomy ./taxonomy
COPY corpus ./corpus
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" PORT=8080 ATSC_TAXONOMY_DIR=/app/taxonomy ATSC_MODEL_CACHE_DIR=/app/models
# Bake the Layer 1 embedding model into the image: no download at request time, ever.
RUN python -c "from atsc.core.scoring import warm; warm()"
# Bake the Layer 2 retrieval embedding model as well: the worker shares this image.
RUN python -c "from atsc.deep.retrieval import get_default_index; get_default_index()"
EXPOSE 8080
CMD ["sh", "-c", "uvicorn atsc.web.app:app --host 0.0.0.0 --port ${PORT}"]
