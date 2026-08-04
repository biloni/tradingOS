# User Guide

Covers every feature shipped through Phase 7. See README.md "Quickstart"
for exact commands to get both servers running locally.

## Running it locally

- API: http://localhost:8000 (`GET /health` returns a JSON status payload
  — see docs/API_CONTRACTS.md).
- Web: http://localhost:3000. A left sidebar links every section below;
  the top of each page names what it shows.

## Dashboard (`/`)

The landing page. Shows:

- A **portfolio snapshot** — cash, market value, total equity (see
  Portfolio section below for exact meaning).
- An **API status** card (the original Phase 1 health check, kept rather
  than dropped — knowing the API is reachable has real value on every
  page, not just this one).
- **Quick links** to every other section (Symbols & Charts, Paper
  Portfolio, Ask, Backtests, Strategy Versions).

## Symbols & Charts (`/symbols`, `/symbols/[ticker]`)

`/symbols` lists every tracked symbol (ticker, name, exchange, asset
type). Click a ticker to open its detail page.

The detail page shows:

- A **candlestick chart** of that symbol's price history
  (`lightweight-charts`).
- A **latest indicators** readout (SMA_20/SMA_50, RSI_14, MACD line/
  signal/histogram, Bollinger upper/mid/lower, ATR_14) as of the most
  recent date with computed indicators.

**Known limitation:** there is no indicator overlay drawn on the chart
itself (e.g. an SMA line over the candles). `GET /api/v1/symbols/
{ticker}/indicators` only returns a single day's snapshot, not a ranged
time series — plotting a real overlay line would require a new ranged
endpoint, which is out of scope for this phase. The indicators are shown
as a text readout instead of inventing data the API doesn't provide.

## Paper Portfolio (`/portfolio`)

Shows, in order:

1. **Holdings** — cash, total market value, total equity, and a
   per-position table (ticker, quantity, average entry price, current
   price, market value, unrealized P&L).
2. **Propose a paper order** — a form (ticker, side, quantity, order
   type, limit price if `LIMIT`). Submitting this **only creates a
   `DRAFT` order** — nothing is sent to Alpaca yet (principle 11: human
   confirmation immediately before any order action).
3. **Orders** — every paper order, with status. A `DRAFT` order shows
   **Confirm** and **Cancel** buttons; Confirm requires a second click
   ("Are you sure?") before it actually submits to Alpaca's paper-trading
   API. Orders in `SUBMITTED`/`PARTIALLY_FILLED` show a **Refresh**
   button (there is no background poller — ADR-016 — so refreshing a
   still-open order is a manual, explicit action).
4. **Reconciliation** — this app's derived position quantities compared
   against what Alpaca's paper account actually reports, with any
   discrepancy called out.

**Walkthrough:** fill in a ticker (e.g. `AAPL`), leave the defaults
(BUY, quantity 1, MARKET), click **Propose order** — a `DRAFT` row
appears. Click **Confirm** — the row shows "Are you sure?"; click
**Confirm** again — the order is submitted to Alpaca, and its status
updates to `SUBMITTED` or `FILLED` once the order clears (paper trading
fills near-instantly during market hours, with a brief delay otherwise).

## Ask (`/ask`)

A chat-style panel for natural-language questions about the tracked
symbols, e.g. "What does AAPL's current setup look like?" Backed by
`POST /api/v1/ask`, which uses Claude in a **tool-use** pattern — the
model calls typed, server-validated tools (`query_symbols`,
`get_price_summary`, `get_indicators`, `get_recommendations`,
`compute_recommendation`) and only synthesizes from what those tools
actually returned; it never writes or executes SQL, and it never invents
a price or a score (principles 6/7). Any recommendation the model
surfaces is rendered as a small chip (ticker, deterministic score,
confidence pill) below the answer.

This is stateless per request (ADR-019) — the page keeps its own local
message history for display, but each question is answered independently
server-side. If a question triggers a rate limit, a missing-API-key
condition, or fails validation, the page shows a specific explanation
(not a generic error) for each of those three cases.

## Backtests (`/backtests`, `/backtests/[id]`)

`/backtests` lets you run a new backtest (optionally overriding the date
range; every other parameter uses the currently-active strategy version's
defaults) and lists every past run. Each run's detail page
(`BacktestReport`, also reused by the strategy compare view below) shows:

- Summary metrics: ending equity, total return %, max drawdown %, win
  rate %, trade count, average win/loss %, and the benchmark return % (if
  a benchmark ticker was set).
- An **equity curve** chart.
- A full **trade log** table (entry/exit date and price, quantity, P&L,
  and the exit reason — signal exit, max holding period reached, or
  end-of-backtest force-close).

## Strategy Versions (`/strategy-versions`, `/strategy-versions/[id]`)

`/strategy-versions` has a **propose a candidate** form — a structured
set of typed fields (per-signal weights, RSI thresholds), not a raw JSON
box, since the shape is fixed and validated server-side — plus a list of
every strategy version and its status (`PROPOSED`/`ACTIVE`/`REJECTED`/
`SUPERSEDED`).

A `PROPOSED` candidate's detail page shows a **Review** card:

1. **Compare against active** — runs two fresh backtests (candidate vs.
   whatever is currently `ACTIVE`) and shows the delta (candidate minus
   active) for every summary metric, plus both full `BacktestReport`s
   side by side. This is read-only and repeatable (ADR-028) — it never
   changes the candidate's status, so you can compare as many times as
   you like before deciding.
2. **Approve** / **Reject**, each behind the same two-step confirmation
   gate as the paper-order flow, with an optional comment. Approving
   re-runs the comparison itself (never trusting an earlier `/compare`
   call) as the audit-trail snapshot, activates the candidate, and
   supersedes whatever was previously `ACTIVE`. The system never enforces
   a numeric approval bar — a human decides; the UI's job is only to
   surface the comparison clearly.

Once a version leaves `PROPOSED` (approved, rejected, or superseded), the
Review card disappears — the decision and its comment remain visible on
the detail page, but the actions themselves are one-time.

## What's not here yet

- No historical-outcome-based confidence calibration (needs a real sample
  of completed trades post-activation — docs/MODEL_GOVERNANCE.md).
- No authentication/multi-user support — single-user personal tool by
  design (ADR-007).
- No live-order capability anywhere in the codebase, by design
  (principle 10) — every order action in this app is paper trading only.
- No persisted multi-turn `/ask` conversation history — each question is
  answered independently (ADR-019).
- No SMA/indicator overlay line on the price chart (see the Symbols
  section above for why).
