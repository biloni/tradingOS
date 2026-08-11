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
any value in this layer, no recommendation created yet), and Revision
Prompt 6 (evidence-bound Investment Committee and Tactical Trading Desk,
shipped — 8 + 9 real committee roles run through one shared LLM adapter
and one shared 15-field Agent Contract, a code-enforced deterministic-veto
override, cost/timeout/fallback guardrails, and a side-by-side
comparison view; live-verified against the real Anthropic API, no orders
or sizing produced), and Revision Prompt 7 (decision policy, risk
manager, and hybrid earnings recommendation engine, shipped — the
9-step deterministic decision pipeline, the 10 hard vetoes, HES-3
position sizing, HES-4/HES-6 post-confirmation gating, HES-5
gap-through-stop disclosure, the remaining Investment/Tactical action
plan fields, and extended recommendation list/detail + a safe
policy-configuration screen; no broker calls), and Revision Prompt 8
(portfolio, lane attribution, trade journal, and reconciliation,
shipped — the FIFO accounting engine deriving holdings/cash/lots/
realized P&L from immutable events, per-lane lot attribution with a
lane-scoped `Trade` round-trip, corporate action application, corrections
through reversal, idempotent CSV import, broker-aggregate reconciliation,
per-lot Investment/Tactical holding guidance, and the composed trade
journal view; demonstrated with a symbol held simultaneously as an
Investment thesis and a Tactical earnings trade), Revision Prompt 9
(Morning Decision Dashboard and market-calendar scheduler, shipped — a
hardcoded documented 2026 NYSE/Nasdaq calendar with DST-safe
America/Los_Angeles display, an idempotent/retryable/resumable/versioned
scheduler decision function, the 12-stage plan-generation orchestrator
that curates already-computed recommendations rather than running
committees live (ADR-055), the dashboard read API with a richer
computed `plan_status` than the stored completeness label, and
Markdown export/in-app notification/read-only Cowork delivery; no
broker calls, no order submission from the read-only delivery path),
and Revision Prompt 10 (paper broker execution, approval queue, and
bracket lifecycle, shipped — the single broker-boundary entry point
(`services/order_execution.py`), idempotent/ambiguous-timeout-safe
paper submission, native-vs-emulated bracket orders with a mandatory
reliability disclosure, a disabled-by-default versioned paper
auto-policy that can never override a hard veto (ADR-058), the OA-9
kill switch and cancel-open-orders controls, and OA-6 fail-closed
paper-only enforcement; demonstrated end-to-end via both the real
Alpaca paper sandbox and a deterministic synthetic broker, no live
order submission anywhere in the codebase), and Revision Prompt 11
(active position monitor and post-earnings confirmation engine,
shipped — earnings-actuals ingestion, the alerts engine
(`create_or_dedupe_alert()`, deduplicated/expiring/evidence-linked/
audited), the 10-step post-earnings confirmation workflow reusing
Revision Prompt 5/7's scoring/gate/pipeline functions with reversal
invalidation (ADR-059) and HES-6 enforcement, the active position
monitor's 9 alert types, and the active-position-cards/event-timeline/
confirmation-checklist/alert-center read screens; demonstrated
end-to-end with a real Alpaca-backed market-data layer already live,
no new paid vendor contracted for reported-results data), and Revision
Prompt 12 (performance, decision quality, and recommendation-versus-
reality analytics, shipped — a shared DB-free statistics library backing
both this revision's live-portfolio metrics and the not-yet-built
Revision Prompt 13 backtest engine (ADR-062), portfolio/strategy/
recommendation-vs-reality/morning-plan-quality read services and their
16 endpoints plus 6 required charts, and an AI coach whose sample-size
guardrail is a code gate before any LLM call, never a prompt instruction
(ADR-061); no new schema — every metric is derived from data that
already existed, except `HypotheticalTradeOutcome` which is written to
for the first time), and Revision Prompt 13 (event-driven backtesting
and walk-forward validation, shipped — an event-driven backtest engine
reusing four already-pure live functions verbatim (tactical scoring,
expected-move selection, position sizing, and Prompt 12's own exit-
simulation walk, ADR-063), all 8 required strategy variants, a locked
baseline-reproduction scenario run honestly against a deterministic
synthetic universe with every deviation from the prompt's stated targets
explained rather than forced, a full validation grid (score/expected-
move/risk-budget sensitivity, lane-variant comparison, semiconductor-
concentration subset, 3-window walk-forward), a go/no-go report, golden/
regression tests, and 7 new API endpoints; this dev environment's real
market/earnings history — ~3 months across 6 instruments, 3 total
events — was nowhere near sufficient for the prompt's 2-year/~25-trade
requirements, honestly disclosed rather than glossed over), and Revision
Prompt 14 (controlled learning, calibration, and strategy governance,
shipped — calibration across all 7 required segmentation axes with
structural sparse-bin suppression, agent evaluation's 6 required
dimensions including the "data revisions" category proven against a
real `EarningsEventCorrection` row, and a propose -> approve -> activate
-> rollback change-governance engine where self-activation is
structurally unrepresentable in the state machine (never just a
convention) and neither activation nor rollback ever touches
`RecommendationVersion` history, proven byte-for-byte, ADR-064; no new
tables — calibration and agent evaluation compute on demand from
existing rows, and the pre-existing `ModelChangeProposal`/
`ModelChangeApproval` schema fixtures get their first live service), and
Revision Prompt 15 (executive-quality morning dashboard UX, shipped —
`app/page.tsx` rebuilt against real `GET /api/v1/morning-plan/dashboard`
data (status strip, portfolio strip, and Prompt 15's own 8-section
primary layout, no longer the Revision Prompt R2 static scaffold),
one-click evidence/committee-disagreement/risk/audit drill-in per card,
a real order-approval confirmation page (`/approvals/[id]`) built on the
already-shipped Revision Prompt R3/10 approval flow with a two-click
confirm gate at both approve and submit, manual dark/light theming and
an off-canvas mobile nav drawer app-wide, and — found live-verifying the
above in a browser — three pre-existing frontend/backend contract
mismatches fixed (`/portfolio`, `/legacy-dashboard`, `/symbols` were all
calling nonexistent endpoints from an earlier backend generation,
ADR-065; `/strategy-versions`'s complete absence of a backend was
flagged, not built, as out-of-scope real UX debt), and Revision Prompt
16 (paper beta security, deployment, and reliability — shipped: real
password-gated authentication with sessions and step-up re-auth for
sensitive actions (ADR-066), CSRF/security-header/CORS hardening, a
documented threat model, secret/dependency scanning (gitleaks +
pip-audit + `pnpm audit`) now wired into a new GitHub Actions CI
pipeline alongside lint/type/test/build for both apps, structured/
redacted logging, honest health/readiness reporting for every real
dependency, a job dashboard, a cost-budget-triggered kill switch,
closed idempotency gaps in order confirm/cancel/cancel-open plus a new
broker-fetched scheduled-reconciliation capability, a real in-process
always-on scheduler (APScheduler) that now actually calls the
morning-plan and reconciliation decision functions on a timer instead
of nothing calling them (still local-always-on, not deployed), tested
`pg_dump`/`pg_restore` backup/restore tooling, Dockerfiles plus a full
`docker-compose` stack (written carefully but not build-verified — this
dev machine has no Docker installed), release-gate journey tests
closing a real pre-existing gap (no test had ever driven the full
order-authority propose→approve→submit chain over HTTP), and a
release-gate proofs document (docs/RELEASE_GATE_PROOFS.md) that found
and filed — rather than rush-fixed — one real gap: the
operator-configured baseline order-authority mode isn't yet
cross-checked server-side, only the kill switch itself is; no live
broker execution exists anywhere, unchanged, and Revision Prompt 17
remains explicitly gated on this release being tagged and separately
approved to begin).
**Last updated:** 2026-08-11

## Revision Prompt 15 (2026-08-10) — executive-quality morning dashboard UX

**No schema changes.** One additive, read-only response field
(`RecommendationVersionResponse.committee_session_id`) and one new
read-only endpoint (`GET /api/v1/recommendations/versions/{version_id}`)
— see docs/API_CONTRACTS.md area 4. No trading/scoring/sizing/policy
logic changed anywhere in `apps/api`.

**The dashboard** (`app/page.tsx`, fully rebuilt): status strip (market
date, countdown, plan state, evidence cutoff, regime, operating mode,
kill switch) and portfolio strip (equity, cash, day/week P&L, drawdown,
exposure, risk budget — the latter two sourced from Revision Prompt 12's
own performance endpoint, never re-derived) sit above the fixed section
order Prompt 15 specifies: Act Now, Approval Required, Buy and Hold,
Tactical Earnings, Existing Positions, Upcoming Events, Watch/Avoid,
Data and Job Health — mapped onto Revision Prompt 9's own shipped
section keys, with Existing Positions as a client-side cross-cut (no
matching backend section key exists; docs/UX_MAP.md records this as
known UX debt) and Data and Job Health additionally surfacing
`provider_broker_status` and failed plan quality checks. Investment/
Tactical labels render as both plain text (already in every card's
headline) and an icon+text badge — never color alone, matching this
app's pre-existing badge convention.

**Evidence/audit drill-in**: `components/dashboard/EvidenceDetails.tsx`,
a `<details>` disclosure (not a modal, same precedent `ConfirmButton`
already set) showing the five `card_detail` keys immediately, plus a
lazily-loaded recommendation-version risk/committee/audit view behind
two endpoints new this revision.

**Order approval** (`app/approvals/[id]/page.tsx`, new): built directly
on the already-shipped `/api/v1/order-approvals/*` flow — the immutable
`ApprovalBoundFields` snapshot, a live pre-submission refresh, and a
`ConfirmButton`-gated approve/submit, each requiring a distinct second
click. Live-verified end-to-end against the real backend (not mocked):
a real `OrderProposal` → policy-evaluation → `OrderApproval` created via
the actual HTTP API, clicked through Approve (real state transition
PENDING → APPROVED), the pre-submission refresh (real quote/buying-power
snapshot), and two real terminal states — a hard `MANUAL`-account block
(`assert_broker_boundary_is_paper()`, OA-6, firing correctly) and this
dev environment's `RESEARCH_ONLY` operating mode correctly denying
submission, the latter surfaced by the page *before* the two-click
confirm dance rather than after.

**Cross-cutting**: manual dark/light theme (`@custom-variant dark` in
`app/globals.css` — every existing `dark:` utility across the whole app
now responds to a `.dark` class instead of only `prefers-color-scheme`,
no component file touched), a skip-link + app-wide `:focus-visible` ring
for keyboard navigation, and an off-canvas mobile sidebar drawer (fixed
a real, confirmed horizontal-overflow bug on `/` at 375px width).

**Real bugs found and fixed live** (docs/DECISIONS.md ADR-065):
`/portfolio`, `/legacy-dashboard`, and `/symbols`/`/symbols/[ticker]`
were all calling backend endpoints that don't exist (a leftover from an
earlier, integer-PK backend generation) — rewired to the real
`/api/v1/portfolio/accounts/*`, `/api/v1/orders`, `/api/v1/instruments`,
and `/api/v1/market/instruments/*` endpoints; the tests that should have
caught this were themselves mocking the phantom contract. Separately,
`/strategy-versions` has no backend at all — flagged as real, pre-existing
UX debt rather than built unprompted. The dashboard's own "Approval
Required" cards previously always claimed `NOT_YET_PROPOSED` regardless
of reality; `services/morning_plan_generate.py::_order_authority_state()`
(new, read-only) now reports the real `OrderProposal`/`OrderApproval`
state.

**Tests**: 70 new/extended frontend tests (Vitest + Testing Library) —
`page.test.tsx` rewritten for the real dashboard (7), `order-approval.test.tsx`
new (6, immutable summary, two-step confirm at both approve and submit,
real denial surfacing, upfront operating-mode block, hard pre-submission
block with its real reason), `sidebar.test.tsx` extended (+3, mobile
off-canvas toggle), `portfolio.test.tsx` and `legacy-dashboard.test.tsx`
rewritten against the corrected real contracts. Full frontend suite: 64
passed. `tsc --noEmit`, `eslint`, and `next build` (21 routes, including
the new `/approvals/[id]`) all clean. Backend: 595 passed (unchanged
count from Revision Prompt 14 plus the schema/endpoint additions above),
mypy/ruff clean.

## Revision Prompt 14 (2026-08-10) — controlled learning, calibration, and strategy governance

**Schema**: additive columns only, no new tables — extends the
pre-existing `model_change_proposals` fixture (unpopulated by any live
service since Revision Prompt R3) with `evidence_package` (JSON),
`activated_at`/`activated_by`, `rolled_back_at`/`rolled_back_by`/
`rollback_reason`, and two new `ModelChangeProposalStatus` values
(`ACTIVATED`, `ROLLED_BACK`). See docs/DATA_DICTIONARY.md §20 /
docs/ER_DIAGRAM.md §24.

**Calibration** (`services/calibration.py`): distinguishes ranking score,
direction confidence, and expected-move magnitude as three genuinely
separate axes, never blended (extends DQ-4's existing "confidence and
magnitude are different numbers" rule). `get_closed_outcomes()` pulls
every recommendation with a *determined* real or hypothetical outcome;
seven segmentation functions (confidence, score, strategy, sector,
regime, event timing, holding period) each report `sample_size`/
`is_adequate` honestly and suppress hit rate/confidence interval/Brier
score below `MIN_SAMPLE_SIZE_FOR_CALIBRATION=20`. The Wilson score
interval (`services/performance_metrics.py::wilson_confidence_interval()`,
new) was chosen over the naive normal approximation for its better
behavior at small `n` and extreme rates.

**Agent evaluation** (`services/agent_evaluation.py`): all 6 required
dimensions — factual accuracy, evidence coverage, contradiction
detection, directional usefulness, contribution after deterministic
features, minority-opinion usefulness — computed from real `AgentRun`/
`AgentOpinion`/`AgentEvidenceLink`/`CommitteeSession` data joined to real
outcomes, never a second LLM grading the first one's prose
(docs/MODEL_GOVERNANCE.md already scoped that out). Factual accuracy
uses `EarningsEventCorrection` as the checkable "data revisions" signal:
a citation of evidence tied to a later-corrected earnings event is
treated as tainted. Every metric gated at
`MIN_SAMPLE_SIZE_FOR_AGENT_EVAL=10`, independently per role.

**Change governance** (`services/change_governance.py`): `propose_change()`
(generic path, caller-supplied evidence package validated against
Prompt 14's own required-fields list) and
`propose_strategy_parameter_change()` (deep-integration path — runs
`run_backtest_splits()` against Revision Prompt 13's real engine for
train/validation/out-of-sample/walk-forward, and creates the actual
candidate `StrategyVersion` row). `approve_change()`/`reject_change()`/
`withdraw_change()` only ever touch `ModelChangeProposal.status`.
`activate_change()` is the only function that flips a subject's live
configuration, and `MODEL_CHANGE_PROPOSAL_TRANSITIONS` has no
`PROPOSED -> ACTIVATED` edge — self-activation is unrepresentable, not
discouraged. `rollback_change()` clones the proposal's own
`evidence_package["current_version_snapshot"]` into a **new**
`StrategyVersion` (never resurrects the superseded row —
`StrategyVersionStatus` has no edge back out of `SUPERSEDED`, by
design). See ADR-064 for the full reasoning.

**Routers**: new `routers/governance.py`, prefix `/api/v1/governance` —
calibration, agent-evaluation (all roles + single role), and the full
proposal lifecycle (create/create-strategy-parameter/list/detail/
approve/reject/withdraw/activate/rollback). See docs/API_CONTRACTS.md §27.

**Tests**: 46 new/extended tests — `test_calibration.py` (11, sparse-bin
suppression, regime segmentation never blending, confidence/score axis
independence, DB-level smoke test), `test_performance_metrics.py`
(+9, Brier score, Wilson interval known vector), `test_agent_evaluation.py`
(6, sparse sample, the required data-revisions category against a real
`EarningsEventCorrection`, directional usefulness), `test_change_governance.py`
(9, no-self-activation, full state machine, version comparison snapshot,
never-rewrites-history), `test_governance_endpoints.py` (11, full
lifecycle via the API, 404s, 422 on an incomplete evidence package); full
suite: 595 passed. `mypy src/` and `ruff check src/ tests/` both clean.

**Demo**: `demo_prompt14.py` — calibration against real dev-DB closed
outcomes (honestly inadequate on most segments given this dev
environment's small sample), agent evaluation showing factual accuracy
fall live after seeding 10 runs that cite a newly-corrected earnings
event, and the full propose -> reject-premature-activation ->
approve -> activate -> rollback lifecycle with a byte-for-byte proof
that a pre-existing `RecommendationVersion` survives unchanged.

## Revision Prompt 13 (2026-08-09) — event-driven backtesting and walk-forward validation

**Schema**: 2 new tables (`event_backtest_runs`, `event_backtest_trades`),
4 new enums — additive, no table renamed or restructured. The legacy
`backtest_runs`/`backtest_trades` (Phase 8-era, `strategy_version_id`-keyed)
are untouched; this revision did not extend them (ADR-063 explains why).
See docs/DATA_DICTIONARY.md §19 / docs/ER_DIAGRAM.md §23.

**The core finding, stated up front**: this dev environment's real
`MarketBar`/`EarningsEvent` coverage (~3 months, 6 instruments, 3 total
earnings events) is nowhere near what the locked baseline scenario
(2026-02-03 to 2026-07-31, ~25 trades) or the "at least two years"
validation requirement need. Rather than forcing a match against
unreachable real-data targets, `services/backtest_data.py` generates a
deterministic (seed=42), reproducible 2-year/20-instrument synthetic
universe — reusing this project's own real, sector-diverse seeded
`Instrument` rows for identity, synthetic for price/earnings history.
The synthetic earnings-gap generator injects no relationship between an
event's score and its subsequent gap, so backtest results validate the
engine's mechanics honestly, never a fabricated live-strategy edge —
every report this revision produces says so explicitly.

**Services**: `services/backtest_data.py` (the synthetic universe
generator), `services/backtest_engine.py` (`BacktestRunConfig`, the 8
strategy dispatch functions, the chronological allocator enforcing
position/sector/concurrency caps, `run_backtest()` — reuses
`compute_tactical_earnings_score()`, `compute_expected_move()`,
`compute_tactical_position_size()`, and Revision Prompt 12's
`compute_hypothetical_outcome()` verbatim, ADR-063), `services/backtest_validation.py`
(score/expected-move/risk-budget sweeps, lane-variant comparison,
semiconductor-concentration subset, 3-window walk-forward with no
re-optimization between windows, the go/no-go report),
`services/backtest_persistence.py`.

**Routers**: new `routers/event_backtests.py`, prefix
`/api/v1/event-backtests` (distinct from the legacy `/api/v1/backtests`)
— run/list/detail/compare/download plus two live reports
(baseline-reproduction, go-no-go). See docs/API_CONTRACTS.md §26.

**Tests**: 41 new tests — `test_backtest_data.py` (7, determinism),
`test_backtest_engine.py` (14, eligibility-gate known vectors, the
required no-look-ahead category — mutating an event's own or a later
event's realized outcome never changes an earlier evaluation, exit-
simulation wiring, allocator cap/fee enforcement, all 8 strategies run
end-to-end), `test_backtest_engine_golden.py` (5, reproducibility across
runs + locked figures for the current engine behavior), `test_backtest_validation.py`
(6), `test_event_backtests_endpoints.py` (9); full suite: 549 passed.

**Demo**: `demo_prompt13.py` — the locked baseline scenario compared
against Prompt 13's own stated targets with the deviation explained, all
8 strategies, the score-threshold sweep, 3-window walk-forward, one
persisted run read back through the drill-down/download path, and the
full go/no-go report (honest recommendation: reject for paper activation
pending real multi-year data — the synthetic universe's 29 trades even
over the widened window is below any reasonable sample size, and the
data has no embedded predictive signal by construction).

**Bug found and fixed live**: `GET /api/v1/event-backtests/compare` was
originally registered after `GET /api/v1/event-backtests/{run_id}` —
Starlette's route matching is order-sensitive for same-depth paths, so
`/compare` was being swallowed as a `run_id` value (`422 uuid_parsing`
on the literal string `"compare"`). Fixed by moving the static
`/compare` and `/reports/*` routes ahead of the dynamic `/{run_id}`/
`/{run_id}/download` routes in the router file. A second bug in the same
pass: `POST /run` never called `db.commit()` (`get_db()` does not
auto-commit, confirmed by grep of every other router), so a persisted
run was invisible to any subsequent request outside the tests'
savepoint-sharing fixture — fixed by adding the explicit commit.

## Revision Prompt 12 (2026-08-09) — performance, decision quality, and recommendation-versus-reality analytics

**Schema**: none — every metric is derived on demand from existing
tables (ADR-013's derived-never-stored philosophy extended to portfolio
reporting). One exception: `HypotheticalTradeOutcome` (a schema fixture
since Revision Prompt R3) is written to for the first time, by
`compute_and_persist_hypothetical_outcome()`. See
docs/DATA_DICTIONARY.md §18 / docs/ER_DIAGRAM.md §22.

**Services**: `services/performance_metrics.py` (the shared DB-free
formula library — Sharpe/Sortino/drawdown/TWR/MWR/trade-stats/beta-
alpha/turnover/concentration, deliberately shared in advance with
Revision Prompt 13's backtest engine, ADR-062), `services/performance_portfolio.py`
(`get_equity_curve()`/`get_portfolio_performance()`, reconstructing
equity on demand from `CashLedgerEntry`/`Execution`/`MarketBar`),
`services/performance_strategy.py` (lane/pre-post-confirmation/score-
band/sector/score-threshold-sensitivity/policy-veto breakdowns),
`services/recommendation_reality.py` (`compute_hypothetical_outcome()` —
long-only, next-bar, no-look-ahead simulation reusing ADR-022's retired
backtest engine's own "assume the worse outcome under same-bar stop/
target ambiguity" discipline), `services/morning_plan_quality.py`
(on-time/completeness/check-pass rates, realized results by section,
approval-to-submission conversion), `services/performance_coach.py`
(the AI coach — see ADR-061 for its structural sample-size guardrail).

**Routers**: `routers/performance.py` extended with 16 new endpoints —
portfolio, 5 strategy breakdowns, recommendation reality, 3 morning-plan-
quality views, the AI coach, and 6 chart endpoints. See
docs/API_CONTRACTS.md §25.

**Tests**: 9 new/extended test files (`test_performance_metrics.py` — 31
known-vector tests; `test_performance_portfolio.py`; `test_performance_strategy.py`;
`test_recommendation_reality.py` — 9 hypothetical-fill edge cases;
`test_morning_plan_quality.py`; `test_performance_endpoints.py` — 14
router smoke tests; `test_performance_coach.py` — 7 tests proving the
LLM is structurally never called below the sample-size threshold) — the
6 required test categories (known vectors, cash flows, sparse samples,
open positions, benchmark calendars, hypothetical-fill edge cases) all
covered; full suite: 508 passed.

**Demo**: `demo_prompt12.py` — the AI coach called against a 0-trade
account (LLM never invoked, no API key needed) and again after 12 real
round-trip trades are built through `apply_execution()` (adequate
sample, LLM invoked through the same `run_agent_role()` guardrail every
committee role uses), portfolio return/risk/drawdown/benchmark metrics,
strategy breakdowns (including the honest 0-sample result for
unattributed manual fills), a hypothetical-fill simulation for an
`IGNORED` recommendation, and the morning-plan-quality sparse result —
all against real Postgres state.

**Bug found and fixed while writing the demo**: the demo script built 12
round-trip trades via `apply_execution()` but only flushed after
creating each `Order`/`Execution` row, not after `apply_execution()`
itself — `SessionLocal` is configured with `autoflush=False`
(`db/session.py`), so the very last round trip's `Trade.realized_pnl`/
`status=CLOSED` mutation stayed pending in the session and was invisible
to the immediately-following `get_portfolio_performance()` read (11
trades reported instead of 12) even though every prior round trip's
mutation had already been flushed incidentally by the *next* round
trip's own `Order`/`Execution` inserts. Not a bug in
`services/performance_portfolio.py`/`performance_metrics.py` (both read
whatever is actually flushed correctly) — fixed by adding the missing
`db.flush()` in the demo script itself, a `SessionLocal`-autoflush
gotcha worth remembering for any future direct-session script.

## Revision Prompt 11 (2026-08-09) — active position monitor and post-earnings confirmation engine

**Schema**: `alerts.alert_type`/`expires_at`/`dedup_key`/`evidence_type`/
`evidence_id`, new `alert_status_events` table, new
`post_earnings_workflow_runs` table, new `PostEarningsWorkflowStatus`
enum, `ApprovalInvalidationReason.THESIS_INVALIDATED` — see
docs/DATA_DICTIONARY.md §17 / docs/ER_DIAGRAM.md §21. Making
`alert_type` required exposed 2 pre-existing call sites outside
Prompt 11's own vocabulary; resolved with a 19th value,
`SYSTEM_NOTIFICATION` (ADR-060).

**Providers**: `providers/earnings_actuals.py`
(`EarningsActualsProvider` Protocol) + `SyntheticEarningsActualsProvider`
(the 16th provider-diagnostics entry — no real reported-results vendor
exists yet, docs/PROVIDER_MATRIX.md).

**Services**: `services/alerts_engine.py` (`create_or_dedupe_alert()` —
the one function every new alert-producing call site goes through;
`transition_alert_status()`; `expire_stale_alerts()`),
`services/post_earnings_workflow.py` (`run_post_earnings_workflow()` —
the 10-step state machine; see ADR-059 for what its 4 statuses actually
mean), `services/position_monitor.py` (`evaluate_position()` — the 9
alert types this module owns, vs. the 9 the workflow/order-authority
own). `services/ingest_evidence.py` gains `ingest_earnings_actuals()`.

**Routers**: new `routers/monitoring.py`
(`GET /monitoring/positions`, `GET /monitoring/positions/{id}/timeline`,
`GET /monitoring/positions/{id}/confirmation-status`);
`routers/alerts.py` extended with the new fields, lazy expiry on every
read, and an audited `PATCH`. See docs/API_CONTRACTS.md §24.

**Tests**: 60 new tests across `test_ingest_earnings_actuals.py` (7),
`test_alerts_engine.py` (9), `test_post_earnings_workflow.py` (14),
`test_position_monitor.py` (25, including the required-category
additions), `test_monitoring_endpoints.py` (5) — the 7 required
categories (gap, reversal, stale data, conflicting guidance, duplicate
release, worker restart, existing bracket orders) all covered; full
suite: 435 passed.

**Demo**: `demo_prompt11.py` — earnings-actuals duplicate-release
idempotency, a full eligible confirmation reaching `TRADE_ADD_CONFIRMED`
via a real (synthetic-LLM-backed) Tactical Trading Desk call, a
worker-restart replay, a beat-with-lowered-guidance conflict, a
reversed-reaction invalidation, HES-6's absolute negative-gap failure,
and the active position monitor's stale-data/stop/gap-risk/earnings
checks — all against real Postgres state, verified live via the running
API afterward.

**Bug found and fixed while running the demo against the live API**:
the long-running `uvicorn` dev server process predated this revision's
`SYSTEM_NOTIFICATION` enum addition (added mid-session to
`models/enums.py`), so its in-memory SQLAlchemy enum mapping didn't
know the new Postgres value existed — `GET /api/v1/alerts` 500'd with
`LookupError: 'SYSTEM_NOTIFICATION' is not among the defined enum
values` the moment it read a row using it. Not a code bug (the fix was
a server restart, not an edit) — recorded here because it's the same
class of "stale long-running dev process" issue documented earlier in
this revision's own session history, now specifically tied to a
Postgres enum value added without a server restart.

## Revision Prompt 10 (2026-08-09) — paper broker execution, approval queue, and bracket lifecycle

**Promoted docs/ORDER_AUTHORITY_MODEL.md from architecture-only to
mostly-implemented** (status note added at the top of that document).
One deliberate deviation from its original text: a missing/stale quote
at submission time now transitions the approval straight to
`INVALIDATED` rather than leaving it `APPROVED` "waiting on a quote" —
documented inline in that file, reasoning in docs/DECISIONS.md.

**Schema**: `approval_bound_fields.quote_price_at_approval`,
`broker_submission_attempts.resulting_order_id`/`request_snapshot`/
`response_snapshot`, `order_approvals.auto_policy_version_id`,
`BrokerSubmissionOutcome.TIMEOUT_UNKNOWN`, two new tables
(`paper_auto_policy_versions`, `cancel_open_orders_events`), one new
enum (`KillSwitchBehavior`) — see docs/DATA_DICTIONARY.md §16 /
docs/ER_DIAGRAM.md §20.

**Services**: `services/order_execution.py` (the sole broker-boundary
caller — `submit_paper_order()`, `submit_protective_leg()`,
`poll_and_reconcile_fills()`, `cancel_order_at_broker()`,
`refresh_and_recalculate()`), `services/bracket_execution.py`
(native-vs-emulated + `BRACKET_EMULATION_DISCLOSURE`),
`services/paper_auto_policy.py` (`evaluate_auto_submission()` — see
ADR-058), extensions to `services/order_authority.py`
(`compute_effective_mode()`, `assert_broker_boundary_is_paper()`,
kill-switch activate/deactivate, `price_move_requires_invalidation()`).

**Providers**: `providers/synthetic_paper_broker.py`
(`SyntheticPaperBrokerProvider`/`SyntheticBrokerCapabilityProvider` —
deterministic, no Alpaca credentials required),
`providers/synthetic_market_quote.py`; `core/dependencies.py`'s
`get_broker_provider()`/`get_broker_capability_provider()`/
`get_market_quote_provider()` fall back to these automatically when no
Alpaca credentials are configured (principle 5), so
`demo_prompt10.py`/`tests/test_order_execution.py` never need network
access. `providers/broker.py` gains `client_order_id`/bracket-leg
fields, `find_order_by_client_id()`, and `BrokerSubmissionAmbiguous`.

**Routers**: `routers/order_authority.py` gains
`GET /order-approvals/{id}/refresh` and
`POST /order-approvals/{id}/submit` (the only two HTTP routes that
reach a broker); `routers/orders.py` gains `POST /orders/cancel-open`;
`routers/settings.py` gains kill-switch activate/deactivate and an
effective-mode-aware `GET /operating-mode`; new
`routers/paper_auto_policy.py` (CRUD). See docs/API_CONTRACTS.md §23.

**Tests**: `tests/test_order_execution.py` (22 tests, the 11 required
categories — bracket lifecycle, partial fill/partial exit, rejection,
accepted-order timeout, duplicate click, approval expiration, quote
changes outside tolerance, cancel/replace race, gap through stop,
broker/local reconciliation mismatch, attempted live configuration
fails closed — plus the broker-boundary single-entry-point structural
test), plus 2 new `tests/test_alpaca_paper_broker.py` tests guarding
the stop-order fix below. Full suite: 375 passed.

**Demo**: `demo_prompt10.py` — manual-approval flow through a real
fill and reconciliation, a duplicate-click no-op, an emulated bracket
with both protective legs submitted post-fill, a kill switch
invalidating a pending approval, and a paper auto-policy evaluation
correctly blocked by an active hard veto despite otherwise qualifying.
Also live-verified once against the real Alpaca paper sandbox (the dev
environment's configured credentials) via a full HTTP round trip
through `TestClient` — propose → policy-evaluate → approve → refresh →
submit → duplicate-submit — before switching the demo script itself to
the deterministic synthetic broker for reproducibility.

**Bug found and fixed during this revision's own documentation pass**:
`AlpacaPaperBrokerProvider.submit_paper_order()` originally only
branched on `"limit"` vs. everything-else-is-market, so a `STOP` or
`STOP_LIMIT` order (e.g. `services/bracket_execution.py`'s emulated
stop-loss leg) would have silently reached the real Alpaca client as a
plain market order, and `PaperOrderRequest` had no `stop_price` field
at all for `services/order_execution.py` to populate in the first
place. Fixed: `PaperOrderRequest.stop_price` added,
`services/order_execution.py`'s two request-building sites populate it
from `ApprovalBoundFields.stop_price`/the protective-leg price, and
`AlpacaPaperBrokerProvider` now sends a native `StopOrderRequest`/
`StopLimitOrderRequest` for those two order types
(`tests/test_alpaca_paper_broker.py::test_stop_order_sends_a_native_stop_order_request`
guards against the regression). The deterministic synthetic broker
(used by all other tests and the demo) never had this gap, since it
does not distinguish order types beyond market-fills-immediately.

## Revision Prompt 9 (2026-08-08) — Morning Decision Dashboard and market-calendar scheduler

**Promoted docs/MORNING_PLAN_SPEC.md from architecture-only to
implemented**, with one deliberate deviation from its original text:
the spec's original "Fixed section grouping" named 7 sections including
`Hold/Manage`, `Investment Watch`, `Tactical Watch`, and `Avoid`; this
revision's own live prompt text specified a different, more detailed
hierarchy (`Buy and Hold`, `Tactical Trades`, `Watch and Avoid`,
`Upcoming Events`) which is what actually shipped — the newer, more
detailed live instruction superseded the earlier architecture-only
sketch, consistent with how this project has resolved every prior
architecture-doc/live-prompt conflict. `models/enums.py::MorningPlanSectionKey`
keeps the four old values (documented as superseded, not removed —
nothing currently pattern-matches against them) alongside the four new
ones the orchestrator actually writes.

- **Market calendar** (`services/market_calendar.py`, new): a
  hardcoded, documented `NYSE_HOLIDAYS_2026` (10 dates) plus the
  existing `KNOWN_EARLY_CLOSE_DATES_2026` (Revision Prompt 4) — one
  source of truth, not duplicated. `resolve_trading_day()` always
  publishes a `skip_reason` string when a date isn't a trading day,
  never a bare `False`. `zoneinfo.ZoneInfo` resolves
  America/Los_Angeles and America/New_York offsets per-date, verified
  correct across both the March 2026 spring-forward and November 2026
  fall-back transitions (`tests/test_market_calendar.py`).
- **Scheduler** (`services/morning_plan_scheduler.py`, new):
  `decide_schedule()` is a pure function of an explicit `now_utc`
  parameter — never reads the wall clock internally — so a controllable
  clock can drive it deterministically in tests and the demo. A
  `COMPLETED` run for a (date, label) blocks further attempts; a
  `FAILED` or stuck-`RUNNING` (past `STUCK_RUN_TIMEOUT` = 15 minutes,
  modeling a crashed worker) attempt does not, and a fresh attempt gets
  an incremented idempotency-key suffix
  (`morning-plan:{date}:{label}:attemptN`).
- **12-stage generation orchestrator** (`services/morning_plan_generate.py`,
  new): curates the most recent already-computed `RecommendationVersion`
  per candidate rather than invoking Revision Prompt 6's committees or
  Revision Prompt 7's decision pipeline live — see docs/DECISIONS.md
  ADR-055 for the full reproducibility/latency rationale. A
  recommendation older than `STALE_RECOMMENDATION_AGE` (20 hours,
  relative to the plan's own evidence cutoff) is routed to Data
  Problems rather than shown as fresh and actionable; a majority-stale
  plan is labeled `INCOMPLETE`, never silently downgraded to a
  false-confidence `COMPLETE`. Every held position with an open lot is
  evaluated regardless of watchlist membership; a lot whose source
  recommendation says exit/trim/tighten-stop is routed to Act Now
  regardless of lane. `ACTIONABLE_SECTION_CAP = 3` caps Act Now and
  Approval Required, recording a quality-check note when truncated
  rather than silently hiding the excess.
- **Dashboard read API** (`services/morning_plan_dashboard.py`,
  `GET /api/v1/morning-plan/dashboard`, new): a `DashboardPlanStatus`
  Literal (`COMPLETE`/`INCOMPLETE`/`STALE`/`FAILED`/`MARKET_CLOSED`)
  distinct from the stored `PlanCompletenessStatus` — `STALE` is a
  wall-clock-elapsed-since-generation signal
  (`STALE_PLAN_AGE` = 6 hours) the stored label alone can't express.
  `FINAL`/`CORRECTION` versions always outrank `PRELIMINARY`/`AD_HOC`
  for the same date once both exist.
- **Delivery**: `render_markdown()` (`services/morning_plan_export.py`)
  for the printable export (`GET .../versions/{id}/export.md`); an
  in-app `Alert` + `MorningPlanDeliveryEvent(channel=IN_APP)` is
  recorded whenever a `FINAL` version is generated (never for
  `PRELIMINARY`/`AD_HOC`, so the notification means what it says);
  `GET .../cowork-brief` serves only `FINAL`/`CORRECTION` versions,
  404s honestly if none has been published yet for the date, and has
  no code path into order creation, approval, or execution (a `GET`,
  full stop — docs/MORNING_PLAN_SPEC.md's Cowork section, ADR-049).
- **Tests:** 351 backend tests (up from 315) — `test_market_calendar.py`
  (weekday/weekend/holiday/observed-holiday/early-close/DST-spring/
  DST-fall/next-trading-day/countdown), `test_morning_plan_scheduler.py`
  (before-window/weekend/holiday/preliminary-then-final/duplicate-
  protection/worker-restart-after-crash/worker-restart-after-completion),
  `test_morning_plan_generate.py` (provider-partial-outage/required-
  data-stale/stale-majority-incomplete/no-qualified-trades/empty-
  watchlist/existing-position-requiring-action/routine-hold-not-forced/
  evidence-reproducibility), and three new classes in
  `test_morning_plan_endpoints.py` (preliminary-to-final diff,
  Cowork-only-serves-final, Markdown export). `ruff`/`mypy --strict`
  clean across `src/`.
- **Demonstrated live** (`src/tradingos_api/scripts/demo_prompt9.py`):
  a controllable clock walks a synthetic 2026-08-17 trading day from
  before the preliminary window through a simulated worker crash
  mid-FINAL-run and a successful attempt-2 retry after the stuck-run
  timeout, calling the real `/generate`/`/dashboard`/`/versions/{id}/export.md`/
  `/cowork-brief` endpoints against the live dev database throughout —
  including a genuine Data Problems routing for several real
  `recommendation_versions` rows that had aged past the staleness
  threshold since Revision Prompt 6/7's demo runs committed them.
- **Docs:** docs/DATA_DICTIONARY.md §15, docs/ER_DIAGRAM.md §19,
  docs/API_CONTRACTS.md area 8, docs/MORNING_PLAN_SPEC.md
  (implementation-status note), this entry, docs/TEST_EVIDENCE.md,
  docs/DECISIONS.md (ADR-055), docs/OPERATIONS.md (scheduler runbook).

## Revision Prompt 8 (2026-08-08) — portfolio, lane attribution, trade journal, and reconciliation

**Extended a schema that was already rich but entirely unused** — Phase
8 had already built `Account`/`CashLedgerEntry`/`Position`/`PositionLot`/
`Order`/`Execution`/`Fee`/`Trade`/`TradeThesis`/`TradeReview`/
`RecommendationOutcome`/`BenchmarkSnapshot`, every one of them schema-only
with no service layer deriving anything from the underlying events. This
revision's real work was building that missing derivation layer, not
inventing new tables from scratch — of the "JOURNAL" requirement's own
field list, only `mfe`/`mae`/`exit_reason`/lane attribution needed new
columns; "user response," "post-trade lesson," and "benchmark result"
already had a home (`RecommendationOutcome.classification`, `TradeReview.review_text`,
`BenchmarkSnapshot` respectively) that nothing had ever populated.

- **FIFO accounting engine** (`services/portfolio_accounting.py`, new):
  `apply_buy_execution()`/`apply_sell_execution()` derive holdings, cash,
  lots, and realized P&L purely from `Execution`/`Fee`/`CashLedgerEntry`
  rows using `Decimal` throughout. `apply_sell_execution()`'s `target_lane`
  parameter is lane-aware FIFO — consumption is restricted to one lane's
  open lots (in open-date order), never spilling into a different lane's
  lots just because they're older. `target_lane=None` models a real
  broker fill that reports no lane at all, and the result is disclosed
  as `lane_selection_is_certain=False` — the required "lot-selection
  uncertainty disclosure."
- **Per-lane `Trade` round-trips**: adding `lane` to `Trade` means the
  same instrument now has independent OPEN→CLOSED lifecycles per lane —
  a `TACTICAL` trade can fully close while an `INVESTMENT` trade on the
  identical instrument stays open throughout untouched (see
  docs/ER_DIAGRAM.md §18). This is what makes "partial tactical exit
  while investment lot remains" a correctly-modeled first-class scenario.
- **Corporate actions, corrections, CSV import**
  (`services/corporate_actions_apply.py`, `services/execution_corrections.py`,
  `services/csv_import.py`, all new): split/dividend application is
  idempotent per `(corporate_action_id, account_id)`; a correction is
  always a new, real reversal `Execution` — the original row is never
  touched ("never silently delete or rewrite an executed event");
  CSV import is idempotent at both the file level (identical re-upload
  is a no-op) and the row level (a partial unique index scoped to
  `status = 'IMPORTED'` catches an overlapping fill across two different
  files while still allowing multiple `DUPLICATE_SKIPPED` audit rows for
  the same key).
- **Broker-aggregate reconciliation** (`services/reconciliation.py`,
  new): deliberately distinct from the pre-existing self-consistency
  check at `GET /api/v1/orders/reconciliation/{account_id}` — see
  docs/DECISIONS.md ADR-054 for why both exist and neither replaces the
  other. A `MANUAL` account with no broker feed always reconciles
  `MATCHED`, never a fabricated discrepancy.
- **Holding guidance** (`services/holding_guidance.py`, new): per-lot
  read models composing already-existing data (Revision Prompt 6's
  committee output via `deterministic_inputs_snapshot`, R3's
  `RecommendationLevel`/`InvestmentThesis`, Revision Prompt 4's
  `EarningsEvent`, `Alert`) — no new business logic, purely a view.
- **Trade journal** (`services/trade_journal.py`, new):
  `compute_recommendation_outcome()` finally populates
  `RecommendationOutcome.classification` (`FOLLOWED`/`IGNORED`/`MODIFIED`),
  honoring its own R3-era docstring's "computed... never self-reported"
  promise that nothing had implemented yet. `compute_mfe_mae()` derives
  maximum favorable/adverse excursion from daily `MarketBar` rows.
  `get_journal_entry_view()` composes everything the "JOURNAL" requirement
  asks for into one read model.
- **API**: `GET .../positions/{instrument_id}` (position detail: combined
  + subpositions + per-lot guidance), `POST .../manual-fill`,
  `POST .../import-csv` (multipart), `POST .../reconcile` +
  `GET .../reconciliation-runs`, and `routers/journal.py`'s trade detail
  extended with every new journal field.
- **Tests:** 314 backend tests (up from 296) — `test_portfolio_accounting.py`
  (9: same-symbol-two-lanes, partial-tactical-exit, lot-selection-uncertainty,
  cash/position invariants), `test_corporate_actions_apply.py` (4: split/
  dividend math + idempotency), `test_reconciliation.py` (4: broker
  aggregate reconciliation including the MANUAL-account and
  broker-reports-a-position-we-don't-have cases), `test_csv_import.py`
  (3: import idempotency at both the file and row level). `ruff`/
  `mypy --strict` clean across `src/`.
- **A real design bug found and fixed during test-writing**: the initial
  `ImportRow` schema used a blanket `UniqueConstraint(account_id, dedup_key)`
  — but recording a `DUPLICATE_SKIPPED` audit row for an already-imported
  fill *itself* violates that constraint (a second row with the same
  key). Fixed with a partial unique index scoped to `status = 'IMPORTED'`
  only, requiring a migration edit and a downgrade→edit→upgrade round
  trip to fix in place (see docs/TEST_EVIDENCE.md).
- **Demonstrated live** (`src/tradingos_api/scripts/demo_prompt8.py`):
  AMD held simultaneously as a 50-share `INVESTMENT` lot and a 100-share
  `TACTICAL` lot, combined-vs-subposition view, per-lane holding
  guidance, a 60-share partial tactical exit (realized P&L $420, the
  investment lot provably untouched at 50 shares throughout), a $0.25/share
  dividend correctly credited against the post-exit combined position,
  a broker reconciliation reporting `MATCHED`, and the tactical trade's
  full journal view — all in one run, all committed to the dev database.
- **Docs:** docs/DATA_DICTIONARY.md §14, docs/ER_DIAGRAM.md §18,
  docs/API_CONTRACTS.md area 5, this entry, docs/TEST_EVIDENCE.md,
  docs/DECISIONS.md (ADR-054).

## Revision Prompt 7 (2026-08-07) — decision policy, risk manager, and hybrid earnings recommendation engine

**No prior implementation existed for the pipeline itself** — R3 had
already built the full `OrderProposal`→policy-evaluation→`OrderApproval`
lifecycle (`routers/order_authority.py`) and Revision Prompt 5/6 had
already built the deterministic features and the committees; this
revision's real new work was the decision-policy layer that decides
*what* proposal to create and *whether* one should exist at all — no
schema-first build was needed for the 9-step pipeline structure itself.

- **9-step pipeline** (`services/recommendation_pipeline.py`, new):
  freeze evidence cutoff → pre-flight hard vetoes (an explicit `NO_ACTION`
  with no committee session at all if one fires) → deterministic
  features (already computed by the caller) → lane selection (explicit)
  → run the committee (Revision Prompt 6, deterministic-veto override
  already enforced there) → portfolio/cash/sector/correlation/liquidity
  constraints (Tactical only) → calculate the proposal → publish. Every
  run ends in exactly one of three states: a published action, a
  published `NO_ACTION`, or a pre-flight `NO_ACTION`.
- **10 hard vetoes** (`services/hard_vetoes.py`, new): stale required
  data, unverified event timing, failed liquidity, risk/sector limit,
  missing price/expected move, evidence leakage, kill switch active,
  broker environment ambiguity, investment/tactical attribution
  ambiguity, expired recommendation — each produces a stable
  machine-readable `veto_code` and a plain-English `explanation`
  sentence, never just a boolean.
- **HES-3 position sizing** (`services/position_sizing.py`, new):
  notional = risk budget ÷ selected expected-move %, then six sequential
  caps (max position allocation, max sector exposure, max correlated-
  group exposure, liquidity, speculative-name, available cash) — each
  recorded whether or not it actually bound. Defaults: 0.25% risk budget
  (0.50% hard ceiling, enforced by the settings endpoint itself, not
  just documented), 15% max position, 25% max sector, 5bps slippage —
  all versioned, configurable via the extended `RiskPolicy`.
- **HES-4/HES-6 post-confirmation gate** (`services/post_confirmation_gate.py`,
  new): `TRADE_ADD_CONFIRMED` may only be attempted when the three
  post-earnings confirmation gates (Revision Prompt 5) all pass **and**
  liquidity is adequate **and** the gap was not adverse — the last
  check is absolute and independent of the other four, so "no averaging
  down after an adverse gap" (HES-6) holds even in the hypothetical case
  where every other condition looked fine.
- **HES-5 gap-through-stop** (`services/gap_risk.py`, new): estimates
  what a stop actually fills at when an overnight gap carries price
  through it before the market can trade at the stop price — every
  result carries a literal "NOT a guaranteed execution price" disclosure
  string, present even when the gap doesn't breach the stop.
- **Investment/Tactical action plan fields completed** (`schemas/agent_contract.py`,
  extended): `InvestmentCioOutput` gained `preferred_accumulation_zone`,
  `tranche_plan`, `proposed_max_allocation_pct`, and
  `why_investment_not_trade` — the remaining "INVESTMENT ACTION PLAN"
  fields. No numeric valuation range is requested from the CIO
  (principle 6/7 — that's a calculation, not a judgment call).
- **Order proposal fields completed** (`models/order_authority.py`,
  additive migration): `environment`, `outside_hours`, `attached_legs`,
  `max_slippage_bps`, `valid_from`/`expires_at`, `risk_policy_version`,
  `data_cutoff`/`quote_observed_at`, `requires_approval` — fills out the
  "ORDER PROPOSAL FIELDS" list on top of R3's original columns.
- **Recommendation list/detail extended** (`routers/investment.py`,
  `routers/tactical.py`): both detail views now surface the full plan
  (thesis-break/entry-invalidation conditions, the new CIO fields, and,
  for Tactical, the linked `OrderProposal` if one was created) — reused
  and extended R3's existing endpoints rather than building new ones. A
  pre-existing R3 gap was fixed in the same pass: `RiskPolicyVersion`
  rows are now actually written on every `PATCH /settings/risk-policy`
  (the model's own docstring promised this since R3; the handler never
  did it).
- **Tests:** 296 backend tests (up from 256) — `test_hard_vetoes.py`
  (8, including the required "every veto produces a user-readable
  explanation code" and "event date correction" cases),
  `test_position_sizing.py` (11, including "correlated semiconductor
  positions" and "insufficient cash"), `test_post_confirmation_gate.py`
  (8, HES-6's no-averaging-down guarantee), `test_gap_risk.py` (7, the
  "gap-through-stop" scenario), `test_recommendation_pipeline.py` (6,
  pre-flight `NO_ACTION`, "score 5 fails / score 6 needs every other
  gate," "same symbol receives `INVEST_HOLD` and `TRADE_AVOID` without
  conflict," and the six-month baseline reproducibility substitute — see
  that file's own docstring for why a full historical-replay backtest
  wasn't rebuilt this pass). `ruff`/`mypy --strict` clean across `src/`.
- **Demonstrated live** (`src/tradingos_api/scripts/demo_prompt7.py`,
  fake deterministic LLM — Revision Prompt 6's own demo already proved
  live-Anthropic compatibility for the committee layer): an Investment
  `INVEST_BUY`, a Tactical `TRADE_ENTER` with real sizing math and a real
  persisted `OrderProposal`, a pre-flight veto publishing `NO_ACTION`
  before any committee ran, HES-6 blocking an adverse-gap add-on, a
  favorable-gap `TRADE_ADD_CONFIRMED`, and the gap-through-stop
  disclosure — all in one run, all committed to the dev database.
- **Docs:** docs/DATA_DICTIONARY.md §13, docs/ER_DIAGRAM.md §17,
  docs/API_CONTRACTS.md areas 12/14/15, this entry, docs/TEST_EVIDENCE.md,
  docs/DECISIONS.md (ADR-053).

## Revision Prompt 6 (2026-08-06) — evidence-bound Investment Committee and Tactical Trading Desk

**No prior implementation existed to inspect for this exact shape** —
`docs/MODEL_GOVERNANCE.md`'s "Refinement: the investment committee"
section had planned a single, lane-agnostic 8-role committee (ADR-038)
before the Investment/Tactical mode split (R3) existed; this revision
supersedes that plan with two separate committees instead of building
what was originally sketched (see ADR-052). The underlying
`AgentDefinition`/`AgentVersion`/`CommitteeSession`/`AgentRun`/
`AgentEvidenceLink`/`AgentOpinion` schema and the R3 Recommendation/
Investment-thesis schema needed no new tables — only 17 new `agent_role`
enum values and one nullable `committee_sessions.mode` column.

- **Agent Contract** (`schemas/agent_contract.py`, new): one shared
  15-field pydantic shape (`AgentContractOutput`) every role's output is
  validated against — agent/prompt version, recommendation lane,
  evidence cutoff, evidence ids, factual claims mapped to evidence ids
  (a `model_validator` rejects any claim citing an undeclared id),
  deterministic feature ids, thesis, strongest supporting/contradictory
  evidence, risks, missing information, invalidation conditions,
  categorical stance, evidence completeness, calibration status
  (always `UNCALIBRATED` — DQ-5), and model/token/latency/cost run
  metadata. `InvestmentCioOutput`/`TradingCioOutput` extend it with each
  CIO's lane-specific required fields and their own action enum
  (`policy.recommendation_modes.InvestmentAction`/`TacticalAction`,
  already existing from R0) — two separate schemas, never one shape
  with a lane flag (ADR-052).
- **Provider-neutral LLM adapter, reused and widened** (`providers/llm.py`):
  the existing `LLMProvider` Protocol (ADR-020) gained optional
  `tool_choice`/`timeout_seconds` parameters, backward-compatible with
  every existing caller — both committees share this one adapter, no
  second one was introduced.
- **17-role registry** (`services/committee_roles.py`, new): 8
  Investment Committee roles (Business Quality, Fundamental/Valuation,
  Industry/Competitive, Long-Term Bull, Long-Term Bear, Portfolio
  Strategist, Risk Manager, Investment CIO) and 9 Tactical Trading Desk
  roles (Market Intelligence, Technical, Earnings/Guidance, News/Catalyst,
  Tactical Bull, Tactical Bear, Portfolio/Correlation Manager, Trading
  Risk Manager, Trading CIO) — pure role identity/prompt-focus data, no
  computation.
- **Generic agent runner with guardrails** (`services/agent_runner.py`,
  new): the one execution path every role goes through. Cost ceiling
  (a role whose turn arrives after the run's budget is already spent is
  `DEGRADED`, never called); timeout (passed straight to the provider);
  fallback (`LLMProviderNotConfigured` or any provider exception
  degrades that one role without crashing the committee); forced
  structured output (the role's schema becomes a single named tool with
  `tool_choice` forcing exactly that tool). `services/llm_cost.py`
  (re-created; retired at Phase 8 along with the rest of the shipped
  MVP's business logic) prices every call at Anthropic's standard,
  non-intro `claude-sonnet-5` rate.
- **Committee orchestrator** (`services/committee_orchestrator.py`,
  new): runs every analyst role for a lane, then that lane's CIO,
  persists the full audit trail, and — the one rule this revision exists
  to make impossible to bypass — applies the deterministic-veto override
  **in code**, after the CIO's output has already passed schema
  validation and before any `Recommendation` row is written (ADR-051).
  For a new `INVEST_BUY`/`INVEST_ADD`, also creates the `InvestmentThesis`
  DQ-1 requires (thesis, valuation context, horizon, review date,
  thesis-break conditions — all read from the CIO's own validated
  output, never invented).
- **Side-by-side view** (`services/side_by_side.py`,
  `GET /api/v1/committee/side-by-side/{instrument_id}`, new): the latest
  active Investment and Tactical recommendation for one symbol, plus a
  deterministic (never LLM-generated) explanation of why the two lanes
  may differ.
- **Committee API** (`routers/committee.py`, API area 22, new):
  `POST /api/v1/committee/{lane}/{instrument_id}/run` (synchronous,
  human-triggered — no scheduled run anywhere), `GET /sessions/{id}`
  (the review screen — every role's full contract output, cost,
  latency, reconstructed from the persisted audit trail).
- **Tests:** 256 backend tests (up from 226) — Agent Contract schema
  validation (`test_agent_contract.py`), agent-runner guardrails
  (`test_agent_runner.py` — cost ceiling, timeout pass-through,
  fallback, and regression coverage for the two real bugs found via
  live verification below),
  committee eval fixtures (`test_committee_orchestrator.py` — an
  obviously-bullish 8/8-role run, the adversarial veto-override case,
  one degraded analyst not blocking the rest), and prompt-injection
  defense in depth (`test_committee_prompt_injection.py` — every system
  prompt labels evidence untrusted, and a fake LLM that *fully complies*
  with an injected instruction to ignore the veto is still overridden by
  the code, not the prompt). `ruff`/`mypy --strict` clean across `src/`.
- **Two real bugs found via live verification against the real
  Anthropic API** (`src/tradingos_api/scripts/demo_prompt6.py`): (1) the
  tool schema sent to the model originally included `run_metadata`
  (model/tokens/latency/cost) as a required field — asking the model to
  invent values for its own not-yet-finished response, which made real
  calls measurably more likely to fail; fixed by stripping that field
  from the model-facing schema and injecting the real value
  server-side after the call. (2) With a large, single forced-tool
  schema, Claude occasionally wrapped the entire payload one level
  deeper than requested (e.g. `{"agent_output": {...}}`) instead of
  putting fields at the top level — fixed with a narrow, unambiguous
  unwrap (only when a single top-level key's dict value contains at
  least one of the schema's required fields). Both fixes are covered by
  new regression tests in `test_agent_runner.py`; the full test suite
  and a live re-run confirmed the fix.
- **Docs:** docs/DATA_DICTIONARY.md §12, docs/ER_DIAGRAM.md §16,
  docs/API_CONTRACTS.md area 22, docs/MODEL_GOVERNANCE.md (marks the
  original single-committee plan superseded, documents what actually
  shipped), this entry, docs/TEST_EVIDENCE.md, docs/DECISIONS.md
  (ADR-051, ADR-052).

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
