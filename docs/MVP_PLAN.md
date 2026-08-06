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

## Revision Prompt R1 delta — paper release vs. live-confirmed release

**Status: architecture-only.** Phase 8 (shipped) already implemented this
document's data model in schema/API form, and Revision Prompt R0 adopted
the order-authority/product-mode policy this section builds on. This
section adds the one structural requirement Revision Prompt R1 asks for
explicitly: **the MVP above is a *paper* release plan. Live order
placement is a separate, later, explicitly-gated release — never an
incremental extension the paper release backs into.**

### Paper release (everything in "MVP" above, plus the R1 deltas)

Everything in this document's "MVP" section, plus
docs/PRODUCT_REQUIREMENTS.md's R1-delta FRs (FR-51–FR-61), ships and
operates entirely within `RESEARCH_ONLY`/`PAPER_MANUAL_APPROVAL`/
`PAPER_AUTO_POLICY` — the three modes PROJECT_INSTRUCTIONS.md's `OA-*`
never permit to touch a live account. This includes:

- Dual investment/tactical decision lanes (FR-51–FR-53).
- The Morning Decision Dashboard, its scheduler, and job lineage
  (FR-54, FR-60).
- The hybrid earnings workflow, pre- and post-event (FR-55–FR-56) — note
  that even the earnings strategy's "conservative live threshold"
  language (HES-1) only *gates whether live consideration is possible
  later*; nothing in the paper release ever reaches a live order.
- The full order lifecycle through `PAPER_SUBMITTED`/`FILLED` (FR-57),
  including `PAPER_AUTO_POLICY`'s automated paper submission — gated on
  its own prerequisite: **paper automation is allowed only after the
  deterministic policy tests pass** (already true today for the policy
  semantics themselves — `tests/test_policy_order_authority.py` — and
  required again, against whatever schema-backed implementation Prompt 7
  produces, before `PAPER_AUTO_POLICY` is ever turned on for real).
- The visible, server-enforced operating-mode selector (FR-58) — visible
  even though only paper modes are reachable in this release, so the UI
  pattern is validated before a live mode is ever added to the same
  selector.
- Approval binding, invalidation, and the Orders page UI (docs/UX_MAP.md)
  — built and exercised entirely against paper submissions.

### Live-confirmed release (Prompt 17, separately gated)

A live adapter (`LIVE_CONFIRM_EACH_ORDER` actually wired to a real
broker) is its own release, not a flag flipped on the paper release's
code. It requires, in addition to everything above already working in
paper mode:

- **The Prompt 17 acceptance gate** (docs/ARCHITECTURE.md's architecture
  question 10, full detail) — deterministic policy tests passing, a
  demonstrated paper-trading soak period with zero reconciliation
  discrepancies, the Order Execution Service's single-entry-point
  property re-verified, the kill switch and cancel-open-orders controls
  (OA-9/SS-4) built and tested, and explicit recorded user sign-off
  treating live capital risk as its own decision.
- Every live order still requires a **fresh, per-order confirmation**
  (OA-5) — there is no live-mode equivalent of `PAPER_AUTO_POLICY`, by
  design (PROJECT_INSTRUCTIONS.md's `OA-1`: "fully autonomous live entry
  is outside the approved scope, permanently").
- Its own risk-register and threat-model review pass at implementation
  time (docs/RISK_REGISTER.md/docs/THREAT_MODEL.md already carry
  forward-looking rows for this, added in Revision Prompt R1 — see those
  documents), not a retroactive review after the adapter already exists.

### Why this split matters enough to state explicitly

Every prior phase of this project (Phases 1-7, Phase 8) shipped against
paper/research-only surfaces with no live-order code path anywhere
(principle 10, unchanged). The risk this split guards against is not
"forgetting" to gate live trading — it's the more subtle failure of a
paper-release feature (e.g. `PAPER_AUTO_POLICY`'s automatic submission)
quietly becoming the template a rushed future prompt copies for a live
mode without re-deriving why live's requirements (per-order confirmation,
no auto-policy equivalent, the Prompt 17 gate) are categorically
different, not just "the same thing with a different account." Naming
the two releases separately in this document is the durable record that
prevents that shortcut from looking like a reasonable extension later.
