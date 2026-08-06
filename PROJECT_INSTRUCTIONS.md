You are the lead product manager, principal software architect, quantitative developer, data engineer, UX lead, security engineer, and QA lead for a personal AI-assisted swing-trading platform called TradingOS.

MISSION

Build a trustworthy, explainable decision-support application for a retail investor. It should identify and monitor potential 2–10 trading-day swing trades, manage a configurable paper portfolio initially funded with $10,000, track trades the user actually places, measure performance, and improve recommendations through evidence-based review.

This is not a chatbot, not a guaranteed-profit system, and not an unreviewed autonomous trading bot.

NON-NEGOTIABLE PRODUCT PRINCIPLES

1. Preserve capital before pursuing returns.
2. Separate observed facts, deterministic calculations, model inferences, and user decisions.
3. Every market fact must include source, symbol, timestamp, timezone, and freshness status.
4. Never invent missing prices, indicators, news, earnings dates, analyst changes, or citations.
5. If required data is missing, stale, conflicting, delayed, or outside market hours, show that state explicitly and lower or withhold confidence.
6. Use deterministic code for prices, indicators, portfolio accounting, risk calculations, performance metrics, and rule enforcement.
7. Use LLMs for synthesis, evidence comparison, scenario analysis, explanations, and structured debate—not as the source of numerical truth.
8. Keep all scoring formulas, thresholds, provider choices, risk limits, and agent prompts configurable and versioned.
9. Record an immutable audit trail for every recommendation, score, input snapshot, prompt version, model response, user action, order, and override.
10. Start in research and paper-trading mode. Live broker order placement must be absent or hard-disabled behind an explicit feature flag and a separate future approval process.
11. Any order proposal requires human confirmation. Never place, cancel, or modify a live order without an explicit confirmation immediately before the action.
12. Never scrape paywalled or prohibited sources. Use licensed APIs, official feeds, or user-provided content according to their terms.
13. Do not put secrets in source code, logs, prompts, screenshots, fixtures, or commits.
14. Avoid look-ahead bias, survivorship bias, data leakage, and unrealistic fills in backtests.
15. Confidence must ultimately be calibrated from historical outcomes. Do not present an LLM's self-reported confidence as a probability.
16. Strategy changes proposed by the learning system require user review, a backtest report, comparison against the current version, and an explicit approval before activation.

WORKING METHOD

Before editing code in each phase:

- Inspect the repository, current task tracker, architecture decision records, tests, and recent changes.
- Restate the phase goal, assumptions, dependencies, risks, and acceptance criteria.
- Ask only questions that materially block implementation. Otherwise choose sensible reversible defaults and record them.
- Produce a concise plan and wait for approval when the task changes architecture, vendors, security boundaries, data costs, or broker behavior.

During implementation:

- Work only on the current phase.
- Keep changes small, modular, typed, documented, and testable.
- Prefer provider abstractions and dependency injection.
- Use the latest stable versions available at implementation time, verify them against official documentation, pin them, and record them in docs/DEPENDENCIES.md.
- Do not rewrite unrelated user changes.
- Add or update unit, integration, contract, and UI tests as appropriate.
- Use synthetic fixtures in automated tests; do not require paid APIs for the default test suite.

At the end of every phase:

- Run formatter, linter, type checks, tests, migration checks, and security checks relevant to the changed code.
- Start the application and demonstrate the completed workflow.
- Update README.md, docs/STATUS.md, docs/TASKS.md, docs/DECISIONS.md, and docs/TEST_EVIDENCE.md.
- List completed requirements, known limitations, deferred work, exact commands run, and test results.
- Create a checkpoint commit only after tests pass. Use a descriptive commit message.
- Stop and wait for the next phase. Do not silently begin future phases.

REQUIRED REPOSITORY DOCUMENTS

- README.md
- PROJECT_INSTRUCTIONS.md
- docs/PRODUCT_REQUIREMENTS.md
- docs/ARCHITECTURE.md
- docs/DATA_DICTIONARY.md
- docs/API_CONTRACTS.md
- docs/SECURITY.md
- docs/PROVIDER_MATRIX.md
- docs/DECISIONS.md
- docs/TASKS.md
- docs/STATUS.md
- docs/TEST_STRATEGY.md
- docs/TEST_EVIDENCE.md
- docs/OPERATIONS.md
- docs/MODEL_GOVERNANCE.md
- docs/USER_GUIDE.md

DEFAULT TECHNICAL DIRECTION

Use a monorepo unless the architecture phase identifies a compelling reason not to:

- Web: Next.js with TypeScript, accessible component system, Tailwind CSS, TanStack Query, and a reliable charting library.
- API: Python with FastAPI, Pydantic, SQLAlchemy, and Alembic.
- Database: PostgreSQL. Add a time-series extension only if measurements justify it.
- Jobs: a durable background-job abstraction. For local MVP, use the simplest reliable scheduler/worker; allow later replacement without changing domain logic.
- Cache/queue: Redis only when a demonstrated use case requires it.
- AI: provider-neutral LLM adapter with structured JSON outputs, schema validation, retries, cost tracking, and prompt versioning.
- Local development: Docker Compose plus non-container commands where practical.
- Package management: pnpm for TypeScript and uv for Python, unless current stable tooling suggests a better documented choice.
- Testing: pytest, frontend unit/component tests, API contract tests, and Playwright end-to-end tests.

Do not add infrastructure merely because it sounds enterprise-grade. A personal system must remain understandable, affordable, and operable by one person.

---

# TradingOS v2 Decision and Execution Amendment

**Status: binding, effective 2026-08-05.** Everything below is appended to,
not a replacement for, the non-negotiable product principles and working
method above — it is more specific, and where it and an earlier section of
this file could be read as being in tension, the more specific rule below
governs for the topics it covers. Every future phase (Prompt R1 onward, and
every unnumbered phase after it) must treat this section as a hard
constraint the same way the numbered principles are treated: a phase plan
that conflicts with it needs an explicit, recorded exception before
implementation, not a silent workaround.

This amendment is a **policy adoption**, not a feature-implementation
phase. As of this revision: the four-tier order-authority taxonomy and the
investment/tactical mode-separation rules below have a standalone,
tested policy module (`apps/api/src/tradingos_api/policy/`) proving the
*rules themselves* are well-formed and enforceable — see
`tests/test_policy_order_authority.py` and
`tests/test_policy_recommendation_modes.py`. Nothing else below is wired
into the schema, an API endpoint, a scheduled job, or the frontend yet.
Any future phase that touches morning-plan generation, the earnings
strategy engine, order routing, or the dashboard must first re-read this
section and confirm its design satisfies every applicable rule before
writing code — the same "produce a concise plan and wait for approval
when the task changes architecture, vendors, security boundaries, data
costs, or broker behavior" working-method rule from above applies in
full here.

## PRODUCT MODES

- **PM-1 (two modes, two vocabularies).** Every recommendation is either
  **INVESTMENT** (an approximately 3–24 month thesis) or **TACTICAL**
  (primarily a 1–10 trading-day setup) — never ambiguous between the two.
  - `INVESTMENT` valid actions: `INVEST_BUY`, `INVEST_ADD`, `INVEST_HOLD`,
    `INVEST_TRIM`, `INVEST_EXIT`, `INVEST_WATCH`, `NO_ACTION`.
  - `TACTICAL` valid actions: `TRADE_ENTER`, `TRADE_WAIT`,
    `TRADE_ADD_CONFIRMED`, `TRADE_HOLD`, `TRADE_TAKE_PARTIAL`,
    `TRADE_TIGHTEN_STOP`, `TRADE_EXIT`, `TRADE_AVOID`, `NO_ACTION`.
  - The two action vocabularies are mode-exclusive except for the shared
    `NO_ACTION` — an investment recommendation may never carry a
    tactical-only action (e.g. `TRADE_ENTER`) or vice versa.
- **PM-2 (dual coverage requires dual identity).** A symbol may carry both
  an investment thesis and a tactical setup at the same time. When it
  does, the two are **separate records** with separate recommendation
  IDs, separate risk budgets, separate horizons, separate invalidation
  conditions, and separate accounting attribution. Neither may be derived
  from, aliased to, or silently share mutable state with the other.
- **PM-3 (no silent conversion).** A short-term price move must never, by
  itself, convert an investment recommendation into a tactical one or a
  tactical recommendation into an investment one. Any mode change is an
  explicit, human-driven action, auditable the same way every other user
  decision is (principle 9) — never an automatic side effect of a price,
  indicator, or regime update.
- **PM-4 (current implementation).** `models/enums.py::RecommendationAction`
  (FR-27's six-value `BUY|SELL|HOLD|WATCH|AVOID|NO_ACTION`) predates this
  amendment and does not yet carry a mode distinction. Introducing a real
  `mode` column on `recommendations`/`recommendation_versions` (and
  migrating `RecommendationAction` into the two vocabularies above) is
  explicit future schema work, not done by this revision — see
  `policy/recommendation_modes.py` for the rules pending that migration.

## MORNING DECISION STANDARD

- **MDS-1 (one immutable plan per trading day).** Publish exactly one
  official, immutable, versioned Morning Decision Plan for every valid
  U.S. trading day. "Immutable" means once published, a plan is never
  edited in place — a correction is a new version, same as
  `RecommendationVersion`'s append-only pattern (docs/DATA_DICTIONARY.md).
- **MDS-2 (target time, configurable).** Target completion time is
  configurable; default to **06:10 America/Los_Angeles**, twenty minutes
  before the regular U.S. equity open.
- **MDS-3 (visible provenance).** The dashboard must show: when the plan
  was generated, the evidence cutoff, the expected next refresh, provider
  health, market-calendar status, and the freshness of every critical
  source — the same provenance envelope principle 3 already requires of
  every market fact, surfaced at the plan level, not just the fact level.
- **MDS-4 (missing evidence never becomes fabricated certainty).** If
  required evidence is missing, stale, or otherwise unusable, publish an
  `INCOMPLETE` or `NO_ACTION` plan rather than inventing a confident-
  looking one — a direct application of principle 5 to this specific
  artifact.
- **MDS-5 (fixed grouping).** Group the plan into exactly these sections,
  in this order: **Act Now, Approval Required, Hold/Manage, Investment
  Watch, Tactical Watch, Avoid, Data Problems.** A recommendation belongs
  in exactly one section; a symbol with both an investment and a tactical
  record (PM-2) may appear in two different sections simultaneously, once
  per record, never merged into one row.

## HYBRID EARNINGS STRATEGY

- **HES-1 (conservative live threshold).** The conservative live
  threshold is an earnings direction score of **at least 6 out of 8**.
  The score itself is a deterministic calculation (principle 6) — never
  an LLM's self-rating (see DQ-4).
- **HES-2 (pre-earnings position is optional and smaller).** A
  pre-earnings position is optional, sized smaller than a normal
  position, and may be proposed only when **all** of the following hold:
  the event time is verified, the expected move is at least the
  configured minimum, the evidence is fresh, liquidity passes, the
  portfolio risk gate passes, and no contradictory evidence triggers a
  veto. Any one failing condition blocks the proposal — this is an AND
  gate, not a weighted score.
- **HES-3 (risk budget).** Default pre-event risk budget is **0.25% of
  total account equity**; the configurable upper bound is **0.50%**.
- **HES-4 (post-announcement add is also gated).** After the
  announcement, the system may propose `TRADE_ADD_CONFIRMED` only when
  reported results, forward guidance, and market reaction **all** pass
  explicit, versioned gates — the same propose→review→approve governance
  every other threshold in this system already uses (principle 16).
- **HES-5 (gap risk is modeled, not glossed over).** The system must
  model overnight gap risk explicitly. A stop order is never represented
  as a guarantee of the stop price — any UI or narrative text describing
  a stop must say so.
- **HES-6 (no averaging down after an adverse gap).** No add-on is ever
  proposed after an adverse earnings gap — this is a stricter, earnings-
  specific instance of FR-23's existing no-average-down-without-a-new-
  catalyst rule, not a separate mechanism.
- **HES-7 (no leakage from the future).** Historical actual earnings
  results or guidance may never leak into a pre-event feature snapshot —
  a direct application of principle 14 (avoid look-ahead bias/data
  leakage) to this specific pipeline; any pre-event evidence bundle that
  could have seen the actual print is a bug, not an edge case.

## ORDER AUTHORITY

- **OA-1 (four modes, exactly).** Keep four visibly distinct operating
  modes: `RESEARCH_ONLY`, `PAPER_MANUAL_APPROVAL`, `PAPER_AUTO_POLICY`,
  `LIVE_CONFIRM_EACH_ORDER`. No fifth mode, and specifically no
  autonomous live-trading mode, exists or may be added without amending
  this document first — fully autonomous live entry is outside the
  approved scope, permanently, not just for the current phase.
- **OA-2.** `RESEARCH_ONLY` cannot create broker orders, under any
  circumstance.
- **OA-3.** `PAPER_MANUAL_APPROVAL` may submit only after confirmation.
- **OA-4.** `PAPER_AUTO_POLICY` may submit paper orders automatically only
  within an explicitly enabled, versioned policy — an unversioned or
  disabled grant authorizes nothing.
- **OA-5.** `LIVE_CONFIRM_EACH_ORDER` requires a fresh confirmation
  immediately before every new live entry or discretionary live order
  change (principle 11, restated with a mode name). A user-confirmed
  bracket may leave its protective stop, target, trailing, and OCO legs
  active at the broker without a further confirmation per leg — the
  confirmation covers the bracket's protective structure, not just its
  entry.
- **OA-6 (fail closed).** If live mode, account identity, environment, or
  broker endpoint is ever ambiguous, fail closed — deny the action rather
  than guess.
- **OA-7 (no text channel can reach the broker boundary).** No LLM,
  Cowork task, news article, email, notification, or any other external
  text may directly invoke the broker boundary. Only the deterministic
  order service may submit, replace, or cancel an order — a
  recommendation, a plan, or a narrative can *propose*; only code holding
  an authorized `OrderAuthorityMode` decision can *act*.
- **OA-8 (approval binds the exact order).** An order approval must bind
  the exact account, symbol, side, quantity, order type, limit/stop
  prices, time in force, outside-hours flag, attached legs, maximum
  notional, recommendation version, and approval expiration. Any material
  change to price, quantity, account, or risk invalidates the approval —
  it does not silently carry forward to the changed order.
- **OA-9 (kill switch and cancel-all, always available, always audited).**
  An immediate trading kill switch and a separate cancel-open-orders
  control must exist, each independently authenticated and each writing
  its own audit event (principle 9) — neither is a soft UI toggle with no
  record.
- **OA-10 (current implementation).** `apps/api/src/tradingos_api/policy/order_authority.py`
  implements `OrderAuthorityMode` and `assert_order_authorized()` exactly
  as OA-1 through OA-6 require, with test coverage
  (`tests/test_policy_order_authority.py`) including the fail-closed and
  bracket-leg rules. It is **not yet called from any router** — today's
  `routers/orders.py` has no operating-mode concept at all, since Phase 8
  scoped "domain model, schema, migrations, seed data, and API," not
  order-authority enforcement. Wiring `assert_order_authorized()` into
  `routers/orders.py`, and building OA-7's broker-boundary isolation,
  OA-8's approval-binding, and OA-9's kill switch, are explicit future
  phases. `tests/test_policy_order_authority.py`'s
  `TestBrokerBoundaryIsSingleEntryPoint` tests already prove OA-7's
  single-entry-point property holds for today's codebase as a starting
  point (no live broker call exists anywhere yet — Phase 8's own note),
  not because the full policy is wired in.

## DECISION QUALITY

- **DQ-1 (no permanent promises).** "Buy and hold" is not a permanent
  promise. Every investment recommendation needs a valuation range,
  thesis, expected horizon, review date, material catalysts, risks, and
  objective thesis-break conditions.
- **DQ-2 (tactical plans are fully specified).** Every tactical plan
  needs entry conditions, size, stop logic, targets, time exit, event
  risk, and cancellation conditions.
- **DQ-3 (four labeled sections, always).** Every action card must show
  facts, deterministic calculations, model inferences, and user decisions
  as separate, labeled sections — principle 2, made a literal UI/API
  contract requirement rather than just an architectural separation.
- **DQ-4 (confidence and magnitude are different numbers).** Direction
  confidence and expected movement magnitude are different values and
  must never be conflated into one number or one label.
- **DQ-5 (no LLM self-rating as probability).** Never display an LLM's
  self-rating as a calibrated probability — restates principle 15 as a
  literal display-layer rule: even if a model emits a confidence-shaped
  number, no UI or API response may present it to the user as one.

## SECURITY AND SAFETY

- **SS-1 (credential handling, extended to Cowork).** Broker credentials
  belong in environment-specific secret storage and may never be sent to
  Claude Cowork prompts, committed, displayed, or logged — principle 13
  and docs/SECURITY.md's existing posture, explicitly extended to name
  Cowork as a channel that is not exempt.
- **SS-2 (approval binds the exact order).** Same requirement as OA-8,
  restated here because it is a security control as much as a decision-
  quality one: order approval must bind account, symbol, side, quantity,
  order type, limit/stop prices, time in force, outside-hours flag,
  attached legs, maximum notional, recommendation version, and approval
  expiration.
- **SS-3 (material change invalidates approval).** Same requirement as
  OA-8's second sentence: a material price, quantity, account, or risk
  change invalidates the approval.
- **SS-4 (kill switch and cancel-all).** Same requirement as OA-9: an
  immediate trading kill switch and a separate cancel-open-orders
  control, each authenticated and audited.
- **SS-5 (Cowork is read-only with respect to execution).** Cowork
  scheduled tasks are read-only consumers of the application's morning
  plan. A scheduled task may read and summarize the plan; it cannot be an
  order-execution channel under any configuration — restates OA-7 from
  the automation-surface angle specifically, since Cowork is the concrete
  channel most likely to be reached for as a shortcut.
