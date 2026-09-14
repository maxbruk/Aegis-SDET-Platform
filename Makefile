# =========================================================
#  Python SDET Enterprise Automation Platform & Storefront
#  End-to-End Quality Engineering with Playwright & Pytest
#  COM Architecture, Network Chaos, CDP Metrics & Allure
#
#  Developed by Max Bruk, August 2026
# =========================================================

.PHONY: help install test test-ui test-api test-resilience test-perf test-visual test-a11y test-parallel allure-serve allure-report serve lint format clean docker-build docker-test

help:
	@echo "Available commands:"
	@echo "  make install         - Install dependencies and Playwright browser binaries with uv"
	@echo "  make test            - Run full Pytest test suite and record Allure results"
	@echo "  make test-ui         - Run UI Component Object Model end-to-end tests"
	@echo "  make test-api        - Run API contract and Pydantic v2 validation tests"
	@echo "  make test-resilience - Run Chaos and network fault injection tests"
	@echo "  make test-perf       - Run Core Web Vitals and CDP performance telemetry tests"
	@echo "  make test-visual     - Run pixel-level visual regression tests"
	@echo "  make test-a11y       - Run WCAG 2.1 AA automated accessibility scans"
	@echo "  make test-parallel   - Run tests concurrently across 4 workers (pytest-xdist)"
	@echo "  make allure-serve    - Launch live interactive Allure test report server"
	@echo "  make allure-report   - Generate static HTML Allure report directory"
	@echo "  make serve           - Serve modern frontend storefront locally"
	@echo "  make lint            - Check code formatting with ruff"
	@echo "  make format          - Auto-format codebase with ruff"
	@echo "  make clean           - Remove test caches and generated report artifacts"
	@echo "  make docker-build    - Build headless test automation Docker image"
	@echo "  make docker-test     - Run complete test suite inside Docker container"

install:
	uv sync --extra dev
	uv run playwright install --with-deps chromium

test:
	uv run pytest -v

test-ui:
	uv run pytest tests/ui/ -v

test-api:
	uv run pytest tests/api/ -v

test-resilience:
	uv run pytest tests/resilience/ -v

test-perf:
	uv run pytest tests/performance/ -v

test-visual:
	uv run pytest tests/visual/ -v

test-a11y:
	uv run pytest tests/a11y/ -v

test-parallel:
	uv run pytest -n 4 -v

allure-serve:
	allure serve reports/allure-results

allure-report:
	allure generate reports/allure-results -o reports/allure-report --clean

serve:
	uv run python -m http.server 5173 --directory frontend

lint:
	uv run ruff check .

format:
	uv run ruff format .

clean:
	rm -rf .pytest_cache reports/allure-results reports/allure-report reports/*.html reports/artifacts/fail_*.png reports/artifacts/*actual.png reports/artifacts/*diff.png

docker-build:
	docker compose build

docker-test:
	docker compose run --rm sdet-runner
