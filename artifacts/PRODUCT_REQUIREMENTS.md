# Product Requirements

## Mission

TradingOS is a trustworthy, explainable decision-support application for a
retail investor doing swing trading (2–10 trading-day holding periods). It
identifies and monitors candidate trades, manages a configurable paper
portfolio (initially funded with $10,000), tracks trades the user actually
places, measures performance, and improves recommendations through
evidence-based review.

It is **not** a chatbot, **not** a guaranteed-profit system, and **not** an
unreviewed autonomous trading bot. See PROJECT_INSTRUCTIONS.md for the full
set of non-negotiable product principles that govern every design decision in
this repo.

## MVP scope

- **Market universe:** US-listed equities and ETFs only (ADR-003).
- **Time horizon:** 2–10 trading-day swing trades. Not intraday/day-trading.
- **Portfolio:** one configurable paper portfolio, starting cash $10,000 USD.
- **Data & broker vendor:** Alpaca Markets, paper trading only (ADR-002).
- **Recommendation engine:** deterministic indicators/scoring + an LLM
  synthesis layer (Anthropic Claude) for explanation and scenario analysis —
  never for the numeric ground truth (principles 6/7).
- **Backtesting:** historical strategy evaluation with realistic fills, no
  look-ahead bias.
- **Learning loop:** strategy changes proposed by the system require a
  backtest report, comparison against the current version, and explicit user
  approval before activation (principle 16).
- **Audit trail:** every recommendation, score, input snapshot, prompt
  version, model response, user action, order, and override is recorded
  immutably (principle 9).

## Explicitly out of scope for MVP

- **Live broker order placement.** Absent, not merely feature-flagged off
  (principle 10). A future phase would add this behind an explicit approval
  process and a separate interface — nothing in the current
  `PaperBrokerProvider` interface has a live-order method.
- Options, futures, crypto, and non-US markets.
- Multi-user support / authentication (ADR-007) — this is a personal, single-
  user tool.
- Day-trading / intraday strategies (Alpaca's free data tier is 15-min
  delayed IEX data, adequate for a multi-day swing horizon, not for
  intraday decisions).

## Phase roadmap

See docs/TASKS.md for the authoritative, checkbox-tracked breakdown. Summary:

1. **Foundations & architecture** (this phase) — repo scaffold, docs, vendor
   ADRs, no trading logic yet.
2. **Data ingestion & indicators** — Alpaca market data client, deterministic
   technical indicators, corporate-actions handling.
3. **Paper portfolio & trade tracking** — portfolio accounting, order
   lifecycle, position reconciliation against Alpaca's paper account.
4. **Scoring engine & LLM synthesis** — deterministic scoring, the `/ask`-
   equivalent NL/explanation feature, prompt versioning, cost tracking.
5. **Backtesting** — historical replay with realistic fills, no look-ahead.
6. **Learning / strategy-review loop** — proposed strategy changes gated on
   backtest report + user approval (principle 16).
7. **UI polish & documentation hardening.**

## Acceptance philosophy

Depth over breadth: a smaller feature set that works flawlessly beats a
broad one that half-works. Every phase ends with a working, tested,
documented increment — never a partial implementation left mid-stream.
