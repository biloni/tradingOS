# Hybrid Earnings Strategy

**Status: architecture-only (Revision Prompt R1).** Target design for
PROJECT_INSTRUCTIONS.md's `HES-*` requirements (adopted in Revision
Prompt R0). No earnings-scoring code, pre-event gate, or post-event
confirmation workflow exists yet.

## Why "hybrid"

Two distinct workflows around the same event, kept structurally separate
because they have different risk profiles and different evidence
available at decision time:

1. **Pre-earnings** — a smaller, optional position taken before the
   announcement, sized to survive being wrong about the outcome.
2. **Post-earnings** — a possible add-on after the announcement, gated on
   the actual reported results, not a repeat of the pre-event guess.

Neither implies the other. A name can clear the pre-event gate and still
fail the post-event confirmation gates; a name that never got a pre-event
position can still be evaluated post-event as a fresh
`TRADE_ENTER`/`INVEST_ADD` candidate on its own merits.

## Pre-earnings gate (HES-2) — an AND gate, not a score

A pre-earnings position may be **proposed** (never auto-placed above
`PAPER_AUTO_POLICY`'s own bounds, per docs/ORDER_AUTHORITY_MODEL.md) only
when **all** of the following hold. Any single failing condition vetoes
the proposal outright — this is deliberately not a weighted score where a
strong showing on four conditions compensates for failing a fifth:

1. **Event time is verified.** The earnings date/time comes from a source
   consistent with (or corrected against) `earnings_events`
   (docs/DATA_DICTIONARY.md, Phase 8) and is not itself flagged stale or
   ambiguous (e.g. "before market open" vs. "after market close" must be
   resolved, not assumed).
2. **Expected move is at least the configured minimum.** A move smaller
   than the threshold isn't worth the defined risk budget below — sized
   options-market-implied or historical-realized-move-based, whichever
   the eventual implementation chooses (open question, not resolved by
   this pass).
3. **Data is fresh.** Every input the earnings-direction score (below)
   consumes passes the same freshness check every other evidence category
   already uses (principle 3/FR-14).
4. **Liquidity passes.** The existing liquidity cap (FR-22 — never size
   beyond a configurable fraction of average daily volume) applies
   unchanged; earnings volatility does not loosen this check.
5. **The portfolio risk gate passes.** The position, at its (smaller)
   pre-earnings size, still clears the same portfolio-level checks
   (allocation ceiling, sector concentration, correlation,
   speculative-name cap) every other proposed position does — no earnings-
   specific exemption.
6. **No contradictory evidence triggers a veto.** A specific, named
   contradiction (e.g. a very recent negative guidance revision, an
   unresolved data-quality flag on the name) blocks the proposal even if
   conditions 1-5 all pass — the veto is a hard stop, not a factor fed
   into a score.

## Earnings direction score and the conservative live threshold (HES-1)

The earnings direction score is an **8-factor deterministic calculation**
(exact factor list is implementation detail for the prompt that builds
it — e.g. historical post-earnings drift direction, analyst revision
trend, options skew if available, sector/peer earnings reactions this
season, technical trend going into the print, etc.) — never an LLM's
self-reported confidence (docs/MODEL_GOVERNANCE.md's v2 note, DQ-4/DQ-5).
**6 out of 8** is the conservative threshold required before a **live**
order (`LIVE_CONFIRM_EACH_ORDER` mode) may even be proposed for
consideration; a score below 6/8 caps the workflow at paper modes
regardless of how the other pre-event gate conditions resolve. This
threshold is a versioned config value (principle 8), reviewed through the
existing propose→backtest→compare→approve governance loop before any
change takes effect (FR-45/FR-46 — a prompt or scoring-weight change is a
strategy change like any other).

## Risk budget (HES-3)

- **Default pre-event risk budget: 0.25% of total account equity** —
  materially smaller than the standard 1% per-trade risk budget
  (BLOCKING_DECISIONS.md #6), reflecting that an earnings print is a
  binary, gap-risk event rather than a normal technical setup.
- **Configurable upper bound: 0.50%**, reachable only after **explicit
  policy approval** (HES-4's governance pattern, not a UI slider a user
  can silently drag up) — see the conflicts section in this revision's
  covering response for how this interacts with the existing
  `RiskPolicy` schema's configurable-field design.
- **Maximum concurrent earnings trades: 3** (new recommended default,
  this revision) — a portfolio-level cap independent of the per-trade
  risk budget, preventing "0.25% each, but 15 of them this week" from
  quietly reproducing a much larger aggregate binary-event exposure than
  the per-trade number suggests. Enforced at proposal time the same way
  the sector-concentration cap already is (FR-22) — a 4th concurrent
  earnings-trade proposal is blocked, not silently allowed and merely
  flagged.

## Post-announcement confirmation (HES-4, "post-earnings confirmation workflow")

After the announcement, `TRADE_ADD_CONFIRMED` may be proposed only when
**all** of the following pass, each its own explicit, versioned gate (not
a single combined "results were good" judgment call):

1. **Reported results gate** — actual vs. estimate on the metrics the
   strategy version's config designates as material (e.g. EPS, revenue),
   evaluated deterministically against `earnings_events.eps_actual` vs.
   `eps_estimate` (Phase 8 schema, unchanged) — never the CIO's or any
   role's paraphrase of "beat" or "miss."
2. **Forward guidance gate** — whether guidance (if issued) moved
   favorably, unfavorably, or wasn't provided; a no-guidance quarter does
   not default to "pass," it is its own explicit, named outcome.
3. **Market reaction gate** — the actual post-announcement price action
   (e.g. gap direction/magnitude vs. the pre-event range) confirms rather
   than contradicts the thesis — a name that "beat" but sold off hard does
   not pass this gate just because the headline number looked good.

All three must pass for `TRADE_ADD_CONFIRMED` to be proposed at all; any
one failing routes the outcome to a plain `TRADE_HOLD`/`TRADE_EXIT`
evaluation through the normal active-trade-monitor path instead
(docs/PRODUCT_REQUIREMENTS.md FR-35), not a silent retry of the add
proposal.

## Gap risk modeling (HES-5)

- The system must model overnight gap risk explicitly wherever a stop is
  shown or referenced for a name with earnings inside the holding window —
  a numeric gap-risk estimate (e.g. distribution of this name's own
  historical post-earnings overnight moves) accompanies the stop, not just
  the stop price alone.
- **A stop order is never represented as a guarantee of the stop price.**
  Any UI copy, narrative text, or API field describing a stop for an
  earnings-adjacent position must say so explicitly — this is a literal
  text-content requirement, not just an internal risk-modeling note, since
  the persona (a retail investor) is the one who needs to not be misled by
  "stop-loss" sounding like a hard floor.

## No averaging down after an adverse gap (HES-6)

A stricter, earnings-specific instance of FR-23's existing rule: **no
add-on is ever proposed** after an adverse earnings gap, full stop — not
even with a new catalyst, not even if FR-23's general precondition (new
evidenced catalyst + intact thesis + full committee review) would
otherwise be satisfied. FR-23's mechanism (a hard precondition check, not
a prompt suggestion) is reused; HES-6 is a stricter special case of it,
not a separate implementation.

## No leakage from the future (HES-7)

Any pre-event feature snapshot construction must provably exclude the
actual reported results/guidance for that same event — implemented as a
temporal guard on the snapshot-assembly query (only evidence with a
timestamp strictly before the verified announcement time is eligible),
mirroring the existing backtest no-look-ahead-bias discipline
(principle 14, `tests/test_backtest_simulation.py`'s `TestNoLookAhead`
pattern from the shipped MVP) applied to a live pipeline instead of a
historical replay. The acceptance test for this item (below) is
structured the same way: construct a pre-event snapshot for a real past
earnings date, assert the actual reported EPS/guidance for that date
never appears anywhere in the snapshot's inputs.

## Traceability

| Item | Future prompt | Acceptance test (planned id) |
|---|---|---|
| 8-factor earnings direction score (deterministic, versioned) | Prompt 8 | AC-18 |
| Pre-event AND gate (HES-2) | Prompt 8 | AC-19 |
| Risk budget (0.25%/0.50%) + max-3-concurrent cap | Prompt 8 | AC-20 |
| Gap-risk modeling + "not a guarantee" copy requirement | Prompt 8 | AC-21 |
| No-average-down-after-adverse-gap (HES-6) | Prompt 8 | AC-22 |
| No-leakage guard on pre-event snapshots (HES-7) | Prompt 8 | AC-23 |
| Post-earnings 3-gate confirmation workflow (HES-4) | Prompt 9 | AC-24 |
