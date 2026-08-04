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
4. **End-to-end tests** (Playwright) — **implemented, Phase 7**
   (`apps/web/e2e/paper-order-flow.spec.ts`, ADR-030). Exactly one test:
   propose a paper order for a seeded liquid symbol, confirm it through
   the two-step `ConfirmButton` gate, and assert its status leaves `DRAFT`
   via a real Alpaca paper-trading call. Runs against the real local dev
   server + real FastAPI + real seeded Postgres data — not mocked, and
   deliberately not part of the default `pnpm test` run (see below) since
   it requires both servers already running locally
   (`pnpm exec playwright test` or `pnpm test:e2e`). Deferred since Phase
   1 per ADR-006 until this phase's two real multi-step journeys
   (paper-order propose→confirm; strategy propose→compare→approve/reject)
   existed to justify it.

## Fixtures, not live APIs, in the default test suite

No test in the default `pytest` / `vitest` runs is allowed to depend on a
live Alpaca or Anthropic API call or a real API key. From Phase 2 onward,
provider tests inject a fake implementation of `MarketDataProvider` /
`PaperBrokerProvider` / `LLMProvider` (see docs/ARCHITECTURE.md's provider
abstraction section) built from static fixture data. This keeps CI/local
test runs free, fast, and reproducible without secrets.

The one deliberate exception is the Playwright e2e test (layer 4 above,
ADR-030) — by definition it exercises the real Alpaca paper-trading API,
which is why it is not part of `pytest`/`vitest run` and must be invoked
explicitly (`pnpm test:e2e`) with both real servers already running.

## Determinism

Where synthetic data is needed for a test (e.g., a fixture price series),
it uses a fixed seed / hand-authored values — never live-fetched data — so
test runs are reproducible.

## Backtesting-specific testing (**implemented, Phase 5**)

Backtests get their own test category beyond the pyramid above:
`tests/test_backtest_simulation.py`'s `TestNoLookAhead` runs the pure
simulation core (`services/backtest.py`'s `run_backtest_simulation()`)
over the same shared history once truncated at a boundary day and once
extended further with everything *after* the boundary deliberately
mutated to extreme values — every trade and equity-curve point on or
before the boundary is asserted identical between the two runs, the
concrete operationalization of "absence of look-ahead bias" for this
codebase. `tests/test_backtest_endpoint.py` asserts *absence* of
survivorship bias by seeding a symbol marked `active=False` today with a
signal-worthy historical series and confirming it still appears in the
backtest's trade log — scoped to this system's reality (a fixed 30-name
watchlist, not an index with changing constituents; see ADR-025 for why
full historical-index reconstruction is out of scope).

## What Phase 1 actually runs

- `apps/api`: `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy .`, `uv run pytest -v`
- `apps/web`: `pnpm lint`, `pnpm typecheck`, `pnpm test`

Exact commands and pass/fail results for this phase are in
docs/TEST_EVIDENCE.md.
