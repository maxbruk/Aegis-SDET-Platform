# Engineering & Agent Execution Standards

You are operating in a high-velocity, high-trust codebase. Your goal is to maximize shipping speed while strictly maintaining or improving code quality. Do not produce "slop" (quick workarounds, unverified patches, or unidiomatic code).

## 1. Core Hierarchy of Constraints
Rely on deterministic checks first and prose second:
1. **Architecture & Types (Highest Priority):** Follow established module boundaries, strict types, and framework conventions so invalid states are unrepresentable.
2. **Linters & Static Analysis:** Never bypass, disable, or ignore lint rules, compiler errors, or dependency graph checks. Treat linter error messages as architectural guidance to fix the root cause.
3. **Runtime & Formal Verification:** Prove your code works before finishing.
4. **Prose & Comments (Lowest Priority):** Only use text where judgment is required.

## 2. Codebase Hygiene ("Gardening")
* **Do Not Mimic Anti-Patterns:** Because you learn from existing code, actively avoid copying legacy workarounds or deprecated patterns. When touching an area with tech debt, leave it cleaner than you found it.
* **Fix Root Causes, Never Patch:** Do not use quick fixes (e.g., arbitrary `setTimeout` calls, `requestAnimationFrame` hacks, or complex `useEffect` chains) to paper over architectural mismatches. Fix the underlying state or data flow.
* **Respect Directory & Boundary Conventions:** Strictly adhere to folder-level separation of concerns (e.g., never import main-thread/backend modules into renderer/client code).
* **No Comment Excuses:** Do not write inline comments to justify a suboptimal workaround or explain why you broke a pattern. Code comments go stale and are unenforceable; express intent through clean structure, naming, and types instead.
* **Encode Lessons Deterministically:** Whenever you encounter a recurring mistake or receive a correction from the user, propose or implement a deterministic guardrail (a lint rule, type constraint, or automated test) rather than just adding another line of prose to documentation.

## 3. Verification-First Workflow
Most of your effort and token budget should go toward proving correctness, not just writing initial code:
* **Run & Inspect Like a User:** Do not assume code works because it compiles. Use available runtime tools, CLIs, browser/DevTools protocols, or test runners to execute the application and verify behavior end-to-end.
* **Use Shared Vocabulary:** Refer to UI elements and user flows using the repository's established feature maps, state machines, or component names.
* **Check Invariants & Edge Cases:** Validate system properties using property-based tests, state machine checks, or formal verification tools where configured.
* **Produce Reviewable Artifacts:** When completing a task or PR, provide clear verification proof—such as test outputs, screenshots, recordings, or state-chart diagrams—so human reviewers can verify intent without reading every line of boilerplate.

---

## 4. AEGIS Project Architecture & Boundaries

AEGIS conceptually separates reusable test infrastructure (**AEGIS Platform**) from the **System Under Test (SUT)**:

```text
AEGIS Platform                          System Under Test (SUT)
├── framework/                          ├── backend/main.go   (Go 1.22 API, /metrics, /telemetry/ingest)
│   ├── config/settings.py  (Pydantic)  ├── frontend/         (Vanilla Storefront SPA)
│   ├── execution/          (aegis CLI, RunContext, ExecutionMetadata)
│   ├── artifacts/          (ArtifactManager, console & network collectors)
│   ├── data/               (TestDataManager — isolated API setup & teardown)
│   ├── api/                (BaseAPIClient, endpoint clients, models/ Pydantic v2 DTOs)
│   ├── pages/              (COM: StorefrontPage, AdminPage, components/)
│   ├── quality/            (VisualDiffer, AccessibilityAuditor + vendor/axe.min.js, ChaosNetworkInjector)
│   ├── telemetry/          (CDPTelemetryCollector, PerformanceThresholdEvaluator, ReliabilityAnalyzer, browser.py)
│   ├── ai/                 (FailureClassifier, LocatorHealer, LocatorValidationEngine, HistoricalFailureStore, FailureIntelligenceAnalyzer)
│   └── utils/              (DataFactory & backwards-compatible exports)
├── tests/
│   ├── conftest.py         (xdist AEGIS_RUN_ID propagation & lifecycle/failure hooks)
│   ├── fixtures/           (server, browser, authentication, api, quality_tools)
│   ├── support/            (mock_routes, test_data, artifact_helpers)
│   └── {unit,api,ui,integration,concurrency,e2e,resilience,performance,visual,a11y}/  (90 collected tests)
└── monitoring/             (Prometheus config, Grafana datasources & dashboards: aegis-quality-overview, aegis-sut-telemetry)
```

### Boundary Rules
* **Seed Data Integrity:** Never mutate the shared seeded catalog products (IDs `1–6`) in live tests. Provision isolated users, products, carts, and orders through `TestDataManager` (`framework/data/manager.py`) and clean them up in teardown.
* **Offline Portability:** Keep offline suites (`-m unit`, `-m ui_mocked`, `-m a11y`, `-m resilience`, `-m performance`, `-m visual`) completely runnable without Docker, PostgreSQL, or the Go backend.
* **Gitignore & Artifact Hygiene:** Never commit private `notes/` (`.gitignore:27`) or ephemeral `reports/` outputs (`reports/runs/`, `reports/reliability/`, `reports/allure-results/`, `reports/*.html`, `reports/*.xml`). Only `reports/artifacts/visual_baselines/` is tracked.

## 5. Shared Vocabulary & Domain Invariants

* **Component Object Model (COM) & Playwright:** Use `StorefrontPage` and its scoped sub-components (`HeaderComponent`, `ProductCardComponent`, `CartDrawerComponent`, `CheckoutModalComponent`, `AuthModalComponent`, `ToastComponent`) with `data-testid` anchors and Playwright Web-First assertions (`expect(...)`). Never add arbitrary `time.sleep()` waits for UI state transitions.
* **Dual-Mode Browser Fixtures:** Use `mocked_page`, `mocked_storefront_page`, `mocked_authenticated_page`, and `mocked_admin_page` for deterministic mocked UI suites (`tests/support/mock_routes.py`), and `integration_page`, `integration_storefront_page`, `authenticated_page`, and `admin_page` (gated by `backend_health` + `REQUIRE_BACKEND=true`) for live Go + PostgreSQL verification.
* **Typed API Client & Contracts:** `BaseAPIClient` raises typed `APIClientError`, `APIConnectionError`, and `APITimeoutError` exceptions—never convert transport failures into synthetic HTTP status codes. Validate live API payloads against Pydantic v2 DTOs in `framework/api/models/`.
* **Quality & Failure Intelligence Invariants:**
  * `VisualDiffer` fails strictly on missing baselines or dimension mismatches; set `UPDATE_VISUAL_BASELINES=true` only for intentional baseline updates.
  * `AccessibilityAuditor` combines vendored `axe-core` with AEGIS structural DOM rules, asserting zero violations (`violations == []`) in `tests/a11y/`.
  * `FailureIntelligenceAnalyzer` (`framework/ai/`) is deterministic: it classifies failures from multi-signal evidence, redacts secrets before writing `failure_history.jsonl`, enforces `match_count == 1` + live DOM visibility/enabled probing (`approval_status="pending_human_approval"` / `"rejected"`), and never alters a failed test's status.
* **Go SUT Invariants (`backend/main.go`):** `POST /api/v1/orders/checkout` requires a valid HS256 JWT (`401 UNAUTHORIZED`), serializes `Idempotency-Key` via `pg_advisory_xact_lock`, blocks cross-user key reuse (`409 IDEMPOTENCY_KEY_CONFLICT`), and locks `products` rows via `SELECT ... FOR UPDATE` in ascending `product_id` order (`CHECK (stock >= 0)`).

## 6. Known Codebase Pitfalls

* **Playwright Exception Inheritance:** `playwright.sync_api.Error` inherits directly from `Exception`, **not** `RuntimeError`. Always import and catch `playwright.sync_api.Error` explicitly when guarding Playwright calls.
* **Video Capture Lifecycle:** Never call `page.video.save_as()` while the Playwright `Page` is still open (raises `Page is not yet closed` in sync Playwright); persist recordings only after `page.close()` during teardown.
* **Dependency Auditing with `uv`:** Bare `uvx pip-audit` inspects `uvx`'s own ephemeral environment instead of `uv.lock`. Always export locked dependencies first (`uv export --frozen --no-hashes --no-emit-project -o <file>`) and run `pip-audit -r <file>`.
* **Pytest Collection Purity:** Guard session setup hooks with `_is_collect_or_help()` (`tests/conftest.py`) so `--collect-only` and `--help` create zero `reports/runs/` directories, and never mark `live_server` (`tests/fixtures/server.py`) as `autouse=True`.
* **Cross-OS Env Syntax (Windows PowerShell):** `Makefile` integration/concurrency/e2e targets use POSIX inline `REQUIRE_BACKEND=true ...` syntax; on Windows PowerShell, set `$env:REQUIRE_BACKEND = "true"` instead.

## 7. Required Verification Commands

```powershell
# Static analysis & formatting (must pass with zero warnings/errors)
uv run ruff check .
uv run ruff format --check .
uv run mypy framework tests
Push-Location backend; go vet ./...; Pop-Location

# Offline collection & fast Python unit checks (zero side-effect run dirs)
uv run pytest --collect-only -q
uv run pytest -m unit -v

# Full 6-container stack verification (PostgreSQL -> Go API -> Storefront -> Prometheus -> Grafana -> Pytest)
docker compose up --build --abort-on-container-exit --exit-code-from test-runner
docker compose down -v

# Live stack mode for inspecting Grafana dashboards (http://127.0.0.1:3001)
docker compose up -d --build --wait db backend storefront prometheus grafana
docker compose run --rm test-runner
# When done inspecting: docker compose down -v
```
