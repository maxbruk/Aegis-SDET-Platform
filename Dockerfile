# Python 3.12 slim base matching requires-python >=3.12
FROM python:3.12-slim

WORKDIR /app

# Install uv for deterministic dependency management
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv

# Copy project definition, lockfile, and readme needed by build backend
COPY pyproject.toml uv.lock README.md ./

# Install locked dependencies strictly without fallback
RUN uv sync --frozen --no-install-project

# Install libatomic1 needed by Playwright's bundled Node runtime on slim images, then Chromium + OS deps
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/*
RUN uv run playwright install --with-deps chromium

# Copy repository source, tests, baselines, and storefront
COPY framework ./framework
COPY frontend ./frontend
COPY tests ./tests
COPY reports/artifacts/visual_baselines ./reports/artifacts/visual_baselines

# Install local framework package strictly from lockfile
RUN uv sync --frozen

ENV HEADLESS=true
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "pytest", "-n", "4", "-v"]
