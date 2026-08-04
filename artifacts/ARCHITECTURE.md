# Architecture

## Component overview

```
┌─────────────┐        HTTP/JSON        ┌──────────────┐
│  apps/web   │ ──────────────────────▶ │  apps/api    │
│  Next.js    │ ◀────────────────────── │  FastAPI     │
└─────────────┘                         └──────┬───────┘
                                                │ SQLAlchemy
                                                ▼
                                         ┌──────────────┐
                                         │  PostgreSQL  │
                                         └──────────────┘
                                                ▲
                             ┌──────────────────┼──────────────────┐
                             │                  │                  │
                      ┌──────┴──────┐   ┌───────┴──────┐   ┌───────┴──────┐
                      │   Alpaca    │   │  Anthropic   │   │ (future: a   │
                      │  (market    │   │  (LLM        │   │   2nd data   │
                      │   data +    │   │  synthesis   │   │  or broker   │
                      │   paper     │   │  only, never │   │  vendor)     │
                      │   broker)   │   │  ground      │   │              │
                      │             │   │  truth)      │   │              │
                      └─────────────┘   └──────────────┘   └──────────────┘
```

`apps/web` never talks to Alpaca/Anthropic/Postgres directly — everything
goes through `apps/api`, which is the only place secrets are held
(server-side only, principle: never expose the Anthropic key client-side).

## The fact → calc → inference → decision pipeline (principle 2)

Every number the UI shows traces back through exactly one of these stages,
and the stage is never blurred:

1. **Observed facts** — raw data from a source of record (Alpaca price bars,
   Alpaca order fills). Always tagged with source, symbol, timestamp,
   timezone, and freshness status (principle 3). Never fabricated (principle
   4) — a missing bar is represented as missing, not interpolated silently.
2. **Deterministic calculations** — indicators, portfolio valuation, risk
   metrics, performance metrics. Plain Python functions, unit-tested,
   versioned. No LLM involvement (principle 6).
3. **Model inferences** — LLM-generated synthesis, scenario framing,
   explanations, and structured evidence comparison. Grounded only in tool
   results the model was given; the model never invents a price or a date
   (principle 4/7). Confidence is not the model's self-reported number —
   it's calibrated from historical outcomes over time (principle 15,
   docs/MODEL_GOVERNANCE.md).
4. **User decisions** — what the user actually did (approved a
   recommendation, placed a paper order, overrode a suggestion). Recorded,
   never inferred.

Every stage's output that feeds a later stage is captured in the audit trail
(principle 9) — see docs/DATA_DICTIONARY.md's `AuditEvent`.

## Provider abstraction pattern

`apps/api/src/tradingos_api/providers/` defines three `Protocol` interfaces —
`MarketDataProvider`, `PaperBrokerProvider`, `LLMProvider` — with **no
concrete implementation in Phase 1**. This is deliberate:

- Callers (routers/services, built in later phases) depend on the interface,
  not on Alpaca or Anthropic directly — a provider swap or a second vendor
  doesn't require touching call sites.
- Tests can inject a fake/synthetic implementation instead of hitting a real,
  paid API — the default test suite never requires `ANTHROPIC_API_KEY` or
  Alpaca credentials to pass.
- `LLMProvider` in particular exists to make the "tool-use, not text-to-SQL"
  pattern (docs/MODEL_GOVERNANCE.md) structurally impossible to bypass: the
  interface's return type carries typed tool calls, not raw strings the
  caller would need to parse as SQL.

## Monorepo layout

```
TradingOS/
  apps/
    web/     Next.js 16 (App Router), TypeScript, Tailwind, TanStack Query,
             lightweight-charts. apps/web/README-equivalent: see USER_GUIDE.md.
    api/     FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2. uv-managed.
             src/tradingos_api/
               core/       settings (pydantic-settings)
               db/         engine/session, declarative Base
               providers/  Protocol interfaces (this phase); concrete
                           implementations land in Phase 2+
               models/      empty — Phase 2+ SQLAlchemy models
               schemas/     empty — Phase 2+ Pydantic request/response schemas
               routers/     FastAPI routers (health.py only so far)
               services/    empty — Phase 2+ business logic
  infra/
    docker-compose.yml   Postgres 16 (documented alternative to the native
                          install this dev machine actually uses — ADR-008)
  docs/      all required project documents (this file included)
```

## Why no domain schema yet

Phase 1 intentionally ships Alembic wired up (env.py reads `Base.metadata`
and the app's `Settings.database_url`) but with **zero domain tables**. The
first real migration lands in Phase 2, once `Symbol` and `PriceBar` models
exist to generate it from — writing migrations against tables that don't
serve any code yet would be schema speculation, which the engineering rules
explicitly warn against (no half-finished implementations, no designing for
hypothetical future requirements beyond what's needed now).
