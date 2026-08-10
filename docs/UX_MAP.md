# UX Map

Pages, navigation, key actions, and state handling for the refined product.
Existing shipped pages (Dashboard, Symbols, Portfolio, Ask, Backtests,
Strategy Versions) are listed first as unchanged/lightly-extended; new
pages follow. As of Revision Prompt R2, every route below is **scaffolded**
(a real Next.js route rendering synthetic placeholder content) — see
"R2 scaffold status" per page; the underlying provider calls, strategy
calculations, recommendations, scheduling, and broker submission remain
unbuilt, per R2's explicit scope limit.

## R2 route-naming reconciliation

Revision Prompt R2 named its required routes slightly differently than
this document's original (R1) placeholder paths. R2's names are now
canonical; the mapping:

| R1 original path | R2 actual scaffolded path | Note |
|---|---|---|
| `/premarket` | `/` | R2: "Make Morning Dashboard the default authenticated landing route" — no separate `/premarket`-style path exists; a future `/morning-plan/[date]` historical-view route (FR-31) is still unbuilt. |
| `/watchlist` | `/watchlists` | Matches R2's literal route name. |
| `/committee/[symbol]/[recommendationId]` | `/agent-review` | R2 named this route "Agent Review"; the per-symbol dynamic sub-route (`/agent-review/[symbol]/[recommendationId]`) is future work once real committee data exists — R2's scaffold is a single flat page. |
| `/monitor` (combined monitor + alerts) | `/alerts` | R2's route list separates "Alerts" as its own placeholder; the active-trade-monitor half of the original combined page does not have its own route yet — candidate future homes are `/alerts` itself or a new `/monitor` route, not decided by this pass. |
| `/journal`, `/performance` | unchanged | Same paths. |
| (none) | `/investment`, `/tactical`, `/earnings`, `/approvals`, `/orders`, `/settings` | New in R2 — no R1 equivalent path existed for these. |
| `/` (old Phase 1-7 Dashboard) | `/legacy-dashboard` | Relocated, not deleted, when `/` became the Morning Dashboard — still fully functional and tested against the (retired) old API shape, kept for reference rather than removed. |

## Navigation

Left sidebar, extended from the shipped 6-item version to reflect the
watchlist/committee/journal/monitor loop as the new primary path, with the
existing pages kept as secondary/supporting:

```
Morning Dashboard   (/, scaffolded R2 — the default landing page, R1
                     rename of the earlier "Premarket Plan" concept)
Investment           (/investment, scaffolded R2)
Tactical Trades       (/tactical, scaffolded R2)
Earnings Center      (/earnings, scaffolded R2)
Approval Queue       (/approvals, scaffolded R2)
Orders and Fills     (/orders, scaffolded R2 — order lifecycle)
Watchlists           (/watchlists, scaffolded R2)
Agent Review         (/agent-review, scaffolded R2 — committee detail)
Journal              (/journal, scaffolded R2)
Alerts               (/alerts, scaffolded R2)
Performance          (/performance, scaffolded R2)
─────────────────
Portfolio        (existing — re-labeled "Paper Sandbox", ADR-039)
Symbols          (existing, unchanged)
Ask              (existing, unchanged)
Backtests        (existing, extended — new gates reflected in results)
Strategy         (existing, unchanged mechanism, bigger config)
Settings         (/settings, scaffolded R2)
Legacy Dashboard (/legacy-dashboard, R2 — relocated old Phase 1-7 Dashboard)
```

**Persistent environment banner (R2, implemented).** A full-width banner
above the sidebar/main layout, always mounted (`app/layout.tsx`), showing
RESEARCH/PAPER/LIVE from `GET /api/v1/settings/operating-mode` — never
client storage, never hideable by a query parameter (no code path in
`EnvironmentBanner.tsx` reads a URL at all — verified by a structural
test, `__tests__/environment-banner.test.tsx`).

**Top bar, R1 addition: operating-mode indicator (R2: implemented,
nonfunctional).** Every page that can show an order or recommendation
action displays the current `OrderAuthorityMode`
(`RESEARCH_ONLY`/`PAPER_MANUAL_APPROVAL`/`PAPER_AUTO_POLICY`/
`LIVE_CONFIRM_EACH_ORDER`) via `OperatingModeStatus.tsx`, sourced from
`GET /api/v1/settings/operating-mode` (never client storage). This is a
**display-only** surface as of R2 — it has no control to change the
mode (a real selector remains future scope per FR-58) and must never
widen what the server actually authorizes regardless of what it
displays: selecting a different mode, once a selector exists, sends a
request the server may deny exactly the way any other authorization
check can fail; the UI never assumes the requested mode took effect
until the server confirms it, and never silently falls back to acting
as if a wider mode were active if the request is denied.

**Reusable UI primitives (R2, implemented — `components/ui/`).** Every
new page composes from these rather than inventing its own badge/banner
shape: `DecisionLaneBadge` (Investment ◆ / Tactical ▲, shape-differentiated
so lane is legible without color), `DataFreshnessBadge` (Fresh/Stale/
Unavailable, always text-labeled), `EvidenceCompletenessIndicator`
("N of M evidence categories available" plus a missing-categories list),
`ApprovalRequiredBadge`, `EventRiskWarning` (always states the stop-is-
not-a-guarantee caveat in text, HES-5), `IncompletePlanBanner`
(`role="alert"`), `SourceTimestamp` (source/timestamp/freshness, plain
text), and `OrderStateTimeline` (each lifecycle step's status is both an
icon and visually-hidden text, e.g. "Approved (current)", so a screen
reader gets the same information a sighted user does). A shared
`PageState` component (`components/ui/PageState.tsx`) covers all seven
required non-happy-path states: empty, loading, stale, disconnected,
permission, market-closed, no-action — each distinguished by its title
text, never by color/icon alone. `__tests__/ui-primitives-a11y.test.tsx`
checks every primitive's text-based accessibility explicitly.

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

Every page in this section is **scaffolded as of Revision Prompt R2**
(a real route rendering synthetic placeholder content per
`docs/STATUS.md`'s R2 entry) — file paths given per page below.

### Morning Decision Dashboard (`/`, scaffolded: `app/page.tsx`) — R1 rename of "Premarket Plan", R2 moved it to the root route

The default landing page once this ships (replacing the current Dashboard
as the first thing the user sees, matching "busy, wants a concise premarket
plan"). **R1 formalizes this page against docs/MORNING_PLAN_SPEC.md** — same
underlying concept as the original "Premarket Plan" design below, extended
with the fixed seven-section grouping, dual-refresh timing, and the
`COMPLETE`/`INCOMPLETE` labeling MDS-1..MDS-5 require.

- **Key content:** generation metadata banner at the very top (MDS-3) —
  when generated, evidence cutoff, `PRELIMINARY`/`FINAL` label, next
  refresh time, provider health, market-calendar status — followed by
  regime summary (FR-01–FR-03), then the seven fixed sections in order
  (**Act Now** capped at 3 headline entries, **Approval Required**,
  **Hold/Manage**, **Investment Watch**, **Tactical Watch**, **Avoid**,
  **Data Problems** — docs/MORNING_PLAN_SPEC.md). Every recommendation
  card shows its lane badge (`INVESTMENT`/`TACTICAL`, FR-52) prominently —
  a symbol appearing in both an Investment and a Tactical section renders
  as two separate cards, never merged.
- **Key actions:** expand a card → committee detail; jump to journal entry
  form pre-filled with a recommendation's symbol/side; for an "Approval
  Required" card, approve/reject inline (routes into the Orders page's
  lifecycle, FR-57); a `PRELIMINARY` plan shows a visible "final plan
  arrives at 06:10" notice rather than looking like the finished artifact.
- **Empty state:** before the first scheduled run of the day, show
  yesterday's `FINAL` plan with a clear "last updated" timestamp and a
  manual "run now" action — never a blank page (NFR-04's auditability
  applies to the UI too: there's always *something* concrete to show).
  freshness status shown per name if regime/evidence is stale beyond a
  configurable threshold.
- **Error / incomplete state:** if the scheduled job itself failed, show
  that explicitly ("morning plan generation failed at 6:02am — retry"),
  never silently show stale data without saying so. A plan labeled
  `INCOMPLETE` (docs/MORNING_PLAN_SPEC.md) shows a persistent, unmissable
  banner naming which sections/symbols are affected — distinct from a
  full generation failure.
- **Historical view:** `/morning-plan/[date]` retrieves the stored
  `FINAL` artifact for any past date (FR-31) — read-only, no
  re-computation; `?version=preliminary` retrieves that day's
  `PRELIMINARY` version separately, never conflated with `FINAL` in the
  same view.
- **Mobile:** cards stack single-column; the generation-metadata banner
  and regime summary stay pinned at top on scroll (they're the context
  every other card depends on for interpretation).

**Status: implemented (Revision Prompt 15, 2026-08-10).** `app/page.tsx`
is rebuilt against real `GET /api/v1/morning-plan/dashboard` data (no
longer synthetic). Primary layout matches Prompt 15's own live
instruction, which supersedes this section's earlier sketch the same
way `docs/MORNING_PLAN_SPEC.md` already documents for its own section
list: **Status strip** (market date, countdown, plan state, freshness,
evidence cutoff, regime, operating mode, kill switch —
`components/dashboard/StatusStrip.tsx`), **Portfolio strip** (equity,
cash, day/week P&L, drawdown, exposure, risk budget —
`components/dashboard/PortfolioStrip.tsx`, cross-referencing Revision
Prompt 12's own performance endpoint so dashboard and payroll-equivalent
figures tie out), then **Act Now**, **Approval Required**, **Buy and
Hold**, **Tactical Earnings**, **Existing Positions**, **Upcoming
Events**, **Watch/Avoid**, **Data and Job Health** — the backend's own
`BUY_AND_HOLD`/`TACTICAL_TRADES`/`UPCOMING_EVENTS`/`WATCH_AND_AVOID`/
`DATA_PROBLEMS` section keys (Revision Prompt 9's shipped hierarchy, not
this section's older `HOLD_MANAGE`/`INVESTMENT_WATCH`/`TACTICAL_WATCH`/
`AVOID` sketch) relabeled to Prompt 15's exact section names. **Existing
Positions** has no dedicated backend section key — it's a client-side
cross-cut of Act Now/Buy and Hold/Tactical Earnings, filtered by
`card_detail.evidence.lot_id` (see `app/page.tsx::existingPositions()`);
a held symbol can legitimately appear there *and* in its action section
at once, the same "two distinct entries, never merged" rule
`docs/MORNING_PLAN_SPEC.md` already applies to dual Investment/Tactical
identity. **Data and Job Health** additionally surfaces
`provider_broker_status` and the plan's own failed `quality_checks` —
real job/data-health signals, not just the `DATA_PROBLEMS` section
renamed. Every card's evidence/deterministic/AI-synthesis/policy-result/
user-broker-state detail is one click away via
`components/dashboard/EvidenceDetails.tsx` (a `<details>` disclosure,
not a modal — same "second explicit interaction, not a full dialog"
precedent `components/ui/ConfirmButton.tsx` already set); opening it for
a recommendation-backed card also lazily loads that
recommendation-version's entry/stop/target levels and committee
per-role stances (disagreement count) via two new endpoints (see
docs/API_CONTRACTS.md §28). "Approval Required" cards link to the new
`/approvals/[id]` page below when a real `OrderProposal`/`OrderApproval`
already exists for that recommendation version — `services/morning_plan_generate.py`
now looks this up honestly instead of hardcoding `NOT_YET_PROPOSED`
(docs/DECISIONS.md ADR-065).

### Order Approval (`/approvals/[id]`, new: `app/approvals/[id]/page.tsx`)

**Status: implemented (Revision Prompt 15, 2026-08-10).** The "final
immutable summary and deliberate confirmation" screen the prompt asks
for, built directly against the real, already-shipped Revision Prompt
R3/10 `OrderApproval` flow (`/api/v1/order-approvals/*`) — no new
backend business logic, only a UI on an existing contract.

- **Key content:** `ApprovalBoundFields` rendered verbatim as the
  immutable summary (side, quantity, order type, prices, time in force,
  max notional, the quote price captured at approval time, the integrity
  hash, expiry) — this is the same row the backend hashes and never
  mutates after creation. Once `APPROVED`, a second card shows the
  live ORDER FLOW steps 2-4 pre-submission snapshot (fresh quote, buying
  power, open positions/orders, trading-day check), recalculated on
  load, never reused from approval time.
- **Key actions:** `ConfirmButton`-gated Approve (`PENDING` → `APPROVED`)
  and, once approved, a second independently-gated Submit — both require
  a distinct second click ("Yes, approve/submit exactly as shown above"),
  never a single click reaching a broker.
- **Empty/error/stale states:** an unknown id shows an honest error, not
  a blank page; a denied approve/submit call (expired approval, a
  non-broker-backed `MANUAL` account, a market-moved pre-submission
  check) surfaces the server's real reason text, never a generic
  failure. If the app's global operating mode cannot submit orders
  (`can_submit_orders=false`, e.g. `RESEARCH_ONLY`), the page says so
  immediately after approval — before the two-click submit dance, not
  after — since it's a known-in-advance state, not a possible outcome
  worth making the user click through to discover (docs/DECISIONS.md
  ADR-065).
- **Mobile:** single-column card stack, same as every other page; all
  risk/warning text (denial reasons, emulation disclosure, expiry) stays
  full-width and un-truncated.

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

- **Key content:** a lane badge (`INVESTMENT`/`TACTICAL`, FR-52) at the
  very top of the page, before anything else — the single most important
  piece of context for interpreting everything below it. **R1 addition:**
  directly under the badge, an explicit "why this is a buy-and-hold-style
  thesis, not a tactical trade" panel for Investment recommendations (or
  the tactical equivalent for Tactical ones), rendering every field
  `DQ-1`/`DQ-2` requires — valuation range, thesis, expected horizon,
  review date, catalysts, risks, and objective thesis-break conditions for
  Investment; entry conditions, size, stop logic, targets, time exit,
  event risk, and cancellation conditions for Tactical — as separate,
  labeled fields, not paraphrased into the CIO narrative prose (FR-59,
  DQ-3's facts/calculations/inferences/decisions separation applied
  literally to this page's layout). If the symbol has earnings inside the
  holding horizon, an **earnings-workflow callout** (docs/HYBRID_EARNINGS_STRATEGY.md)
  appears here too: the earnings-direction score (with its 8 factors
  visible, never collapsed into a single number without them), whether
  the pre-event gate passed/failed and which specific condition(s) drove
  that, the sized pre-event risk budget if a position is proposed, and
  (once the announcement has occurred) the three post-earnings
  confirmation gates each shown pass/fail individually. Below that: the
  full 8-role output (ADR-038's structured schemas rendered as sections —
  Bull/Bear side by side, then Technical/Fundamental/Macro, then Risk/PM
  with the actual gate numbers, then the CIO narrative + final action),
  every cited evidence item shown with its provenance envelope (source,
  timestamp, freshness — FR-14), gate pass/fail detail (FR-26) including
  any gates that blocked the trade even if the CIO's narrative sounds
  favorable.
- **Key actions:** log a journal entry from this recommendation
  (pre-fills symbol/side); view the exact evidence bundle this run used;
  **R1 addition:** if the recommendation has a proposed order attached,
  jump to that order's lifecycle state on the Orders page (approve/
  reject inline is also available here as a shortcut, mirroring the
  Morning Decision Dashboard's inline approval action).
- **Empty/error state:** a role that failed structured-output validation
  (docs/MODEL_GOVERNANCE.md) shows as an explicit "this role's output
  couldn't be parsed" card, not a missing section that looks like it was
  never run.
- **Mobile:** sections stack; Bull/Bear collapse to sequential (not
  side-by-side) cards; the lane badge and buy-and-hold-vs-tactical panel
  stay above the fold even on a small screen — it's the context every
  other section depends on.

### Orders (`/orders`, `/orders/[id]`) — new, R1

The order-lifecycle surface docs/ORDER_AUTHORITY_MODEL.md defines —
distinct from Journal (which records what the user says they actually
did at any broker) and from the existing Portfolio/"Paper Sandbox" page
(which shows Alpaca's own paper-account state). This page shows this
app's own order lifecycle for orders it proposed and/or submitted itself.

- **Key content:** every order the app has drafted, grouped by lifecycle
  state (`DRAFT`/`APPROVAL_REQUIRED`/`AUTO_APPROVED`/`APPROVED`/
  `PAPER_SUBMITTED`/`LIVE_PENDING_CONFIRMATION`/`LIVE_SUBMITTED`/
  `FILLED`/`CANCELED`/`REJECTED`/`EXPIRED`/`INVALIDATED`), each card
  showing the full approval-binding snapshot (OA-8) once one exists —
  account, symbol, side, quantity, order type, prices, time in force,
  outside-hours flag, attached legs, max notional, linked recommendation
  version, and approval expiration — so "what exactly did I approve" is
  always answerable without cross-referencing another page. The current
  `OrderAuthorityMode` is shown per order (an order approved under
  `PAPER_MANUAL_APPROVAL` last week must still say so even after a mode
  change today).
- **Key actions:** approve/reject an `APPROVAL_REQUIRED` order (binds
  OA-8's fields at the moment of the click, never silently reuses a stale
  snapshot); for `LIVE_PENDING_CONFIRMATION`, a distinctly-styled
  "confirm live order" action that visibly differs from the paper
  confirm action (different color/copy, never the same button reused for
  both — the amendment's principle-11 restatement (`OA-5`) deserves a UI
  that can't be misclicked into); cancel an open order; and (`OA-9`) the
  kill switch and cancel-open-orders controls live here, each behind
  their own distinct confirmation step, never a single ambiguous "stop"
  button.
- **Empty state:** "no orders yet" — distinct from "no orders needing
  your approval right now," which is itself distinct from "no open
  orders" — three different empty states, not one generic message,
  matching how differently each one should make the user feel (nothing
  to review vs. nothing urgent vs. nothing at risk).
- **Error/invalidated state:** an `INVALIDATED` order shows exactly which
  condition invalidated it (price moved beyond the threshold, confirmation
  went stale, account/environment became ambiguous) — never a bare
  "invalidated," since the whole point of this state existing separately
  from `CANCELED` is that it's explainable.
- **Mobile:** the live-confirm action is large-touch-target and requires
  an unambiguous, deliberate tap — this is the one action on the entire
  app where a mis-tap has the highest real-world consequence once a live
  adapter exists (Prompt 17), so its mobile design gets specific scrutiny
  at implementation time, not just the app's general responsive pattern.

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

**Added, Revision Prompt 15 (2026-08-10) — applies app-wide, not just to
new pages:**

- **Dark/light theme, manually switchable.** Previously `prefers-color-scheme`
  only. `app/globals.css`'s `@custom-variant dark` makes every existing
  `dark:` utility class across the whole app respond to a `.dark` class
  on `<html>` instead — no component file needed to change.
  `components/layout/ThemeToggle.tsx` (top bar, every page) toggles and
  persists it; `app/layout.tsx`'s `beforeInteractive` script applies the
  persisted-or-system choice before first paint, so there's no flash of
  the wrong theme.
- **Keyboard navigation.** A skip-to-content link (first focusable
  element, jumps past the sidebar), a visible `:focus-visible` ring
  app-wide (never removed by a component), and every interactive control
  introduced this revision is a native `<button>`/`<a>`/`<input>` —
  reachable and operable by keyboard with no custom key handling needed.
- **Mobile navigation.** The sidebar (`components/layout/Sidebar.tsx`)
  is now an off-canvas drawer below the `md` breakpoint — closed by
  default, opened by a hamburger button, closed again on nav-link click
  or its own close button — rather than a permanent 224px-wide column
  that would otherwise cause horizontal page overflow on a phone-width
  viewport (a real, confirmed bug on `/` before this fix: `document.documentElement.scrollWidth`
  exceeded `clientWidth` at 375px).
- **Screen-reader summaries and accessible charts.** Every new dashboard
  region has an explicit `aria-label` (Status, Portfolio, per-section);
  status/lane/freshness badges throughout the app already carry text
  labels alongside color/icon (pre-existing `StatusPill`/`DecisionLaneBadge`/
  `DataFreshnessBadge` convention, unchanged, reused here). Charts
  (`CandlestickChart`/`EquityCurveChart`) are unchanged this revision —
  no new chart type was introduced.
- **Export, sorting, filtering.** Not newly added this revision beyond
  what already existed (the morning plan's own Markdown export from
  Revision Prompt 9, `GET /versions/{id}/export.md`); recorded as known
  UX debt below rather than fabricated.

## Known UX debt (Revision Prompt 15, 2026-08-10)

Recorded honestly rather than silently deferred — these are real gaps a
future pass should close:

1. **No sorting/filtering controls on the dashboard itself.** Sections
   render in the backend's own order with no column-sort or client-side
   filter UI. The "show more" expansion for a capped section (Act Now)
   is the only interactive list control added this revision.
2. **No CSV/PDF export of the dashboard view itself** — only the
   pre-existing morning-plan Markdown export (a different artifact, the
   full plan version, not this rendered screen).
3. **Expected-move magnitude is not shown separately from direction
   confidence on dashboard cards**, despite Prompt 15 asking for both.
   `card_detail.policy_result.confidence` is real and shown; a magnitude
   figure isn't present in `MorningPlanItem.card_detail` for most card
   types (only `UPCOMING_EVENTS` items carry a `days_remaining`, not a
   move estimate) — adding it would mean joining
   `EventExpectedMoveSnapshot` into `services/morning_plan_generate.py`,
   a real backend change out of scope for this frontend-focused pass.
   Confidence is never mislabeled as a probability or blended with a
   magnitude in its place — it's simply omitted where unavailable,
   consistent with this app's "never fabricate a missing figure" rule.
4. **"Existing Positions" is a client-side derived section**, not a
   first-class backend one — see the Morning Decision Dashboard entry
   above. It works correctly for what the current holding-guidance
   classification produces, but a future revision adding a dedicated
   backend section key would be more architecturally honest than a
   `lot_id`-presence filter.
5. **The Approval Queue list page (`/approvals`, not `/approvals/[id]`)
   remains an unwired R2 scaffold.** There is no `GET /api/v1/order-approvals?status=`
   list endpoint on the backend — only get-by-id, so a real "queue" list
   view isn't buildable without an additive backend endpoint. The
   dashboard's own Approval Required section is the real, live
   equivalent for now; the sidebar's "Approval Queue" link still points
   at unwired placeholder content.
6. **`/strategy-versions` has no backend at all** — not a wiring bug
   like the three fixed this revision (`/portfolio`, `/symbols`,
   `/legacy-dashboard`, all previously calling nonexistent endpoint
   prefixes, now pointed at the real `/api/v1/portfolio/accounts/*`,
   `/api/v1/instruments`, `/api/v1/market/instruments/*`, and
   `/api/v1/orders`), but a genuinely unbuilt feature (no propose/
   approve/compare router is mounted anywhere in `main.py`). Flagged
   separately rather than built in this pass — a real new backend
   feature, out of scope for a UX pass.
7. **Accessibility was verified structurally** (roles, labels, focus
   order, keyboard-operability of every new control, mobile overflow)
   but **not run through an automated axe-core/Lighthouse audit** — this
   revision's checks were manual/DOM-inspection based via the available
   browser tooling, not a formal automated accessibility test suite.
