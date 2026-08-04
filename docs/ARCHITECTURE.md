# Architecture

This document covers the shipped Phases 1–7 foundation (unchanged) plus the
bounded contexts the refinement brief adds. Nothing here is scaffolded yet —
this is the target architecture the blocking decisions
(docs/BLOCKING_DECISIONS.md) and MVP plan (docs/MVP_PLAN.md) assume.

## Context diagram

```mermaid
flowchart TB
    User(["Retail investor\n(sole user)"])

    subgraph TradingOS
        Web["apps/web\nNext.js"]
        Api["apps/api\nFastAPI"]
        Scheduler["In-process scheduler\n(premarket / intraday / EOD jobs)"]
        DB[("PostgreSQL")]
    end

    Alpaca["Alpaca Markets\n(price data, paper broker,\nasset reference — existing)"]
    NewsVendor["News/fundamentals/earnings\nvendor(s) — TBD, free-tier MVP\n(BLOCKING_DECISIONS.md #1)"]
    VixProxy["VIXY/VIXM via Alpaca\n(VIX proxy — #2)"]
    Anthropic["Anthropic Claude\n(committee synthesis only,\nnever numeric ground truth)"]

    User -- "reads plan, journals trades,\napproves strategy changes" --> Web
    Web -- "HTTP/JSON, server-side only" --> Api
    Api -- "SQLAlchemy" --> DB
    Scheduler -- "same service layer as API" --> Api
    Api -- "price bars, asset reference,\npaper order fills" --> Alpaca
    Api -- "VIX-proxy bars" --> VixProxy
    Api -- "news, fundamentals,\nearnings calendar" --> NewsVendor
    Api -- "8 committee-role calls,\ntool-use, schema-validated" --> Anthropic

    style Anthropic fill:#eef,stroke:#88a
    style Alpaca fill:#efe,stroke:#8a8
    style NewsVendor fill:#ffe,stroke:#aa8
    style VixProxy fill:#efe,stroke:#8a8
```

`apps/web` never talks to any external vendor directly — everything routes
through `apps/api`, the only place any secret is held (unchanged from the
shipped MVP). The scheduler is not a separate process or trust boundary; it
runs inside `apps/api` and calls the same service functions the HTTP routes
call (BLOCKING_DECISIONS.md #4) — there's no new external attack surface
from adding it.

## Data flow: ingestion → recommendation → user action → outcome review

```mermaid
flowchart LR
    subgraph Ingestion
        A1["Symbol validation\n(Alpaca asset reference)"]
        A2["Price bars + indicators\n(existing, unchanged)"]
        A3["Evidence: news,\nfundamentals, earnings"]
        A4["VIX-proxy → regime\nclassification"]
    end

    subgraph Analysis["Analysis pipeline (per pre-filtered symbol)"]
        B1["Deterministic pre-filter\n(all Tier 1, no LLM)"]
        B2["Evidence bundle\nassembled + provenance-tagged"]
        B3["8-role committee\n(Bull/Bear/Tech/Fund/Macro/\nRisk/PM/CIO)"]
        B4["Deterministic gates:\nstop/target, position size,\nearnings warning, no-avg-down"]
    end

    subgraph Output
        C1["Recommendation\n(BUY/SELL/HOLD/WATCH/\nAVOID/NO_ACTION)"]
        C2["Premarket plan /\nEOD review artifact"]
        C3["Intraday alert"]
    end

    subgraph UserAction["User action (outside the system)"]
        D1["Manual trade journal entry\n(any broker)"]
        D2["Ignored — no entry"]
    end

    subgraph Review["Outcome review"]
        E1["Recommendation-vs-reality\nclassification"]
        E2["Position closes →\noutcome attached"]
        E3["Performance dashboard"]
        E4["Recommendation-vs-reality\nfeeds future calibration\n(Phase 2, principle 15)"]
    end

    A1 --> A2 --> B1
    A3 --> B2
    A4 --> B4
    B1 --> B2 --> B3 --> B4 --> C1
    C1 --> C2
    C1 --> C3
    C1 -->|user reads plan| D1
    C1 -->|user reads plan| D2
    D1 --> E1
    D2 --> E1
    E1 --> E2 --> E3
    E1 --> E4
```

Every arrow above crosses through the same audit-event write the shipped
MVP already established (principle 9) — not drawn per-arrow above for
readability, but every box that produces a new record writes one.

## The fact → calc → inference → decision pipeline (principle 2), extended

Unchanged in kind from the shipped MVP, extended in coverage:

1. **Observed facts** — Alpaca price bars/fills (existing), plus news
   headlines, fundamentals snapshots, earnings dates, VIX-proxy bars (new).
   All carry source/symbol/timestamp/timezone/freshness (principle 3);
   never fabricated (principle 4).
2. **Deterministic calculations** — existing indicators, plus: regime
   classification, ATR+structure stop/target, risk-budget position sizing,
   symbol-validation resolution, recommendation-vs-reality classification,
   active-trade-monitor suggestions. All plain code, unit-tested, versioned,
   no LLM involvement (principle 6).
3. **Model inferences** — existing single-call `/ask` synthesis, plus the
   8-role committee's structured outputs and the CIO's final narrative.
   Grounded only in tool results (evidence bundles + stage-2 calculations);
   never invents a number (principle 4/7).
4. **User decisions** — existing paper-order actions, plus: manual journal
   entries, watchlist tier changes, strategy-version approvals. Recorded,
   never inferred.

## Bounded contexts

Each context below is either **existing** (shipped Phases 1–7, unchanged)
or **new** (this refinement). New contexts follow the same
provider-abstraction and audit-event patterns the existing ones already
established — no new architectural pattern is introduced, only new
instances of the existing ones.

### 1. Market Data & Reference (existing, extended)
`Symbol`, `PriceBar`, `Indicator` (unchanged) + **new:** symbol validation
records (resolution status/reason, canonical match, raw input preserved).
Owns: "is this a real, tradable instrument, and what does its price history
actually say." Provider: Alpaca (`MarketDataProvider`, existing interface,
extended with an asset-reference lookup method).

### 2. Evidence & Context (new)
News items, fundamentals snapshots, earnings-calendar entries, VIX-proxy-
derived regime inputs. Owns: "what's true about this symbol and the market
right now, beyond price." Each evidence type gets its own thin provider
interface (`NewsProvider`, `FundamentalsProvider` — likely one vendor
covers both per BLOCKING_DECISIONS.md #1) following the exact shape of the
existing `MarketDataProvider`/`LLMProvider` Protocols — fakeable in tests,
swappable without touching callers. Every result carries the same
provenance envelope as `PriceBar` (FR-14).

### 3. Watchlist Management (new)
`Watchlist` + tiered membership, monitoring frequency. Owns: "what am I
actively tracking, and how often." Thin — mostly CRUD plus the rule that
membership requires a validation record (FR-05).

### 4. Regime & Risk Budget (new)
Regime classification (FR-01–FR-03) and its downstream effect on the
risk-budget/allocation ceiling used by context 6 below. Owns: "how
aggressive should sizing be right now, market-wide" — deliberately separate
from per-symbol analysis, since it's a portfolio-level, not symbol-level,
concern.

### 5. Investment Committee / Analysis Pipeline (new — the core expansion)
Orchestrates: deterministic pre-filter → evidence assembly → 8 committee
roles (parallel-callable Bull/Bear/Technical/Fundamental/Macro roles, then
sequential Risk Manager → Portfolio Manager → CIO/Judge, since the CIO
needs every other role's output plus the deterministic gates) → final
`Recommendation`. Reuses the existing `LLMProvider` interface and tool-use
pattern (docs/MODEL_GOVERNANCE.md) — each role is a distinct prompt
version + a distinct typed tool result schema, not 8 free-text calls.
Owns: "what does the evidence actually suggest, argued from multiple
angles, synthesized into one auditable call."

### 6. Deterministic Gates (new)
Stop/target (ATR+structure+gap+catalyst+trailing), position sizing
(risk-budget÷stop-distance, capped by allocation/liquidity/sector/
correlation/speculative-name limits), no-average-down precondition,
earnings-window warning. Owns: "the numbers the committee is not allowed to
invent or override" (principle 6/7) — structurally called *before* the CIO
role runs (FR-19), not after, so a blocked gate is never something the CIO
narrative could talk its way around.

### 7. Portfolio & Trade Journal (existing, extended)
Existing: `PaperPortfolio`/`PaperOrder` via the Alpaca adapter, kept as the
practice sandbox (BLOCKING_DECISIONS.md #5). **New:** `TradeJournalEntry` —
broker-agnostic, user-entered, the primary tracked portfolio. Both contexts
share the existing derived-position-from-events pattern (ADR-013) — a
journal's current holdings are computed from entries, never stored
redundantly.

### 8. Active Trade Monitor (new)
Reads open journal positions + context 6's stop/target logic, produces
hold/tighten/partial/exit/watch suggestions (FR-35). Owns: "should anything
change about a position I already hold" — deliberately reuses context 6's
math rather than a second stop/target implementation.

### 9. Scheduling & Workflows (new)
Premarket, intraday, EOD jobs (BLOCKING_DECISIONS.md #4). Owns: "when do
the above contexts actually run, unattended." In-process scheduler calling
existing service functions — not a distinct deployable, not a distinct
trust boundary.

### 10. Performance & Learning (existing, extended)
Existing: `StrategyVersion` governance loop, `BacktestRun`
(single-window). **New:** performance dashboard aggregation over the
journal, recommendation-vs-reality classification and outcome attachment.
Owns: "how well is this actually working, both the user's trading and the
system's calls." Walk-forward backtesting (docs/MVP_PLAN.md Phase 2) would
extend `BacktestRun`'s existing shape, not replace it.

### 11. Observability, Security, Audit (existing, extended)
Existing `AuditEvent` pattern, `.env`-only secrets, no client-side vendor
exposure. Extended to every new entity above (FR-48) — no new mechanism.

## Trust boundaries

Unchanged shape from the shipped MVP, more instances of the same boundary
type:

- **Browser ↔ `apps/api`** — the only boundary the user's own machine
  crosses; no secret ever crosses it (existing posture, docs/SECURITY.md).
- **`apps/api` ↔ each external vendor** (Alpaca, VIX-proxy — also Alpaca,
  the new evidence vendor(s), Anthropic) — each held behind its own
  Protocol interface; a vendor credential lives only in `apps/api`'s
  server-side environment, never logged, never in a prompt sent back to the
  user verbatim beyond the evidence text itself.
- **`apps/api` ↔ PostgreSQL** — unchanged, SQLAlchemy, least-privilege role
  (ADR-008).
- **Scheduler ↔ everything else** — not a new boundary; the scheduler is
  in-process and calls the same functions the API layer calls, under the
  same credentials, in the same trust zone.

See docs/THREAT_MODEL.md for the threats considered at each boundary above.

## Deployment topology

Unchanged single-personal-deployment shape (docs/OPERATIONS.md): one
`apps/api` process (now also running the in-process scheduler), one
`apps/web` process, one PostgreSQL instance, all on the same local machine
for MVP. No new deployable, no new process, no new network boundary beyond
the new outbound vendor calls listed above. A future move to Vercel/Supabase
(if ever pursued) would need the scheduler re-hosted as a real cron/worker
process at that point — flagged here as a known consequence of the
in-process choice (BLOCKING_DECISIONS.md #4), not a blocker for the current
local-personal-use deployment.

## Provider abstraction pattern (existing, extended)

`apps/api/src/tradingos_api/providers/` gains new Protocol interfaces
following the exact existing pattern (`MarketDataProvider`,
`PaperBrokerProvider`, `LLMProvider`): a `NewsProvider`/`FundamentalsProvider`
(evidence context) and possibly a distinct `RegimeDataProvider` if the
VIX-proxy lookup doesn't fit cleanly inside `MarketDataProvider`. No new
pattern — the same "callers depend on the interface, tests inject a fake,
a vendor swap doesn't touch call sites" reasoning applies identically.

## Monorepo layout, extended

```
TradingOS/
  apps/
    web/     (existing, extended with new pages — see docs/UX_MAP.md)
    api/
      src/tradingos_api/
        core/       (existing: settings, dependencies, rate limiter)
                    + scheduler wiring (new)
        db/         (existing, unchanged pattern)
        providers/  existing (alpaca_market_data, alpaca_paper_broker,
                    anthropic_llm) + new (news/fundamentals vendor,
                    regime/VIX-proxy — may reuse alpaca_market_data)
        models/     existing (symbol, price_bar, indicator, paper_*,
                    strategy_version, recommendation, backtest_run,
                    audit_event, llm_call_log)
                    + new (watchlist, watchlist_membership,
                    symbol_validation, news_item, fundamentals_snapshot,
                    earnings_event, regime_snapshot, committee_run,
                    trade_journal_entry, recommendation_outcome,
                    scheduled_artifact)
        schemas/    existing + new (one per new model, same pattern)
        routers/    existing + new (watchlist, symbol-validation,
                    committee/recommendations, journal, monitor,
                    performance, alerts)
        services/   existing (indicators, price_bars, portfolio,
                    reconciliation, scoring, strategy, backtest, ask,
                    llm_tools, llm_cost, audit)
                    + new (symbol_validation, regime, evidence,
                    committee, gates/sizing, gates/stops, journal,
                    monitor, performance, rec_vs_reality, scheduler_jobs)
  infra/     (unchanged)
  docs/      (this file + new: MVP_PLAN.md, UX_MAP.md, THREAT_MODEL.md,
              RISK_REGISTER.md, BLOCKING_DECISIONS.md)
```

No file above is created by this pass — this is the target structure for
whichever implementation phase follows, once docs/BLOCKING_DECISIONS.md is
confirmed.
