# Architecture Decision Records

Format: each ADR is Context / Decision / Alternatives considered / Consequences.
ADRs are append-only — superseding a decision means adding a new ADR that
references the old one, not editing history.

## ADR-001: Monorepo layout — `apps/web` (Next.js) + `apps/api` (FastAPI)

**Context.** PROJECT_INSTRUCTIONS.md specifies Next.js/TypeScript for the web
tier and Python/FastAPI for the API tier, in a single repo unless a compelling
reason exists not to.

**Decision.** One repo, `apps/web` and `apps/api` as independent, separately
tooled projects (`pnpm` workspace for web, `uv` project for api), plus a
shared `docs/` and `infra/` at the root. No shared code package between them
in Phase 1 — nothing to share yet.

**Alternatives considered.** Two separate repos (rejected: adds deploy/version
coordination overhead for a single-person project with no team boundary to
justify it).

**Consequences.** Two toolchains to run locally (`uv run ...`, `pnpm ...`).
Documented clearly in README.md quickstart.

---

## ADR-002: Market data + paper-trading vendor — Alpaca Markets

**Context.** The app needs (a) OHLCV price history and quotes for US equities
and ETFs, and (b) a paper-trading brokerage account to place and track
simulated orders. This is a vendor and recurring-cost decision, confirmed with
the user directly (not defaulted silently), per the project's working method.

**Decision.** Alpaca Markets for both roles. Free tier covers paper trading
(unlimited, no cost) and market data via the IEX feed (real-time bars are a
paid add-on; free tier is suitable for a 2–10 day swing-trade horizon, not
intraday/day-trading).

**Alternatives considered.**
- *Polygon.io* — better data quality/latency, but no built-in paper brokerage;
  would require building the paper ledger fully in-house. Kept as a documented
  fallback in docs/PROVIDER_MATRIX.md if Alpaca's data license terms or rate
  limits become limiting.
- *IEX Cloud* — shut down in 2024; not viable.
- *yfinance / scraping Yahoo Finance* — rejected outright: violates principle
  12 (no scraping of prohibited sources; Yahoo's ToS restricts automated
  access).

**Consequences.** `MarketDataProvider` and `PaperBrokerProvider` interfaces
(apps/api/src/tradingos_api/providers/) are defined against Alpaca's data
shape conceptually, but remain Protocol-typed so a second provider could be
added later without touching callers. No Alpaca API calls exist yet — the
concrete client lands in Phase 2 (data) / Phase 3 (portfolio).

---

## ADR-003: Market universe — US equities + ETFs only for MVP

**Context.** Confirmed with the user directly. Options and crypto would add a
materially more complex data model (strikes/expirations/greeks, 24/7 market
hours) with no confirmed need for the MVP's swing-trading use case.

**Decision.** US-listed equities and ETFs only. `Symbol.assetType` is
constrained to `EQUITY | ETF` (see docs/DATA_DICTIONARY.md).

**Alternatives considered.** Equities + ETFs + options (rejected for MVP,
revisit once the core loop — ingestion → scoring → paper trade → review — is
proven on the simpler asset types).

**Consequences.** Corporate-actions handling (splits/dividends) only needs to
account for equity/ETF cases, not options-specific adjustments.

---

## ADR-004: Chart library — `lightweight-charts` over Recharts

**Context.** The brief's default technical direction names "a reliable
charting library" without pinning one. Swing-trade decision support needs
candlestick/OHLC charts with volume overlays, which Recharts (a general
category/line/bar charting library) does not render well.

**Decision.** `lightweight-charts` (TradingView's open-source canvas charting
library, MIT-licensed) for price/candlestick charts. Recharts (or an
equivalent) may still be used later for generic dashboards/analytics charts
(e.g., a P&L line chart) if a general-purpose need arises — this ADR only
scopes the *price chart* decision.

**Alternatives considered.** Recharts for everything (rejected: no native
candlestick support). D3 directly (rejected: far more implementation effort
for no benefit over a purpose-built financial charting library).

**Consequences.** One more frontend dependency, but a domain-appropriate one.

---

## ADR-005: Python tooling — `uv` + `ruff` + `mypy`; TS tooling — `pnpm` + ESLint + `tsc`

**Context.** PROJECT_INSTRUCTIONS.md specifies `pnpm` for TypeScript and `uv`
for Python "unless current stable tooling suggests a better documented
choice." No better-documented alternative was found.

**Decision.** `uv` for Python dependency/venv/version management, `ruff` for
both linting and formatting (replacing the separate black+isort+flake8
stack), `mypy --strict` for type checking. `pnpm` for TS, ESLint
(`eslint-config-next`) + `tsc --noEmit` for type checking.

**Consequences.** Single fast tool (`ruff`) covers what used to be 2–3 tools
on the Python side.

---

## ADR-006: Redis and Playwright deferred, not adopted, for Phase 1

**Context.** PROJECT_INSTRUCTIONS.md explicitly says "Redis only when a
demonstrated use case requires it," and the default technical direction lists
Playwright end-to-end tests as part of the testing stack.

**Decision.** Neither is installed in Phase 1. Phase 1 has no caching/queueing
need (no background jobs exist yet) and no real user journey beyond a health
check page (a Playwright e2e test of "does the health page load" would just
duplicate what the Vitest smoke test already covers).

**Consequences.** Revisit Redis when a background job (e.g., scheduled market
data ingestion) is designed in Phase 2. Revisit Playwright once a real
multi-step user journey exists (e.g., Phase 3's paper-order flow or Phase 4's
BP-style... — n/a for TradingOS, see Phase 4 scoring review flow).

---

## ADR-007: No auth/multi-tenancy in MVP

**Context.** This is a personal, single-user system per the mission statement
— there is no second user to isolate.

**Decision.** No authentication, no user table, no row-level security in the
MVP. `docs/SECURITY.md` documents this explicitly as a scoped-out concern
rather than an oversight.

**Consequences.** If the app were ever shared with another person, this would
need to be revisited before doing so — noted in README "known limitations."

---

## ADR-008: Local Postgres via native Windows install (winget) rather than Docker Desktop

**Context.** The default technical direction calls for Docker Compose "plus
non-container commands where practical." This dev machine had neither Docker
nor Postgres installed. Installing Docker Desktop on Windows typically
requires enabling WSL2/Hyper-V, which is a system-settings change outside
what an assistant should perform autonomously.

**Decision.** Installed PostgreSQL 16 natively via `winget install
PostgreSQL.PostgreSQL.16` — a standard application installer, no
virtualization features touched. `infra/docker-compose.yml` still exists and
is documented for other machines / a future CI environment, but the native
install is the primary path for this developer's local setup.

**Consequences.** README documents both paths. A dedicated least-privilege
role (`tradingos_app`) and database (`tradingos`) were created rather than
using the `postgres` superuser at runtime.
