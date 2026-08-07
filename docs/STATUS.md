# Status

**Current phase:** Phase 8 (shipped), Revision Prompt R0 (binding policy
amendment, shipped), Revision Prompt R1 (product/architecture delta
review, approved by proceeding to R2), Revision Prompt R2 (scaffold/
navigation compatibility patch, shipped — `apps/web` route/nav/UI-
primitive scaffolding only, no provider calls, strategy calculations,
recommendations, scheduling, or broker submission), Revision Prompt R3
(backward-compatible schema and API migration, shipped — additive
migration + 19 new endpoints across 7 new bounded contexts, no provider
integration, no trading/scoring logic, no live broker submission
endpoint), Revision Prompt 4 (point-in-time evidence layer, shipped
— 15 provider interfaces, ingestion services, 9 data-quality gates, and
a provider-diagnostics API; one real vendor (Alpaca) plus synthetic
fixtures, no paid vendor contracted, no recommendation/scoring/order
logic), and Revision Prompt 5 (deterministic dual-lane analytics and
earnings feature engine, shipped — common technical-analytics library,
market-regime classification, the tactical 8-component score, the
Investment lane's 9-component feature engine, expected-move calculation,
the 9-condition baseline eligibility gate, post-earnings confirmation's
three gates, and a read-only feature-diagnostics API; no LLM computes
any value in this layer, no recommendation created yet).
**Last updated:** 2026-08-06

## Revision Prompt 5 (2026-08-06) — deterministic dual-lane analytics and earnings feature engine

**No prior implementation existed to inspect** — same documented gap as
R2/R3/P4 — this prompt's own scope (deterministic analytics only; no
recommendations) didn't depend on one.

- **Schema (additive):** `FeatureComponentStatus` enum (`PASS`, `FAIL`,
  `MISSING_DATA`, `CAPABILITY_UNAVAILABLE`, and — added in a follow-up
  migration after the first end-to-end demo run surfaced a real gap —
  `INSUFFICIENT_HISTORY`); two new tables, `feature_component_results`
  (the generic, `subject_type`/`subject_id`-keyed component ledger every
  lane writes to, ADR-015's shape reused a third time) and
  `investment_quality_feature_snapshots` (the Investment lane's parent
  snapshot, with `hard_disqualified` as a standalone veto column, never
  derived from the component rows). `EarningsFeatureSnapshot`'s
  pre-existing fixed `component_*` columns are superseded, not migrated
  — this prompt's precisely-named 8 components don't map onto that
  earlier, looser placeholder set. Full detail: docs/DATA_DICTIONARY.md
  §11, docs/ER_DIAGRAM.md §15.
- **Common analytics library** (`services/analytics.py`, new): SMA, EMA,
  RSI, MACD, ATR, normalized ATR, realized volatility, rolling volume,
  relative strength, support/resistance, trend, momentum, liquidity,
  correlation — pure Python + `Decimal`, no numpy/pandas runtime
  dependency. Verified against the trusted, MIT-licensed `ta` library
  (dev-only dependency) to <0.001 relative tolerance on SMA/EMA/RSI/
  MACD-line/MACD-signal/ATR, after two real convention bugs were found
  and fixed by direct `ta` source inspection: (1) MACD's signal EWM
  must seed from the point where both EMAs have "warmed up"
  (`macd_series[slow - 1:]`), not from index 0 of a fully-computed
  series — `ta`'s `min_periods=window` truncation makes its macd series
  NaN before that point, and pandas' `ewm()` seeds at the first non-NaN
  value; (2) `ta`'s ATR true-range series is fully defined from bar 0
  (its NaN-propagating prev-close terms are silently dropped by
  `DataFrame.max(axis=1, skipna=True)`, leaving just `high[0]-low[0]`),
  so the Wilder seed genuinely averages `window` true-range values
  starting at bar 0, not `window` values starting at bar 1.
- **Market regime** (`services/market_regime.py`, new, ADR-034): STRESSED/
  ELEVATED/CALM classification from SPY/QQQ trend, a VIX-proxy
  percentile/rate-of-change, and realized volatility — `ELEVATED` is the
  conservative default on mixed or missing signals, never silently CALM.
- **Tactical 8-component score** (`services/earnings_score.py`, new,
  HES-1): price vs. EMA20, 20-day relative strength vs. SPY, 5-day
  momentum, a documented volume-accumulation rule, forecast EPS growth
  vs. prior-year actual, analyst coverage (≥4 for full quality), SPY vs.
  EMA20, and median prior-gap bias (≥2 events) — `total_score` is a
  literal count of `PASS` components, never a weighted blend.
- **Investment lane** (`services/investment_quality.py`, new): 9
  independent component scores (growth, margin trend, balance-sheet/
  cash-flow quality, valuation, earnings-revision direction, sector
  durability, long-term relative strength, catalysts/event risk,
  portfolio diversification) plus a standalone `hard_disqualified` veto
  (going-concern flag or an unresolved data-quality issue) that no
  combination of passing components can override.
- **Expected move & baseline eligibility** (`services/expected_move.py`,
  `services/baseline_eligibility.py`, new): expected move stores ATR%,
  historical median gap%, and option-implied% separately;
  `selected_expected_move_pct = max(ATR%, historical median gap%)`
  always (option-implied is a diagnostic comparison only, never fed
  back in). Baseline eligibility is a 9-condition AND gate (direction
  score ≥6/8, expected move ≥4%, ADV ≥$50M, ≥3 analysts, verified event
  timing, fresh evidence, portfolio/sector capacity, no unresolved DQ
  issue) — any single failing condition vetoes eligibility regardless of
  the others.
- **Post-earnings confirmation** (`services/post_earnings_confirmation.py`,
  new, HES-4): EPS/revenue surprise (denominator uses `abs(estimate)` so
  a company estimated to lose money that beats by losing less still
  reads as a positive surprise), guidance direction vs. prior/consensus
  (`NONE_PROVIDED` is its own explicit outcome), initial gap direction,
  reversal/failed-breakout (from daily open/close alone), volume ratio,
  sector/market alignment, and 30-/60-minute range + VWAP hold —
  correctly reporting `CAPABILITY_UNAVAILABLE` (not `FAIL`/`MISSING_DATA`)
  when no intraday feed is entitled. Three independent gates (results,
  guidance, market reaction), never blended into one pass/fail.
- **Persistence + diagnostics API** (`services/persist_feature_results.py`,
  `routers/feature_diagnostics.py`, API area 21, new): one write path
  from any lane's pure compute result into the schema above; 4 read-only
  endpoints (generic components-by-subject, plus a "latest snapshot"
  view per lane) showing every component's value, status, source,
  calculation version, and as-of time. Live-verified end to end: an
  eligible synthetic MRVL earnings event (8/8 direction score, all 9
  eligibility conditions pass) and a rejected synthetic AMD event (1/8,
  multiple failing conditions including an `INSUFFICIENT_HISTORY`
  component) both persist and serve correctly —
  `src/tradingos_api/scripts/demo_prompt5.py`.
- **Tests:** 226 backend tests (up from 166) — golden vectors for the
  8-component score (all-pass, all-fail, and a mixed case exercising
  `INSUFFICIENT_HISTORY`/`MISSING_DATA`), trusted-library comparison,
  insufficient-history/missing-data/split-adjustment-matters edge cases,
  missing-options and baseline-selection cases for expected move, the
  9-condition eligibility AND gate, investment-quality's veto and
  independent-component behavior, post-earnings' sign/denominator and
  capability-vs-missing-data cases, market-regime classification, and a
  future-data leakage test reusing Revision Prompt 4's
  `policy/point_in_time.py` guard against P5 snapshot cutoffs (no new,
  parallel leakage rule invented). `ruff`/`mypy --strict` clean across
  `src/`. Frontend untouched.
- **Docs:** docs/DATA_DICTIONARY.md §11, docs/ER_DIAGRAM.md §15,
  docs/API_CONTRACTS.md area 21, this entry, docs/TEST_EVIDENCE.md,
  docs/DEPENDENCIES.md.

## Revision Prompt 4 (2026-08-06) — point-in-time market/earnings/guidance/news/broker-capability ingestion

**No prior implementation existed to inspect** — same documented gap as
R2/R3 — this prompt's own scope (provider abstractions, ingestion, data
quality, provider diagnostics; explicitly not recommendations or orders)
didn't depend on one.

- **Schema (additive):** `EarningsTimingCategory` gains `TIME_NOT_SUPPLIED`/
  `DATE_UNCONFIRMED` (kept alongside R3's `UNKNOWN`, never removed); a
  nullable `usable_at` point-in-time cutoff column on `news_items`,
  `earnings_guidance_items`, `earnings_consensus_snapshots`,
  `earnings_revisions`, `fundamentals_snapshots`; `eps_dispersion` on
  consensus snapshots; `guidance_midpoint`/`units` on guidance items;
  `invalidates_earnings_interpretation`/`note` on corporate actions
  (backfilled `false`); two new generic-ledger tables
  (`earnings_event_corrections`, `provider_ingestion_records`). Migration
  hand-verified upgrade → downgrade → upgrade against the real seeded
  dev database — `ALTER TYPE ... ADD VALUE IF NOT EXISTS` handles the
  two new enum values (Postgres has no `DROP VALUE`, documented as a
  downgrade no-op). Full detail: docs/DATA_DICTIONARY.md §10,
  docs/ER_DIAGRAM.md §14.
- **15 provider interfaces** (`providers/*.py`, ~11 files): `InstrumentReferenceProvider`,
  `MarketQuoteProvider`, `HistoricalBarsProvider`, `CorporateActionsProvider`,
  `FundamentalsProvider`, `EarningsCalendarProvider`, `EarningsConsensusProvider`,
  `AnalystRevisionProvider`, `CompanyGuidanceProvider`, `NewsProvider`,
  `OfficialFilingProvider`, `MacroProvider`, `VolatilityIndexProvider`,
  `OptionsExpectedMoveProvider`, `BrokerCapabilityProvider` — each with
  its own capability-metadata model and its own `NotConfigured`/
  `Unavailable` exceptions, kept interface-specific even where one
  vendor implements several. 7 backed for real by Alpaca
  (`providers/alpaca_evidence.py`, verified against the live API — see
  Test Evidence); 8 synthetic/fixture-backed
  (`providers/synthetic_evidence.py`, honestly `is_live_data: false`) —
  no paid vendor, per this prompt's own explicit instruction;
  docs/BLOCKING_DECISIONS.md #1/#2 remain open, unresolved by this pass.
- **Point-in-time policy** (`policy/point_in_time.py`, new): general
  `assert_evidence_usable_by_cutoff()`/`assert_snapshot_evidence_usable_by_cutoff()`
  — a feature snapshot may use only evidence with `usable_at <=` its
  cutoff, generalized beyond R3's earnings-actual-specific guard.
- **9 data-quality gates** (`services/data_quality.py`): conflicting
  dates/timing, too few analysts, stale quote/bars, missing split
  adjustment, duplicate news, symbol mapping conflicts, guidance unit/
  fiscal-period mismatch, implied-move timestamp inconsistency, market-
  calendar/early-close mismatch — each a pure function returning a
  `DataQualityFinding | None`, written into the existing
  `DataQualityEvent` table (Phase 8) via `record_finding()`.
- **Ingestion services** (`services/ingest_evidence.py`): one function
  per evidence type, each idempotent (safe replay), each recording a
  `ProviderIngestionRecord`. Earnings-calendar corrections write a new
  `EarningsEventCorrection` + linked `Alert` rather than a silent
  overwrite (live-verified — see Test Evidence).
- **Provider diagnostics API** (`routers/provider_diagnostics.py`, API
  area 20): status, last-sync, freshness, earnings-calendar verification
  queue, symbol quarantine, conflicting-source review, raw-to-normalized
  lineage — all read-only, no endpoint triggers ingestion.
- **Tests:** 166 backend tests (up from 126), all 9 explicitly required
  P4 tests present and passing (point-in-time cutoff/future-data
  rejection, date/time corrections, BEFORE_OPEN/AFTER_CLOSE session
  mapping, analyst revision history across 7/30/90-day windows,
  synthetic-official-release guidance parsing, split-adjusted historical
  gaps, provider outage/partial data, idempotent replay, prompt-
  injection-in-news treated as untrusted data). `ruff`/`mypy --strict`
  clean across all 137 `src/`+`tests/` files. Frontend untouched.
- **Docs:** docs/PROVIDER_MATRIX.md, docs/DATA_DICTIONARY.md §10,
  docs/ER_DIAGRAM.md §14, docs/API_CONTRACTS.md area 20, this entry,
  docs/TEST_EVIDENCE.md.

## Revision Prompt R3 (2026-08-06) — backward-compatible schema and API migration

**No "Prompt 3" implementation existed to inspect** — same documented
gap as R2's "no Prompt 2" — R3's own scope (additive migration against
the real Phase 8 schema + new API areas) doesn't depend on it.

- **Domain model (additive, ADR-050):** ~35 new tables + 2 backward-
  compatible column adds (`recommendations.mode`, `strategy_definitions.family`,
  both backfilled for existing rows) across 6 new/extended model files —
  decision taxonomy, investment thesis, earnings evidence, morning plan,
  order authority, strategy governance. Full detail:
  docs/DATA_DICTIONARY.md §9, docs/ER_DIAGRAM.md §§10-13.
- **Migration** (`ce0a85382604_r3_*.py`, revises `ece90645a84b`): hand-
  verified upgrade -> downgrade -> upgrade round trip against the real
  seeded dev database; every native-enum reuse across the migration
  (`order_side`, `order_type`, `time_in_force`, `recommendation_confidence`,
  `alert_delivery_status`, `strategy_version_status`) uses
  `create_type=False` to avoid a duplicate-type error, and every brand-
  new enum type added via `op.add_column()` (rather than
  `op.create_table()`) is explicitly `.create()`d first — both gotchas
  this project has hit before (`eed7cb451bdc`) and now avoided the same
  way. Backfill defaults verified to populate every pre-existing row
  (`recommendations`: 2/2 now `TACTICAL`, `strategy_definitions`: 1/1
  `GENERIC`, `earnings_events`: 1/1 `UNKNOWN` timing).
- **Policy** (`policy/earnings_evidence.py`, new): pure, DB-agnostic
  `assert_actual_not_leaked_into_pre_event_snapshot()` (HES-7) — rejects
  linking an `EarningsActual` to a pre-event snapshot whose
  `evidence_cutoff` predates the actual's `usable_at`.
- **Services** (`services/order_authority.py`, new): `compute_bound_fields_hash()`
  (fixed-order SHA-256 over `ApprovalBoundFields`, ADR-048) and
  `assert_can_transition_to_approved()` (combined legal-transition +
  wall-clock-expiry guard — an approval past `expires_at` is denied even
  if nothing has marked it `EXPIRED` yet).
- **API — 19 areas total, 7 new** (docs/API_CONTRACTS.md §§13-19): morning
  plan (latest/version-history/rerun/quality-status), investment
  recommendations + thesis detail, tactical recommendations, earnings
  events (calendar/detail/post-event-confirmation), order proposals
  (create/get/policy-evaluation), order approvals (create/get/approve/
  reject/expire/invalidate), kill-switch status (added to the existing
  settings area). **No live broker submission endpoint added** — an
  `OrderApproval` reaching `APPROVED` is this revision's final state.
- **Seed data**: `scripts/seed_phase8.py::_seed_r3()` — one representative
  example of every new bounded context (an AMD investment thesis with
  full valuation/catalyst/risk/status-history detail; an upcoming AMD
  earnings event pre-event-only, and an already-reported MRVL earnings
  event with an actual + post-event confirmation, demonstrating the
  structural pre/post-event distinction; a `FINAL`/`COMPLETE` morning
  plan version; a full proposal -> policy-evaluation -> pending-approval
  chain with a real computed `integrity_hash`; kill-switch/mode-history/
  attestation rows; an earnings-strategy definition + eligibility
  snapshot; a decision-policy version and a risk-policy version echo).
  Applied to the real dev database (idempotent — the whole-script guard
  means it only runs once; `_seed_r3` itself was verified separately
  against a rollback-wrapped transaction before being applied for real).
- **Tests:** 126 backend tests (up from 100), all 8 explicitly required
  R3 tests present and passing (migration round trip verified manually;
  existing-clients-compatible + investment/tactical-cannot-be-confused in
  `test_r3_backward_compatibility.py`; pre-event-rejects-future-actuals in
  `test_policy_earnings_evidence.py`; approval-hash-changes +
  expired-cannot-approve in `test_services_order_authority.py`;
  reruns-create-versions in `test_morning_plan_endpoints.py`; money/
  quantity precision extended in `test_precision.py`). `ruff`/`mypy
  --strict` clean across all new/edited `src/` files. Frontend untouched
  (0 new frontend tests this pass — R3 is backend-only).
- **Docs:** docs/DATA_DICTIONARY.md §9, docs/ER_DIAGRAM.md §§10-13,
  docs/API_CONTRACTS.md §§13-19 + intro paragraph, this entry,
  docs/TEST_EVIDENCE.md.

## Revision Prompt R2 (2026-08-06) — scaffold and navigation compatibility patch

**No "Prompt 2" implementation existed to inspect** — docs/TASKS.md's
Prompt 2-17 roadmap (dual decision-lane schema migration, etc.) is still
entirely unimplemented as of this pass; R2's own scope (frontend scaffold
+ one minimal read-only backend endpoint) doesn't depend on it, so this
was a documented gap, not a blocker.

- **Backend (minimal, additive):** `GET /api/v1/settings/operating-mode`
  (`routers/settings.py`) — a config passthrough
  (`Settings.operating_mode`, default `RESEARCH_ONLY`) reporting the
  current `OrderAuthorityMode` and a derived RESEARCH/PAPER/LIVE
  `environment_label`. This is the one and only source of truth the
  frontend's environment banner and operating-mode status component
  read — never client storage. Reporting only; not wired into any
  order-mutating router. 4 new tests; OpenAPI snapshot updated.
- **Frontend — new routes** (all synthetic placeholders, `apps/web/app/`):
  `/` (Morning Dashboard, now the default landing route, replacing the
  old Phase 1-7 Dashboard which moved to `/legacy-dashboard` rather than
  being deleted), `/investment`, `/tactical`, `/earnings`, `/approvals`,
  `/orders`, `/journal`, `/performance`, `/watchlists`, `/alerts`,
  `/agent-review`, `/settings`. Every pre-existing route (`/symbols`,
  `/portfolio`, `/ask`, `/backtests`, `/strategy-versions`) is untouched.
- **Frontend — persistent environment banner** (`EnvironmentBanner.tsx`,
  mounted in `app/layout.tsx`): shows RESEARCH/PAPER/LIVE from the new
  API endpoint, in every state (loading/success/error — never
  unmounts), with no code path that reads a URL/query parameter at all
  (proven by a structural source-inspection test, not just absence of a
  bug today).
- **Frontend — nonfunctional operating-mode status** (`OperatingModeStatus.tsx`):
  read-only readout of the exact mode string, from the API.
- **Frontend — 8 new reusable UI primitives** (`components/ui/`):
  `DecisionLaneBadge`, `DataFreshnessBadge`, `EvidenceCompletenessIndicator`,
  `ApprovalRequiredBadge`, `EventRiskWarning`, `IncompletePlanBanner`,
  `SourceTimestamp`, `OrderStateTimeline` — plus a shared `PageState`
  component covering all 7 required non-happy-path states (empty,
  loading, stale, disconnected, permission, market-closed, no-action).
  Every primitive conveys meaning through text, not color alone
  (`__tests__/ui-primitives-a11y.test.tsx`).
- **No submission behavior added** — no new page calls any order-
  mutating endpoint; verified structurally (no new `apiPost` call
  targets `/orders` anywhere in this revision's diff).
- **Tests:** 53 frontend tests (up from 20), 100 backend tests (up from
  96) — all passing. `pnpm typecheck`/`pnpm lint` and `ruff`/`mypy`
  clean.
- **Docs:** docs/UX_MAP.md reconciled (R1's placeholder paths vs. R2's
  actual scaffolded paths, itemized), docs/API_CONTRACTS.md (new
  endpoint), this entry.

## Revision Prompt R1 (2026-08-05) — product and architecture delta review, approved

Documents-only, per R1's own instruction ("do not implement application
code ... stop for approval without changing code"). Delivers:

- New: docs/MORNING_PLAN_SPEC.md, docs/HYBRID_EARNINGS_STRATEGY.md,
  docs/ORDER_AUTHORITY_MODEL.md.
- Updated: docs/PRODUCT_REQUIREMENTS.md (FR-51–FR-61 + new AC-09–AC-26),
  docs/ARCHITECTURE.md (R1 trust-boundary diagram + all 10 architecture
  questions answered), docs/UX_MAP.md (Morning Decision Dashboard rename,
  new Orders page, operating-mode selector, lane badges, buy-and-hold-vs-
  tactical explainer, earnings-workflow callout), docs/MVP_PLAN.md
  (explicit paper-release vs. live-confirmed-release split).
- docs/DECISIONS.md — ADR-046 (dual decision lanes: two rows + a `mode`
  column, not two tables), ADR-047 (scheduler owns job lineage via a new
  `MorningPlanRun` entity), ADR-048 (order approval binds an immutable
  snapshot, not the live order row), ADR-049 (Cowork delivery is
  one-way/read-only/post-publication only).
- docs/RISK_REGISTER.md (R-11–R-15) and docs/THREAT_MODEL.md (boundaries
  5-6: Cowork delivery, Order Authority Gate/broker-adapter isolation).
- docs/BLOCKING_DECISIONS.md #11 (new) — **one confirmed conflict**: R1's
  recommended 15%/25% max-position/max-sector defaults vs. Phase 8's
  already-shipped, already-seeded 20%/40% `RiskPolicy` defaults.
  Recommended resolution is backward-compatible (update the seed/model
  default values when the sizing gates are actually wired, Prompt 6 — no
  migration needed, the column is already user-configurable) and is not
  acted on pending your confirmation.
- Full per-requirement traceability to a recommended Prompt 2–17
  roadmap and a planned acceptance-test id, embedded in each affected
  document rather than duplicated in one master table.

**Nothing is implemented.** No migration, model, router, or test changed.
Waiting for explicit approval before any numbered implementation prompt
begins.

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
