# UX Map

Pages, navigation, key actions, and state handling for the refined product.
Existing shipped pages (Dashboard, Symbols, Portfolio, Ask, Backtests,
Strategy Versions) are listed first as unchanged/lightly-extended; new
pages follow. Nothing here is built yet — this is the target map
docs/PRODUCT_REQUIREMENTS.md's `FR-*` ids are exposed through.

## Navigation

Left sidebar, extended from the shipped 6-item version to reflect the
watchlist/committee/journal/monitor loop as the new primary path, with the
existing pages kept as secondary/supporting:

```
Premarket Plan   (new — likely the new default landing page)
Watchlist        (new)
Committee        (new — per-symbol recommendation detail lives under here)
Journal          (new)
Monitor          (new — active trade monitor + alerts)
Performance      (new — supersedes parts of the old Dashboard)
─────────────────
Symbols          (existing, unchanged)
Portfolio        (existing — re-labeled "Paper Sandbox", ADR-039)
Ask              (existing, unchanged)
Backtests        (existing, extended — new gates reflected in results)
Strategy         (existing, unchanged mechanism, bigger config)
```

## Existing pages (unchanged or lightly extended)

- **Symbols** (`/symbols`, `/symbols/[ticker]`) — unchanged. A future
  enhancement (not this pass) could show a symbol's watchlist tier/
  validation status inline; not required for MVP.
- **Portfolio → "Paper Sandbox"** (`/portfolio`) — same page, re-labeled
  in the UI to make ADR-039's practice-sandbox framing visible, so it's
  never mistaken for the user's real, journal-tracked portfolio.
- **Ask** (`/ask`) — unchanged mechanism; could optionally gain awareness
  of watchlist/committee data as new tools later, not required for MVP.
- **Backtests** (`/backtests`) — unchanged UI; results reflect the new
  gates once `services/backtest.py`'s exit-rule/sizing modules are swapped
  (ADR-035/036), a backend change with no new page needed.
- **Strategy Versions** (`/strategy-versions`) — unchanged mechanism; the
  propose form's config fields grow to cover the new thresholds (FR-45),
  same page, more fields.

## New pages

### Premarket Plan (`/premarket`, `/premarket/[date]`)

The default landing page once this ships (replacing the current Dashboard
as the first thing the user sees, matching "busy, wants a concise premarket
plan").

- **Key content:** regime summary (FR-01–FR-03) at the top, always visible
  regardless of any name-level detail below it. Per-Tier-1-name one-line
  status (validated names only — quarantined names get their own small
  callout, not mixed into the main list). Full committee detail for the
  pre-filtered subset (FR-20), each collapsed to a summary card
  (recommendation + confidence + one-line CIO rationale) that expands to
  the full committee detail page.
- **Key actions:** expand a card → committee detail; jump to journal entry
  form pre-filled with a recommendation's symbol/side.
- **Empty state:** before the first scheduled run of the day, show
  yesterday's plan with a clear "last updated" timestamp and a manual
  "run now" action — never a blank page (NFR-04's auditability applies to
  the UI too: there's always *something* concrete to show).
  freshness status shown per name if regime/evidence is stale beyond a
  configurable threshold.
- **Error state:** if the scheduled job itself failed, show that
  explicitly ("premarket plan generation failed at 6:02am — retry"), never
  silently show stale data without saying so.
- **Historical view:** `/premarket/[date]` retrieves the stored artifact
  for any past date (FR-31) — read-only, no re-computation.
- **Mobile:** cards stack single-column; regime summary stays pinned at
  top on scroll (it's the one piece of context every other card depends
  on for interpretation).

### Watchlist (`/watchlist`)

- **Key content:** Tier 1 list with validation status badge per symbol
  (`RESOLVED`/`AMBIGUOUS`/`QUARANTINED`, ADR-032), monitoring frequency,
  last-validated timestamp.
- **Key actions:** add a symbol (routes through validation before it can
  be saved as a member, FR-05); re-validate a symbol on demand; change
  monitoring frequency; view a quarantined symbol's specific reason
  (preserving the raw entered ticker, FR-07).
- **Empty state:** n/a for MVP (Tier 1 is pre-seeded), but the add-symbol
  flow's own empty/loading state (validating…) matters — show a spinner
  during the live Alpaca lookup, not a frozen form.
- **Error state:** a validation-provider call failure shows as "couldn't
  validate right now" with a retry action, distinct from `QUARANTINED`
  (which is a real, checked "no" — not a failure to check at all).
- **Mobile:** table collapses to a card-per-symbol list.

### Committee / Recommendation detail (`/committee/[symbol]/[recommendationId]`)

- **Key content:** the full 8-role output (ADR-038's structured schemas
  rendered as sections — Bull/Bear side by side, then Technical/
  Fundamental/Macro, then Risk/PM with the actual gate numbers, then the
  CIO narrative + final action), every cited evidence item shown with its
  provenance envelope (source, timestamp, freshness — FR-14), gate
  pass/fail detail (FR-26) including any gates that blocked the trade even
  if the CIO's narrative sounds favorable.
- **Key actions:** log a journal entry from this recommendation
  (pre-fills symbol/side); view the exact evidence bundle this run used.
- **Empty/error state:** a role that failed structured-output validation
  (docs/MODEL_GOVERNANCE.md) shows as an explicit "this role's output
  couldn't be parsed" card, not a missing section that looks like it was
  never run.
- **Mobile:** sections stack; Bull/Bear collapse to sequential (not
  side-by-side) cards.

### Journal (`/journal`, `/journal/new`)

- **Key content:** every logged `TradeJournalEntry`, open positions
  (derived, FR-33) computed the same way the existing Alpaca-paper
  position derivation works (ADR-013's pattern reused).
- **Key actions:** log a new entry (symbol/side/qty/price/timestamp/
  broker label/notes, optional recommendation link); close/edit an entry.
- **Empty state:** "no journal entries yet" with a prominent "log a trade"
  action — this is the primary portfolio view once shipped, so its empty
  state matters more than the existing Portfolio page's did.
- **Error state:** a save failure (e.g. invalid data) surfaces inline on
  the form, same `ErrorBanner` pattern as the shipped MVP's `ConfirmButton`
  flows.
- **Mobile:** entry form is the most mobile-critical new surface (logging
  a trade "in ten seconds," per the user story) — single-column, large
  touch targets, symbol autocomplete against the watchlist.

### Monitor & Alerts (`/monitor`)

- **Key content:** every open journal position with its current suggestion
  (`HOLD`/`TIGHTEN_STOP`/`TAKE_PARTIAL`/`EXIT`/`WATCH_CLOSELY`, FR-35) and
  the numbers behind it; an alerts feed (FR-29, in-app only per
  BLOCKING_DECISIONS.md #9) below or alongside it.
- **Key actions:** none that mutate anything (FR-36 — suggestions only);
  jump to the journal entry to log an exit/adjustment the user actually
  made in response.
- **Empty state:** "no open positions" (nothing to monitor) vs. "no new
  alerts" are distinct empty states, not collapsed into one message.
- **Stale-data state:** if the intraday job hasn't run recently (e.g.
  outside market hours, or a failure), the suggestion cards show their
  last-computed timestamp plainly rather than implying real-time freshness
  they don't have.
- **Mobile:** this is the second most mobile-relevant page (checking a
  held position during the day) — suggestion cards prioritized above the
  alerts feed on small screens.

### Performance (`/performance`)

- **Key content:** realized/unrealized P&L, win rate, avg R-multiple, max
  drawdown, benchmark comparison (FR-37), time-windowed (week/month/all-
  time, FR-39), plus the recommendation-vs-reality breakdown
  (followed/ignored/modified and their outcomes, FR-40–FR-42).
- **Key actions:** switch time window; drill into a specific closed
  position or recommendation.
- **Empty state:** before any closed trades exist, show the structure
  (empty charts/tables with "no closed trades yet in this window") rather
  than hiding the page — the user should be able to see *what* this page
  will eventually show them.
- **Mobile:** charts scroll horizontally inside their own container (same
  pattern as any wide table elsewhere in this app); summary numbers stack
  above the charts.

## Cross-cutting states (apply to every new page)

- **Stale/missing evidence:** any card or number derived from evidence
  that's missing or beyond its freshness threshold shows a visible
  "stale"/"unavailable" marker inline, never silently substitutes an old
  value as if current (principle 5, reused from the shipped MVP's existing
  posture on price-data freshness).
- **Quarantined symbols:** never appear in a primary list (watchlist table,
  premarket plan) without their quarantine badge; never silently excluded
  either — a quarantined symbol the user explicitly added should still be
  visible *as quarantined*, not vanish.
- **Vendor/job failure:** distinct from "no data yet" — a failure state
  names what failed and offers a retry where one makes sense (symbol
  validation, evidence refresh); a scheduled job failure additionally
  surfaces on the Premarket Plan / Monitor pages since those are exactly
  where a silent failure would otherwise go unnoticed.
- **Mobile, general:** every new page follows the existing app's
  responsive posture (`resize_window`-verified during implementation, same
  as every shipped-MVP page) — single-column stacking, horizontally-
  scrollable tables/charts inside their own container, no fixed-width
  layout assumptions.
