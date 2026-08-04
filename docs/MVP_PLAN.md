# MVP Plan — Refined Scope

This separates the refined product (per the 2026-08-03 refinement brief) into
what ships in the next implementation phases ("MVP" below — the smallest
slice that makes the committee/regime/journal/monitor loop real and
trustworthy end-to-end), what's explicitly Phase 2, and what's Future/out of
scope for now. See docs/BLOCKING_DECISIONS.md for the vendor/config defaults
this plan assumes, and docs/PRODUCT_REQUIREMENTS.md for the full functional
requirements each capability maps to.

**Foundation already shipped (Phases 1–7, `master`, not re-scoped):** Alpaca
market data + paper broker adapter, `Symbol`/`PriceBar`/`Indicator`, the
4-signal deterministic score, `StrategyVersion`'s propose→backtest→compare→
approve governance loop, single-window backtesting, the `/ask` NL-query
tool-use endpoint, the audit-event pattern, the full Next.js UI. Nothing
below replaces this — it's the substrate the refined scope extends
(BLOCKING_DECISIONS.md #10).

## MVP (next implementation phases)

The bar for MVP: the user can wake up, get a real premarket plan grounded in
real evidence and a real committee debate for their highest-conviction
names, act on it (manually, at any broker), have that action tracked, and
see at the end of the day/week whether the system's calls were actually
good — with capital-preservation guardrails enforced in code, not prose.

1. **Symbol validation workflow** (new capability, blocking for everything
   else) — resolve every Tier 1 ticker against Alpaca's asset reference data;
   quarantine unresolved/ambiguous/inactive symbols with a visible reason;
   never silently assume a raw ticker string is tradable.
2. **Watchlist management** — Tier 1 (the 48-symbol list) as a first real
   entity, not a hardcoded seed list; per-symbol/tier monitoring frequency;
   validation status surfaced in the UI.
3. **Evidence gathering, MVP-scoped:** technicals (existing), news headlines
   (Alpaca, existing feed), fundamentals + earnings calendar (one free-tier
   vendor, BLOCKING_DECISIONS.md #1), VIX-proxy macro regime
   (BLOCKING_DECISIONS.md #2). Sentiment scoring is Phase 2 (needs a vendor
   decision this plan doesn't make unilaterally).
4. **Market regime / VIX gating** — configurable regime classification
   (level, percentile, rate-of-change, price/breadth confirmation) that
   adjusts cash and risk limits; explicitly never an independent buy trigger.
5. **Investment committee, cost-bounded** — all 8 roles (Bull, Bear,
   Technical, Fundamental, Macro, Risk Manager, Portfolio Manager, CIO/Judge)
   implemented, but only run in full for the deterministically pre-filtered
   subset of Tier 1 each day (BLOCKING_DECISIONS.md #3) — not all 48 names,
   not on every page load.
6. **Deterministic gates before the CIO narrative** — regime-adjusted risk
   budget, ATR+structure-aware stop/target, risk-budget-derived position
   size capped by allocation/liquidity/sector/correlation/speculative-name
   limits, earnings-window warning, no-average-down rule — all computed in
   code and available to the CIO as tool results, never left to the model to
   compute or override (principle 6/7).
7. **Six-state recommendation output** — BUY/SELL/HOLD/WATCH/AVOID/
   NO_ACTION, replacing the current score-only `Recommendation` shape.
8. **Premarket daily plan and EOD review** — scheduled jobs (in-process,
   BLOCKING_DECISIONS.md #4), each producing an auditable, timestamped
   artifact the user reads, not a live re-query.
9. **Manual trade journal** — broker-agnostic entry logging
   (BLOCKING_DECISIONS.md #5), linked to the recommendation that prompted it
   where applicable.
10. **Active trade monitor** — deterministic hold/tighten-stop/take-partial/
    exit/watch-closely suggestions for every open journal position, computed
    against the same stop/target engine as #6.
11. **Performance dashboard** — realized/unrealized P&L, win rate, average
    R-multiple, drawdown, benchmark comparison — across the journal (the
    primary tracked portfolio, BLOCKING_DECISIONS.md #5).
12. **Recommendation-vs-reality tracking** — for every recommendation:
    followed/ignored/modified, and (once the trade closes) the actual
    outcome — the prerequisite dataset for principle 15's calibration
    requirement, even though calibration itself is Phase 2 (needs a real
    sample size first).
13. **Learning/weight governance, extended** — the existing
    propose→backtest→compare→approve loop (ADR-026/027/028), unchanged in
    mechanism, extended to a larger config surface (regime thresholds, stop/
    target parameters, position-sizing risk budget, committee pre-filter
    bar) — no new governance mechanism, same gate.
14. **Intraday alerts, in-app only** (BLOCKING_DECISIONS.md #9).
15. **Evidence provenance/freshness/audit**, extended to every new evidence
    type (news, fundamentals, earnings, macro) using the same source/
    timestamp/timezone/freshness envelope `PriceBar` already established.

## Phase 2 (explicitly deferred, not MVP)

- **Sentiment scoring** as its own evidence type (needs a vendor decision —
  BLOCKING_DECISIONS.md #1 — deferred pending your approval of a specific
  paid or higher-tier free vendor).
- **Historical-outcome confidence calibration** — needs a real sample of
  closed, outcome-tracked trades from #12 above before any number can
  honestly be framed as a calibrated probability (principle 15). This isn't
  a build-it-later technical gap — it structurally cannot exist before the
  data does.
- **Walk-forward backtesting** — rolling/anchored re-optimization windows
  extending the existing single-window backtest engine. Real methodology
  work (train/validate window sizing, re-optimization cadence) that
  deserves its own design pass once the committee/regime/sizing logic it
  would be validating actually exists to backtest.
- **Push/email/SMS alerts** (BLOCKING_DECISIONS.md #9), if in-app alerts
  prove insufficient in practice.
- **A second market-data or evidence vendor for redundancy.**
- **Options overlays for defined-risk exits** (e.g. protective puts) — the
  refinement brief doesn't ask for this, but it's a natural adjacent
  request for an "aggressive but capital-preserving" profile; flagging it
  as a real Phase-2 candidate rather than silently ignoring the gap.

## Future / explicitly out of scope

- **Live broker order placement** — absent, not feature-flagged, per
  principle 10 and ADR (existing). Nothing in this refinement changes that.
- **Opportunity discovery beyond Tier 1** — the refinement brief explicitly
  requires this stay separated from the core watchlist; no design work
  toward it happens until Tier 1's full loop (validate → evidence →
  committee → journal → monitor → review) is proven.
- **Options, futures, crypto, non-US markets** — unchanged from the existing
  MVP's exclusions.
- **Multi-user / authentication** — unchanged (ADR-007); still a personal,
  single-user tool.
- **A second, independently-connected live paper broker** — the adapter
  pattern already supports this in principle (`PaperBrokerProvider`), but no
  second broker is being added until there's a real reason to (e.g. wanting
  to compare fill quality, or the manual journal proving too much friction).

## Sequencing note

This document intentionally does not assign phase *numbers* (Phase 8, 9,
...) to the MVP items above — that's an implementation-planning decision to
make once you've reviewed and confirmed/overridden docs/BLOCKING_DECISIONS.md,
not something to lock in during this architecture-only pass. docs/STATUS.md
records this refinement as a planning pass with no phase number consumed.
