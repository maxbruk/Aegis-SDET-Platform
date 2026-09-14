# Use official Microsoft Playwright Python base image with all system dependencies
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Set working directory
WORKDIR /app

# Install uv for ultra-fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project definition, lockfile, and readme needed by build backend
COPY pyproject.toml uv.lock* README.md* ./

# Install dependencies using uv (pre-install dependencies without local package for optimal layer caching)
RUN uv sync --frozen --no-install-project || uv sync --no-install-project

# Install Playwright browser binaries
RUN uv run playwright install chromium

# Copy entire repository source, tests, and storefront
COPY . .

# Install local framework package
RUN uv sync --frozen || uv sync

# Set environment variables for headless container runs
ENV HEADLESS=true
ENV PYTHONUNBUFFERED=1

# Default execution command
CMD ["uv", "run", "pytest", "-n", "4", "-v"]
