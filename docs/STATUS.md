# Status

**Current phase:** Phase 3 — Paper Portfolio & Trade Tracking
**Last updated:** 2026-08-03

## Done

- **Phase 1** (Foundations & Architecture) — checkpoint `0a2644d`.
- **Phase 2** (Data Ingestion & Indicators) — checkpoint `c2caa4c`.
- **Phase 3:**
  - `PaperPortfolio`, `PaperOrder` models + migration `6fa6b9fd2ff4`
    (downgrade/upgrade round-trip verified clean). `PaperPosition` is a
    derived view, not a table (ADR-013).
  - `AlpacaPaperBrokerProvider`: submit order, get positions, cancel order,
    and (added mid-phase after live testing — see below)
    `get_paper_order_status` for asynchronous-fill catch-up.
  - Two-step propose → confirm order flow (ADR-014): nothing reaches
    Alpaca until explicit human confirmation; capital/position
    sufficiency validated at both steps (principle 1 — no overdraw, no
    short selling).
  - `AuditEvent` audit trail introduced (ADR-015) for every
    propose/confirm/refresh/cancel action.
  - Reconciliation endpoint (`GET /api/v1/portfolio/reconciliation`)
    against Alpaca's own paper-account position report.
  - 40/40 tests passing (17 new this phase), `ruff`/`mypy --strict` clean.
  - **Live-verified**: proposed and confirmed a real 1-share SPY market
    order against the real Alpaca paper account. Portfolio cash/position
    and reconciliation exactly match Alpaca's own account state. See
    docs/TEST_EVIDENCE.md for full numbers.

## In progress / next

- Create the Phase 3 checkpoint commit.
- **Then stop and wait** — Phase 4 (scoring engine & LLM synthesis) does
  not start until explicitly requested.

## Known blockers

None.

## Notable bug caught and fixed this phase

The original Phase 3 plan assumed `submit_paper_order()`'s response would
reflect the order's outcome. Live-tested against the real Alpaca paper API:
a submitted market order's immediate response reported status `new` — the
actual fill (`filled`, at a real market price) landed about 0.8 seconds
later. This is normal broker behavior (fills are asynchronous), not an
edge case, and the original design would have left confirmed orders stuck
showing `SUBMITTED` even after they'd actually filled — which would have
made the reconciliation deliverable meaningless (comparing an unfilled
local record against Alpaca's real filled position).

Fixed by adding `PaperBrokerProvider.get_paper_order_status()`: `confirm`
does one immediate re-check (catches the common same-cycle-fill case,
demonstrated live), and a new `POST /api/v1/paper-orders/{id}/refresh`
endpoint re-syncs any order still open later (ADR-016). Verified live: the
real order was stuck at `SUBMITTED` in our DB until `/refresh` was called,
which then correctly showed `FILLED` at $754.92/share, matching Alpaca's
own record exactly.

## Deferred (not blockers, intentional)

- Docker-based local dev (ADR-008), Playwright e2e, Redis (ADR-006).
- Automatic order-status polling / websocket trade-updates subscription —
  explicit `/refresh` covers the MVP's manual/API-driven usage; a
  background poller is deferred until a UI exists to justify it (ADR-016).
- FIFO/LIFO tax-lot cost-basis accounting — simple weighted-average cost
  basis is enough for MVP P&L direction (ADR-013).
