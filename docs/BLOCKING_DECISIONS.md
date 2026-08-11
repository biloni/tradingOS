# Blocking Decisions

Eleven decisions (ten from the original refinement pass, plus #11 added in
Revision Prompt R1) that materially affect architecture, vendor selection,
cost, or security boundaries — exactly the categories
PROJECT_INSTRUCTIONS.md's working method requires stopping for. Each has a
recommended default so implementation isn't blocked on an answer; **no
default here has been acted on** — nothing is scaffolded, no vendor is
contracted, no paid tier is selected, no config value has been changed.
Silence is not consent: these stay open until you confirm or override them
explicitly, most importantly #1, #2, and #6 (the ones with real recurring
cost or new secrets) and #11 (the one confirmed conflict against an
already-shipped default).

## 1. Which vendor(s) supply news, sentiment, fundamentals, and earnings-calendar data?

Alpaca (the existing vendor) has no fundamentals/earnings-calendar product
and only a narrow news feed (headlines, not sentiment-scored). Every
"evidence" capability the refinement asks for beyond price/technicals needs
at least one new vendor, and PROJECT_INSTRUCTIONS.md explicitly says not to
select a paid one without approval.

**Recommended default:** start MVP with the cheapest viable combination —
Alpaca's included news endpoint (headlines only, no sentiment score — the
Fundamental/Macro/Sentiment analyst roles say "insufficient evidence" rather
than inventing a score, per principle 4/5) plus one free-tier fundamentals/
earnings-calendar API (candidates in docs/PROVIDER_MATRIX.md — Financial
Modeling Prep and Finnhub both have usable free tiers). Defer a paid
sentiment/news vendor (e.g. a licensed news-sentiment API) to Phase 2 of the
refined roadmap, revisited only if the free tier's coverage/rate limit
proves actually limiting in practice, and only with your explicit sign-off
on the specific vendor and cost.

## 2. What supplies VIX and broader macro data?

Alpaca's equities feed doesn't carry the CBOE VIX index itself. "Configurable
volatility regimes using VIX level, percentile, rate of change, term
structure" needs a real VIX source.

**Recommended default:** track VIX via its liquid ETP proxies already
tradable through Alpaca — `VIXY` (front-month VIX futures ETN, close proxy
for spot VIX level/rate-of-change) and, if term-structure comparison is
wanted, `VIXM` (mid-term futures ETN) alongside it — zero new vendor, zero
new cost, reuses the existing `MarketDataProvider`. This is a documented
approximation (ETP price tracks futures, not the spot VIX index tick-for-
tick) — precise term-structure/percentile-rank analysis would need a real
CBOE data feed (a paid decision, deferred, same as #1) if the ETP proxy's
accuracy turns out to matter for exact percentile calculations.

## 3. Which symbols get the full 8-role LLM committee, and how often?

Running Bull/Bear/Technical/Fundamental/Macro/Risk/PM/CIO as 8 separate
Anthropic calls for all 48 Tier 1 names, every day, is real recurring
spend (modeled in docs/PROVIDER_MATRIX.md's cost estimate) and real
latency for a "concise premarket plan."

**Recommended default:** a cheap, deterministic pre-filter (existing
signal-agreement scoring, extended with regime/catalyst checks — no LLM
call) runs on all 48 Tier 1 names every trading day. Only names that clear
a configurable pre-filter bar (default: top 8 by deterministic score, plus
any name with a new user-flagged catalyst) get the full committee. Every
other name still gets a one-line deterministic status (score, regime, any
earnings-window warning) in the premarket plan, just not a full narrative.
This bound is itself a versioned, auditable config value (principle 8), not
a hardcoded constant.

## 4. Scheduler technology for premarket / intraday / EOD jobs

ADR-006 deferred a background-job system as having "no demonstrated use
case." A scheduled premarket plan (before market open), intraday alert
polling (during market hours), and an EOD review (after close) is a real,
demonstrated need now.

**Recommended default:** an in-process scheduler (APScheduler, running
inside the existing FastAPI process) triggering the same service-layer
functions the API routes call — no Redis, no Celery, no separate worker
process. This is the simplest reliable option for a single-user, single-
process personal app (matches PROJECT_INSTRUCTIONS.md's "simplest reliable
scheduler ... allow later replacement without changing domain logic," and
ADR-021's identical reasoning for the rate limiter). Revisit only if a job
needs to survive an API-process restart mid-run, which none of the three
jobs above do (each is idempotent and re-runnable).

**Built (Revision Prompt 16, task: real always-on scheduler/worker
process).** `core/scheduler.py` implements exactly this recommendation —
`apscheduler`'s `BackgroundScheduler`, started/stopped from `main.py`'s
`lifespan`, ticking every 60s and calling `decide_schedule()`/
`decide_reconciliation_schedule()` (`services/scheduler_jobs.py`'s
per-subject glue). See `docs/OPERATIONS.md`'s "Real always-on
scheduler/worker process" section for the operational detail.

## 5. Manual trade journal vs. the existing Alpaca-paper portfolio

The refinement wants trades "manually placed at any broker" tracked, plus
optionally connecting a paper broker later. The current `PaperPortfolio`/
`PaperOrder` model is Alpaca-specific (cash, positions, and fills are all
derived from real Alpaca paper-account activity).

**Recommended default:** add a new, broker-agnostic `TradeJournalEntry`
entity (user manually logs each fill: symbol, side, quantity, price,
timestamp, broker/account label, linked recommendation, notes) and make
**the journal the primary tracked portfolio** the dashboard/performance
views are built around. The existing Alpaca paper portfolio is kept, not
removed, but re-labeled as a secondary "practice sandbox" — useful for
testing the propose→confirm flow and for backtesting/strategy-comparison
infrastructure, which stay Alpaca-driven since they need a broker-shaped
fill simulator regardless. A position can exist in one, the other, or (if
the user chooses to also paper-trade the same idea) both, tracked
separately — no forced reconciliation between them.

## 6. Position-sizing risk budget

"Position size must derive from risk budget and stop distance" needs an
actual default risk-per-trade number to be computable at all.

**Recommended default:** 1% of total current equity risked per trade
(shares = (equity × 1%) / stop_distance_per_share), a standard retail
swing-trading default consistent with the "aggressive but capital
preservation is a hard objective" profile — aggressive enough to size
meaningfully into high-conviction setups, conservative enough that a full
stop-out on any single name is a small, recoverable drawdown. Configurable
and versioned like every other threshold (principle 8), capped by the
existing allocation/liquidity/sector/correlation/speculative-name limits
(docs/PRODUCT_REQUIREMENTS.md's FR-14 series) regardless of what the raw
risk-budget math would otherwise allow.

## 7. Symbol validation source of truth

The Tier 1 list includes several tickers that don't obviously resolve
(`SKHY`, `SPCX`, `NASA`, `DRAM`) and the product requires a real validation
workflow, not a silent assumption.

**Recommended default:** Alpaca's own assets reference endpoint
(`GET /v2/assets`) as the canonical source — it's the already-incumbent,
already-licensed provider, and it directly answers exchange, tradability,
and active/inactive status for anything Alpaca could ever place a paper (or
future live) order against, which is the property that actually matters
here. A ticker Alpaca doesn't recognize as tradable is quarantined
regardless of whether some other data provider happens to have a row for
it — "would we ever be able to act on this" is the right validation
question for a trading tool, not "does a symbol exist somewhere."

## 8. Speculative-name and sector classification for concentration limits

"Capped by ... sector, correlation, and speculative-name limits" needs a
concrete, computable definition of "speculative" and a sector taxonomy —
Alpaca's asset metadata doesn't carry either.

**Recommended default:** sector comes from the same free fundamentals
vendor selected in #1 (both Financial Modeling Prep and Finnhub's free
tiers include a sector/industry field). "Speculative" is a deterministic,
code-computed rule from data already in-house — no new vendor needed:
realized volatility (already computable from `ATR_14` relative to price)
above a configurable percentile threshold across the Tier 1 universe, OR a
name explicitly tagged speculative by the user at watchlist-add time
(several Tier 1 names — `IONQ`, `QBTS`, `SMCI`, `SKHY`, `SPCX` if they
validate — are exactly the kind of name this tag exists for). Correlation
uses the existing price-history data (a rolling correlation matrix computed
in code, no vendor needed).

## 9. Alert delivery channel

"Intraday alerts" could mean in-app only, or push/email/SMS.

**Recommended default:** in-app only for MVP — an "Alerts" feed the user
checks, populated by the same intraday scheduled job. No email/SMS/push
integration, which would mean a new vendor, new secrets, and a new outbound
trust boundary (docs/THREAT_MODEL.md) for a single-user personal tool that
already has the app open during its own working hours. Revisit only if
being away from the app during market hours turns out to defeat the point
of "intraday" alerts in practice.

## 10. Does the refined scope replace or extend the shipped Phases 1–7 MVP?

The current shipped app (Phases 1–7, this repo's `master` branch) has a
~30-symbol seed list, a 4-signal deterministic score, a single-call LLM
`/ask` tool, and no scheduler/journal/committee/regime layer at all.

**Recommended default:** extend, not replace. Every entity and service
built in Phases 1–7 (`Symbol`/`PriceBar`/`Indicator`, the Alpaca paper
broker adapter, `StrategyVersion`'s propose→backtest→compare→approve
governance loop, the audit-event pattern, the provider-abstraction pattern)
is reused as the foundation the refined product builds on, not thrown away.
docs/MVP_PLAN.md frames the refined scope as an additive "Phase 8+" body of
work on top of the existing shipped MVP, and docs/ARCHITECTURE.md's bounded
contexts are drawn as new/extended contexts alongside the existing ones,
not a rewrite.

## 11. (Revision Prompt R1) `RiskPolicy` default position/sector caps conflict with R1's recommended defaults

R1's recommended defaults name **maximum single position: 15%** and
**maximum sector exposure: 25%**. Phase 8's already-shipped, already-
seeded `RiskPolicy` schema (`apps/api/src/tradingos_api/models/identity.py`,
confirmed live via `GET /api/v1/settings/risk-policy`) defaults
`max_position_pct` to **20%** and `max_sector_pct` to **40%** — a real
conflict between a Prompt 0–3 artifact and this revision's recommended
numbers, not a hypothetical one.

**Recommended default (backward-compatible):** no schema or migration
change. `risk_policy` is already modeled as a single, user-owned,
mutable-in-place settings row — not versioned/approved like a strategy
(docs/DATA_DICTIONARY.md: "a user changing their own risk tolerance
doesn't need a backtest comparison to take effect") — and it is already
fully user-configurable via the existing `PATCH /api/v1/settings/risk-policy`
endpoint. The Python model defaults and the seed script's values (which
simply use those defaults, `scripts/seed_phase8.py::RiskPolicy(owner_user_id=user.id)`)
are a **starting point**, not a locked-in product decision. Resolution:
whichever future prompt actually wires deterministic position-sizing/
concentration gates against `RiskPolicy` (Prompt 6, per
docs/ORDER_AUTHORITY_MODEL.md's traceability table) updates the seed
script's/model's default values from 20%→15% and 40%→25% to match R1's
recommendation, as a plain value change with no migration required (the
column types and constraints are unaffected) — and documents that change
in that prompt's own commit, not silently. Until then, the shipped 20%/
40% defaults remain in effect and are not a bug, just an unconfirmed
default pending this decision.

**Not acted on.** No seed value or model default has been changed by this
revision — this entry exists so the conflict is recorded and requires
your explicit confirm/override before whichever future prompt implements
the gates that actually enforce these numbers.
