# Test Strategy

## Pyramid

1. **Deterministic unit tests** (heaviest layer, from Phase 2 onward) — every
   indicator formula, portfolio calculation, risk metric, and scoring
   function gets a pure-function unit test with known inputs/outputs. These
   never call a live API.
2. **API contract tests** (pytest + FastAPI `TestClient`) — one per endpoint,
   asserting response shape and status codes. `tests/test_health.py` is the
   Phase 1 example.
3. **Component tests** (Vitest + React Testing Library) — UI components in
   isolation, with `fetch`/API calls mocked. `__tests__/page.test.tsx` is the
   Phase 1 example.
4. **End-to-end tests** (Playwright) — deferred until a real multi-step user
   journey exists (ADR-006). Phase 1's only journey is "load the health
   page," already covered by the component test — a Playwright test today
   would duplicate it for no additional signal.

## Fixtures, not live APIs, in the default test suite

No test in the default `pytest` / `vitest` runs is allowed to depend on a
live Alpaca or Anthropic API call or a real API key. From Phase 2 onward,
provider tests inject a fake implementation of `MarketDataProvider` /
`PaperBrokerProvider` / `LLMProvider` (see docs/ARCHITECTURE.md's provider
abstraction section) built from static fixture data. This keeps CI/local
test runs free, fast, and reproducible without secrets.

## Determinism

Where synthetic data is needed for a test (e.g., a fixture price series),
it uses a fixed seed / hand-authored values — never live-fetched data — so
test runs are reproducible.

## Backtesting-specific testing (Phase 5)

Backtests get their own test category beyond the pyramid above: tests that
specifically assert *absence* of look-ahead bias (a bar dated after the
simulated "current" date must never be visible to the strategy) and
*absence* of survivorship bias (the historical symbol universe for a given
date must include instruments that were later delisted, not just today's
index membership).

## What Phase 1 actually runs

- `apps/api`: `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy .`, `uv run pytest -v`
- `apps/web`: `pnpm lint`, `pnpm typecheck`, `pnpm test`

Exact commands and pass/fail results for this phase are in
docs/TEST_EVIDENCE.md.
