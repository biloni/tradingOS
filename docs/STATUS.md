# Status

**Current phase:** Phase 7 (shipped) + a planning-only Product &
Architecture Refinement pass layered on top, not yet implemented.
**Last updated:** 2026-08-03

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

- **Stop and wait**, per this pass's own explicit instruction. Nothing is
  scaffolded. Next step is yours: review docs/BLOCKING_DECISIONS.md
  (confirm or override each of the 10), after which an implementation
  phase plan (with real phase numbers) can be proposed.

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
