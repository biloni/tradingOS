# Status

**Current phase:** Phase 4 — Scoring Engine & LLM Synthesis
**Last updated:** 2026-08-03

## Done

- **Phase 1** (Foundations & Architecture) — checkpoint `0a2644d`.
- **Phase 2** (Data Ingestion & Indicators) — checkpoint `c2caa4c`.
- **Phase 3** (Paper Portfolio & Trade Tracking) — checkpoint `811c5bd`.
- **Phase 4:**
  - Deterministic scoring engine (`services/scoring.py`): combines 4
    existing Phase 2 indicators (trend, momentum, MACD crossover,
    Bollinger position) into a 0–100 score plus a `LOW`/`MEDIUM`/`HIGH`
    confidence band computed from signal agreement — never the LLM's
    self-report (principle 15). Weights/thresholds read from
    `StrategyVersion.config`, never hardcoded (principle 8).
  - `StrategyVersion`, `Recommendation`, `LLMCallLog` models + migration
    `cd811cf4102b` (downgrade/upgrade round-trip verified clean), plus
    `PaperOrder.linked_recommendation_id`.
  - Concrete `AnthropicLLMProvider` (`claude-sonnet-5`, model/pricing
    verified via the `claude-api` skill — ADR-017).
  - `services/llm_tools.py`: 5 typed, schema-validated tools
    (`query_symbols`, `get_price_summary`, `get_indicators`,
    `get_recommendations`, `compute_recommendation`) — an explicit
    allow-list, pydantic-validated arguments, no model access to SQL or
    arbitrary code (principle 7). `compute_recommendation` is the one
    tool allowed a side effect: it persists a `Recommendation` row
    (ADR-018).
  - `services/ask.py`: the tool-use orchestration loop — call, execute
    requested tools, feed results back, repeat, capped at 5 iterations
    (ADR-019); every Anthropic call logged to `LLMCallLog`
    (`services/llm_cost.py`'s `estimate_cost_usd()`), no exceptions.
  - `POST /api/v1/ask` (`routers/ask.py`), rate-limited via an in-process
    token-bucket limiter (`core/rate_limit.py`, ADR-021) — 5-request
    burst, 5/min steady state.
  - 71/71 tests passing (31 new this phase: scoring invariants, mocked
    `AnthropicLLMProvider`, tool dispatcher validation/dispatch,
    orchestration-loop with a fake `LLMProvider` including the iteration
    cap, endpoint rate-limit/validation), `ruff`/`mypy --strict` clean.
  - **Live-verified**: a real `/api/v1/ask` call ("What does AAPL current
    setup look like...") produced a genuine 2-turn tool-use round trip
    (`get_price_summary` → `get_indicators` → `compute_recommendation`,
    then synthesis), a real `Recommendation` row (score 37.50, LOW
    confidence), and 2 real `LLMCallLog` rows (total cost $0.01496). See
    docs/TEST_EVIDENCE.md for full numbers.

## In progress / next

- Create the Phase 4 checkpoint commit.
- **Then stop and wait** — Phase 5 (backtesting) does not start until
  explicitly requested.

## Known blockers

None.

## Deferred (not blockers, intentional)

- Docker-based local dev (ADR-008), Playwright e2e, Redis (ADR-006/021).
- Automatic order-status polling / websocket trade-updates subscription
  (ADR-016). FIFO/LIFO tax-lot cost-basis accounting (ADR-013).
- Persisted multi-turn `/api/v1/ask` conversation history — stateless
  per-request for now (ADR-019); a future chat UI can resend history
  itself if needed.
- Historical-outcome-based confidence calibration — needs completed trade
  history from backtesting (Phase 5) before any number is framed as a
  calibrated probability (docs/MODEL_GOVERNANCE.md).
