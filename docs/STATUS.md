# Status

**Current phase:** Phase 6 — Learning / Strategy-Review Loop
**Last updated:** 2026-08-03

## Done

- **Phase 1** (Foundations & Architecture) — checkpoint `0a2644d`.
- **Phase 2** (Data Ingestion & Indicators) — checkpoint `c2caa4c`.
- **Phase 3** (Paper Portfolio & Trade Tracking) — checkpoint `811c5bd`.
- **Phase 4** (Scoring Engine & LLM Synthesis) — checkpoint `fa66912`.
- **Phase 5** (Backtesting) — checkpoint `29a0763`.
- **Phase 6:**
  - `StrategyVersion` gains a real 4-state lifecycle (`PROPOSED`/`ACTIVE`/
    `REJECTED`/`SUPERSEDED`), replacing `is_active: bool` outright —
    migration `eed7cb451bdc` (backfill + enum-drop-on-downgrade round-trip
    verified clean, ADR-027).
  - Proposals are user/operator-submitted candidate configs
    (`POST /api/v1/strategy-versions`), not an autonomous optimizer
    (ADR-026) — schema-validated against the exact shape
    `compute_score()` expects.
  - `POST /{id}/compare`: fresh backtest for candidate + currently-active
    version with identical params, persists 2 real `BacktestRun` rows,
    never changes candidate status.
  - `POST /{id}/approve`: requires `PROPOSED`; re-runs the comparison
    itself for the audit snapshot rather than trusting a prior `/compare`
    call (ADR-028); activates the candidate, supersedes the previous
    active version. Never enforces a numeric approval bar — a human
    decides, the system only surfaces the comparison.
  - `POST /{id}/reject`: requires `PROPOSED`, no backtest re-run.
  - Every proposal/approval/rejection writes its own `AuditEvent`
    (principle 9).
  - 107/107 tests passing (15 new this phase: pure `compute_comparison_delta`
    deltas, propose/compare/approve/reject state-machine + audit-trail
    endpoint tests), `ruff`/`mypy --strict` clean, no live API required
    (no new vendor this phase either — pure computation + the existing
    backtest engine).
  - **Live-verified**: a real propose → compare → approve flow — proposed
    a momentum-weighted candidate, compared it against the real active
    `Plan of Record v1` (candidate traded 148 fewer times, ~0.10pp lower
    return over the same ~2-year window), then approved it anyway. The
    previous active version correctly flipped to `SUPERSEDED`, the
    candidate is `ACTIVE` with `decided_at`/`decision_comment` set, and
    both `AuditEvent` rows reference the exact `BacktestRun` ids the
    decision was based on. See docs/TEST_EVIDENCE.md for full numbers.

## In progress / next

- Create the Phase 6 checkpoint commit.
- **Then stop and wait** — Phase 7 (UI polish & documentation hardening)
  does not start until explicitly requested.

## Known blockers

None.

## Deferred (not blockers, intentional)

- Docker-based local dev (ADR-008), Playwright e2e, Redis (ADR-006/021).
- Automatic order-status polling / websocket trade-updates subscription
  (ADR-016). FIFO/LIFO tax-lot cost-basis accounting (ADR-013).
- Persisted multi-turn `/api/v1/ask` conversation history (ADR-019).
- Historical-outcome-based confidence calibration — still needs a real
  sample of completed trades post-activation before any number is framed
  as a probability (docs/MODEL_GOVERNANCE.md).
- Full historical index-constituent/delisting reconstruction — out of
  scope for a fixed watchlist, not an index (ADR-025).
- An autonomous system that generates candidate strategy configs on its
  own — proposals are user/operator-submitted (ADR-026); the review gate
  doesn't care what originates a candidate if one is ever added.
- Any UI for reviewing/proposing/approving strategy versions or viewing
  backtest reports — everything through Phase 6 is API-only (Phase 7).
