# Status

**Current phase:** Phase 8 (shipped), plus Revision Prompt R0 — a binding
policy amendment (PROJECT_INSTRUCTIONS.md's new "TradingOS v2 Decision and
Execution Amendment") layered on top, documentation- and policy-check-only
per R0's own instruction ("do not implement future provider, scoring,
dashboard, or broker features in this revision").
**Last updated:** 2026-08-05

## Revision Prompt R0 (2026-08-05) — v2 Decision and Execution Amendment

Appended a new, clearly-labeled, binding section to `PROJECT_INSTRUCTIONS.md`
covering six areas: **PRODUCT MODES** (investment vs. tactical
recommendations, mode-exclusive action vocabularies, no silent
conversion), **MORNING DECISION STANDARD** (one immutable versioned plan
per trading day, fixed section grouping, provenance display), **HYBRID
EARNINGS STRATEGY** (6/8 conservative live threshold, 0.25%/0.50%
pre-event risk budget, gap-risk modeling, no leakage from the future),
**ORDER AUTHORITY** (four modes exactly —
`RESEARCH_ONLY`/`PAPER_MANUAL_APPROVAL`/`PAPER_AUTO_POLICY`/
`LIVE_CONFIRM_EACH_ORDER` — fail-closed, kill switch, no text channel can
reach the broker boundary), **DECISION QUALITY** (facts/calculations/
inferences/decisions shown as separate sections, confidence ≠ magnitude,
no LLM self-rating presented as a probability), and **SECURITY AND
SAFETY** (credentials never reach Cowork, approval binds the exact order,
material changes invalidate approval).

Per R0's explicit scope limit, this pass is policy adoption plus proof-
of-concept validation, not feature implementation:

- Two new standalone modules under `apps/api/src/tradingos_api/policy/`
  (`order_authority.py`, `recommendation_modes.py`) — pure Python, no
  SQLAlchemy model, no migration, no router, no provider call — encode
  the four-mode taxonomy and the investment/tactical separation rules as
  executable, testable logic.
- 45 new unit tests (`tests/test_policy_order_authority.py`,
  `tests/test_policy_recommendation_modes.py`) prove: the mode taxonomy
  is exactly the four required members with no autonomous-live mode; each
  mode's authorization gate (deny-always / confirmation-required /
  versioned-grant-required / fresh-confirmation-required, fail-closed on
  ambiguity); the bracket-leg no-second-confirmation carve-out; the two
  recommendation action vocabularies are mode-exclusive except for the
  shared `NO_ACTION`; sharing a `recommendation_id` across an investment/
  tactical pair is rejected; a mode change without an explicit user
  action is rejected; and (a structural guard against the real `src/`
  tree) the order-fill/broker-boundary function and every order-mutating
  endpoint exist only in `routers/orders.py` today.
- docs/DECISIONS.md — ADR-045 records the decision and its alternatives.
- docs/SECURITY.md, docs/MODEL_GOVERNANCE.md, docs/OPERATIONS.md,
  docs/TASKS.md — each cross-references the amendment from its own
  section (credential/Cowork handling, confidence-vs-magnitude and
  earnings-score-is-deterministic notes, kill-switch/cancel-all runbook
  stub, and the R0 task checklist respectively).
- **Not done, and explicitly out of scope for this revision:** wiring
  `assert_order_authorized()` into `routers/orders.py`; a real `mode`
  column on `recommendations`/`recommendation_versions`; the morning-plan
  generator, the earnings-strategy engine, the kill switch's actual
  control surface, or any dashboard change. All are named as the next
  phase's work, not silently started.
- `ruff check`/`ruff format --check`/`mypy .` clean; full suite (96 tests:
  the 51 from Phase 8 plus 45 new) passing.

## Done

- **Phase 1** (Foundations & Architecture) — checkpoint `0a2644d`.
- **Phase 2** (Data Ingestion & Indicators) — checkpoint `c2caa4c`.
- **Phase 3** (Paper Portfolio & Trade Tracking) — checkpoint `811c5bd`.
- **Phase 4** (Scoring Engine & LLM Synthesis) — checkpoint `fa66912`.
- **Phase 5** (Backtesting) — checkpoint `29a0763`.
- **Phase 6** (Learning / Strategy-Review Loop) — checkpoint `3fdbfac`.
- **Phase 7:**
  - Full Next.js frontend (`apps/web`) built against the already-complete,
    already-tested API — no new backend logic this phase. Six sections:
    Dashboard, Symbols & Charts, Paper Portfolio, Ask, Backtests, Strategy
    Versions, behind a persistent sidebar (ADR-029's hand-rolled
    `components/ui/` kit — `Card`/`Button`/`Table`/`StatusPill`/
    `LoadingSpinner`/`ErrorBanner`/`Input`/`Textarea`/`ConfirmButton`, no
    external design system).
  - Both review flows fully built and live-verified: paper-order
    propose→confirm→(refresh), and strategy propose→compare→approve/
    reject, each behind `ConfirmButton`'s two-step human-confirmation gate
    for the irreversible action.
  - Charts (`lightweight-charts` v5, `CandlestickChart` +
    `EquityCurveChart`) use a manual `ResizeObserver` +
    `chart.applyOptions()` resize pattern rather than the `autoSize`
    convenience flag, which was observed live to leave the canvas's pixel
    buffer stuck at the browser default in this app's flex/sidebar
    layout.
  - Decimal-as-string is a first-class TypeScript contract (ADR-031) —
    every `Numeric`-backed API field types `string` in `lib/api/*.ts`,
    converted to `Number(...)` only at display/chart boundaries.
  - **Bug found and fixed** via this discipline while writing component
    tests: `CompareView.tsx`'s `DeltaMetric` called `Number()` on an
    already `%`-suffixed string (`"4.00%"` → `NaN`), silently breaking the
    +/− sign and emerald/red tone on every comparison delta metric since
    it was written in Phase 6's UI. Fixed by stripping the trailing `%`
    before parsing.
  - 20 new Vitest/RTL component tests (paper-order propose→confirm + error
    states; strategy propose→compare→approve/reject state machine + error
    states; ask page recommendation rendering + 429/503/422 states;
    `BacktestReport` data-shape/empty-state coverage — jsdom can't render
    `<canvas>`, so `EquityCurveChart` is mocked in these tests). `pnpm
    lint`/`pnpm typecheck`/`pnpm test` all clean.
  - One Playwright e2e test (`e2e/paper-order-flow.spec.ts`, ADR-030)
    against the real dev server + real API + real seeded data — passing.
  - **Live-verified** via the Browser tool: the full demo path end to
    end — dashboard → symbol candlestick chart → propose/confirm a real
    paper order (real Alpaca submission, `SUBMITTED` status) → propose/
    compare/reject a real strategy version (two real backtests, correct
    delta, real state transition) → ask a real NL question (real
    Anthropic tool-use round trip, grounded in real indicator data). See
    docs/TEST_EVIDENCE.md for exact evidence, including a transparently
    documented environment/tooling limitation (this session's Browser
    pane could not composite frames for screenshots or canvas pixel
    inspection, and coordinate-based clicks didn't register — worked
    around via `javascript_tool`-dispatched clicks and text/DOM/network
    inspection instead of pixel screenshots).
  - docs/USER_GUIDE.md fully rewritten (one section per page/flow, plus
    known limitations). docs/SECURITY.md and docs/TEST_STRATEGY.md got
    their final review-pass updates (frontend introduces no new
    secret-handling surface; Playwright layer marked implemented).

## Phase 8 (2026-08-03) — domain model, schema, migrations, seed data, API

Implements the schema/API scope of the refinement pass below ("domain
model, database schema, migrations, seed fixtures, and versioned API
contracts — do not integrate external providers yet"):

- **Domain model** — 13 bounded contexts, ~70 tables, all UUID-keyed
  (ADR-043 supersedes the old integer-PK, 9-table Phase 1-7 schema
  wholesale; `audit_events` is the one table kept unchanged). Full column
  list in docs/DATA_DICTIONARY.md; relationships in docs/ER_DIAGRAM.md.
- **36 native Postgres enums** with co-located lifecycle transition maps
  (`models/enums.py`), enforced through one shared
  `services/lifecycle.py::assert_transition_allowed()` helper.
- **One migration** (`ece90645a84b`) — hand-verified empty→head, head→
  one-step-down (old schema restored byte-for-byte), and downgrade→base,
  all via `tests/test_migrations.py` against an isolated Postgres schema
  (never the real dev database).
- **Seed script** (`tradingos-seed`) — idempotent; populates every
  bounded context with realistic linked data (48-symbol Tier-1 watchlist,
  one full 8-role committee session, a manual journal account with real
  fills/positions/lots, one backtest run with normalized trades, alerts,
  provider config, risk policy).
- **12 API areas, 37 endpoints** (`docs/API_CONTRACTS.md`) — instruments/
  validation, watchlists, market overview/freshness, recommendations/
  committee detail, portfolio/positions/cash/risk, manual order entry/
  import/reconciliation, trade journal, performance, alerts, daily plans,
  backtests (read-only), settings/provider status. Pagination, filtering,
  idempotency keys, and optimistic concurrency (`expected_updated_at`)
  implemented per the brief; decimal fields serialize as JSON strings
  (ADR-031, unchanged) — verified structurally by
  `tests/test_openapi_snapshot.py`.
- **Old Phase 1-7 business-logic routers/services retired**, not ported,
  this pass (ADR-044) — `scoring`, `backtest`-execution, and LLM
  tool-use orchestration are out of "domain model ... not full business
  logic" scope; `GET /api/v1/backtests` serves only seeded historical
  runs, and `POST /api/v1/ask`/`/api/v1/backtests`/strategy compare no
  longer exist on the API.
- **Bug found and fixed** while writing `tests/test_invariants.py`:
  `routers/orders.py::_apply_fill()` reduced `positions.quantity` on a
  SELL but never consumed the matching `position_lots` rows via FIFO,
  silently diverging the two places this app tracks quantity. Fixed by
  adding oldest-first lot consumption on the SELL path — the exact
  invariant the brief's own test requirement asks for. Also fixed:
  `ORDER_TRANSITIONS["DRAFT"]` didn't include `FILLED`, which blocked a
  `MANUAL` account's one-step confirm-and-fill (no broker submission step
  to pass through `SUBMITTED` first).
- **51 tests** across migration reversibility, DB constraints/indexes,
  Numeric-never-float precision (incl. a fractional-share exact-Decimal
  round trip), position-lot/cash-ledger invariants, OpenAPI structural
  contracts, and idempotency/optimistic-concurrency — all passing, plus
  the pre-existing provider-mapping tests. `ruff check`/`ruff format
  --check`/`mypy .` all clean across `src/` and `tests/`.
- **Live-verified** via direct `curl` against the real seeded Postgres
  database: instrument validation, watchlist add/patch/409-on-duplicate,
  committee-session detail (all 8 real agent runs + opinions), the full
  manual order propose→confirm→fill→reconciliation cycle (including the
  SELL/FIFO-lot fix), bulk order import with idempotency, journal note/
  review append, alert acknowledge with optimistic-concurrency 409, and
  risk-policy PATCH/revert — all 12 API areas exercised with real data.

## Product & Architecture Refinement (2026-08-03, planning only — no code changed)

A much larger scope was defined per an explicit refinement brief: a
symbol-validated tiered watchlist, an 8-role investment committee behind
deterministic risk gates, regime/VIX-aware position sizing, ATR+structure
stops, a broker-agnostic trade journal as the primary tracked portfolio,
an active trade monitor, premarket/intraday/EOD scheduled workflows, and
recommendation-vs-reality tracking. Per the brief's own instruction, this
pass produced **documents only — no application code, no scaffolding, no
migration, no new dependency installed.**

Produced this pass:
- docs/PRODUCT_REQUIREMENTS.md — full rewrite (persona, jobs-to-be-done,
  50 functional requirements, 8 non-functional requirements, user stories,
  8 measurable acceptance criteria).
- docs/ARCHITECTURE.md — full rewrite (context diagram, ingestion→
  recommendation→action→review data-flow diagram, both Mermaid; 11 bounded
  contexts; trust boundaries; deployment topology).
- docs/DECISIONS.md — ADR-032 through ADR-042 (symbol validation,
  watchlist tiers, regime-can't-trigger enforcement, ATR+structure stops,
  risk-budget sizing, no-average-down precondition, committee execution
  order/cost bound, journal-vs-Alpaca-paper split, in-process scheduler,
  computed recommendation-vs-reality classification, deferred walk-forward).
- docs/PROVIDER_MATRIX.md — candidate evidence vendors (none selected,
  BLOCKING_DECISIONS.md #1/#2/#7) + a low/normal/heavy usage cost estimate.
- docs/MODEL_GOVERNANCE.md — extended for the 8-role committee (per-role
  prompt versions, structured output schemas, evaluation/drift plan, cost
  bound of 7 calls/run).
- docs/MVP_PLAN.md (new) — MVP / Phase 2 / Future scope split.
- docs/UX_MAP.md (new) — pages, actions, empty/error/stale states, mobile.
- docs/THREAT_MODEL.md (new) — STRIDE walk of the 4 new trust boundaries.
- docs/RISK_REGISTER.md (new) — 10 risks with likelihood/impact/mitigation.
- docs/BLOCKING_DECISIONS.md (new) — 10 decisions, each with a recommended
  default, none acted on.
- README.md — status/known-limitations updated to make clear this refined
  scope is unimplemented.

## In progress / next

- **Stop, per this phase's own explicit instruction** ("commit, and
  stop"). Not yet done, and explicitly out of Phase 8's scope (ADR-044):
  re-implementing scoring/backtest-execution/LLM tool-use orchestration
  against the new schema; wiring up real Anthropic/Alpaca calls for the
  committee and evidence-ingestion contexts ("do not integrate external
  providers yet"); a frontend for the new schema (the existing `apps/web`
  still targets the retired Phase 1-7 API and will not build against the
  current backend until that work happens).

## Known blockers

None.

## Deferred (not blockers, intentional)

- Docker-based local dev (ADR-008), Redis (ADR-006/021).
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
- An SMA/indicator overlay line on the symbol-detail candlestick chart —
  the real `GET /api/v1/symbols/{ticker}/indicators` contract only
  returns a single day's snapshot, not a ranged series; a text readout is
  shown instead (docs/USER_GUIDE.md).
- A larger Playwright suite beyond the one paper-order journey (ADR-030)
  — the existing mocked-fetch Vitest component tests already cover
  per-component behavior and error states.
