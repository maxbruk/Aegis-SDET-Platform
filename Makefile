.PHONY: help install test test-unit test-ui test-ui-mocked test-api test-integration test-concurrency test-e2e test-resilience test-perf test-visual test-a11y test-parallel aegis-run aegis-reliability typecheck allure-serve allure-report serve lint format clean docker-build docker-up docker-down docker-test

help:
	@echo "Available commands:"
	@echo "  make install          - Install locked dependencies and Playwright Chromium"
	@echo "  make lint             - Run ruff lint and format checks"
	@echo "  make typecheck        - Run mypy static type checker"
	@echo "  make test             - Run full Pytest test suite"
	@echo "  make test-unit        - Run framework unit and Pydantic contract tests"
	@echo "  make test-ui-mocked   - Run deterministic mocked UI tests across 4 workers"
	@echo "  make test-api         - Run API contract and live endpoint tests"
	@echo "  make test-integration - Run real Go backend + PostgreSQL integration tests"
	@echo "  make test-concurrency - Run backend idempotency, race-condition, and rollback tests"
	@echo "  make test-e2e         - Run full-stack Storefront + Go backend + PostgreSQL E2E tests"
	@echo "  make test-resilience  - Run Chaos and network fault injection tests"
	@echo "  make test-perf        - Run Core Web Vitals and CDP performance telemetry tests"
	@echo "  make test-visual      - Run pixel-level visual regression tests"
	@echo "  make test-a11y        - Run automated accessibility checks"
	@echo "  make test-parallel    - Run tests concurrently across 4 workers (pytest-xdist)"
	@echo "  make aegis-run        - Run unit suite via AEGIS CLI orchestrator"
	@echo "  make aegis-reliability- Generate JSON & HTML reliability dashboard"
	@echo "  make docker-test      - Run full-stack tests in Docker and tear down on exit"
	@echo "  make docker-down      - Tear down Docker services and volumes"

install:
	uv sync --frozen --extra dev
	uv run playwright install --with-deps chromium

test:
	uv run pytest -v

test-unit:
	uv run pytest -m unit -v

test-ui:
	uv run pytest tests/ui/ -v

test-ui-mocked:
	uv run pytest -m ui_mocked -n 4 -v

test-api:
	uv run pytest -m api -v

test-integration:
	REQUIRE_BACKEND=true uv run pytest -m integration -v

test-concurrency:
	REQUIRE_BACKEND=true uv run pytest -m concurrency -v

test-e2e:
	REQUIRE_BACKEND=true uv run pytest -m e2e -v

test-resilience:
	uv run pytest -m resilience -v

test-perf:
	uv run pytest -m performance -v

test-visual:
	uv run pytest -m visual -v

test-a11y:
	uv run pytest -m a11y -v

test-parallel:
	uv run pytest -n 4 -v

aegis-run:
	uv run aegis run --suite unit --workers 1

aegis-reliability:
	uv run aegis reliability

typecheck:
	uv run mypy framework tests

allure-serve:
	allure serve reports/allure-results

allure-report:
	allure generate reports/allure-results -o reports/allure-report --clean

serve:
	uv run python -m http.server 5173 --directory frontend

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

clean:
	rm -rf .pytest_cache .mypy_cache reports/allure-results reports/allure-report reports/runs reports/reliability reports/*.html reports/*.xml reports/artifacts/fail_*.png reports/artifacts/*actual.png reports/artifacts/*diff.png

docker-build:
	docker compose build

docker-up:
	docker compose up -d --build --wait db backend storefront prometheus grafana

docker-down:
	docker compose down -v

docker-test:
	docker compose up --build --abort-on-container-exit --exit-code-from test-runner
