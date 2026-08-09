# resumaker API image. Deploy-agnostic: runs on any host with Docker.
#
# Notes:
#  - LLM engine on a headless VM is the Anthropic API (no Claude CLI to authenticate);
#    set RESUMAKER_DEFAULT_PROVIDER=anthropic + ANTHROPIC_API_KEY in .env.
#  - LibreOffice (headless) renders .docx -> .pdf; Carlito is the metric-compatible
#    Calibri substitute so the PDF layout matches the desktop output.
#  - Playwright is intentionally omitted (the scraper's public-API path covers the
#    supported boards); add the `scrape` extra + browsers only if you need the fallback.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    RESUMAKER_ENVIRONMENT=vm \
    RESUMAKER_DATA_DIR=/data \
    RESUMAKER_OUTPUT_DIR=/outputs

RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer fonts-crosextra-carlito \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first (cached layer) from the lockfile - core + api extras, no dev.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra api --no-install-project

# Then the source (README is referenced by pyproject's `readme` field, needed to build).
COPY README.md ./
COPY src ./src
COPY apps ./apps
RUN uv sync --frozen --no-dev --extra api

RUN mkdir -p /data /outputs
EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "apps.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
