# TradingOS

A trustworthy, explainable decision-support application for a retail
investor doing swing trading (2–10 trading-day holding periods). It
identifies and monitors candidate trades, manages a configurable paper
portfolio (starting at $10,000), tracks trades the user actually places, and
improves recommendations through evidence-based review.

**This is not a chatbot, not a guaranteed-profit system, and not an
unreviewed autonomous trading bot.** See [PROJECT_INSTRUCTIONS.md](PROJECT_INSTRUCTIONS.md)
for the full set of non-negotiable product principles, and
[docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md) for MVP scope.

**Current status:** Phase 4 (Scoring Engine & LLM Synthesis) — see
[docs/STATUS.md](docs/STATUS.md).

## Stack

- **Web:** Next.js 16 (App Router, TypeScript), Tailwind CSS, TanStack Query,
  `lightweight-charts`
- **API:** FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic (uv-managed)
- **Database:** PostgreSQL 16
- **Market data + paper brokerage:** Alpaca Markets ([ADR-002](docs/DECISIONS.md))
- **LLM:** Anthropic Claude, tool-use pattern only — never raw SQL, never the
  source of numeric ground truth

Exact pinned versions: [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).

## Quickstart (local dev)

### Prerequisites

- Node.js, `pnpm` (`npm install -g pnpm` if you don't have it)
- Python 3.12+, `uv` (`pip install uv` if you don't have it)
- PostgreSQL 16, running locally — either:
  - **Native (what this project's dev machine uses — [ADR-008](docs/DECISIONS.md)):**
    `winget install PostgreSQL.PostgreSQL.16`, then create the app role/db:
    ```sql
    CREATE ROLE tradingos_app WITH LOGIN PASSWORD '<your-choice>';
    CREATE DATABASE tradingos OWNER tradingos_app;
    ```
  - **Docker (documented alternative, other machines/CI):**
    `docker compose -f infra/docker-compose.yml up -d` (reads
    `POSTGRES_PASSWORD` from your shell env)

### 1. API

```bash
cd apps/api
cp .env.example .env   # then fill in DATABASE_URL with your real password
uv sync
uv run uvicorn tradingos_api.main:app --reload
```
Runs on http://localhost:8000. Check `GET /health`.

### 2. Web

```bash
cd apps/web
cp .env.local.example .env.local   # defaults are fine for local dev
pnpm install
pnpm dev
```
Runs on http://localhost:3000.

### Running checks

```bash
# apps/api
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v

# apps/web
pnpm lint && pnpm typecheck && pnpm test
```

## Documentation index

| Doc | What's in it |
|---|---|
| [PROJECT_INSTRUCTIONS.md](PROJECT_INSTRUCTIONS.md) | The governing brief for this whole project — read this first |
| [docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md) | Mission, MVP scope, explicit out-of-scope list, phase roadmap |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component diagram, fact/calc/inference/decision pipeline, provider abstraction pattern |
| [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | Every entity in the data model, and which phase implements it |
| [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md) | Endpoint contracts |
| [docs/SECURITY.md](docs/SECURITY.md) | Secrets handling, least privilege, authn/authz posture |
| [docs/PROVIDER_MATRIX.md](docs/PROVIDER_MATRIX.md) | Vendor choices and alternatives considered |
| [docs/DECISIONS.md](docs/DECISIONS.md) | ADR log |
| [docs/TASKS.md](docs/TASKS.md) | Phase-by-phase checklist |
| [docs/STATUS.md](docs/STATUS.md) | Current phase, what's done, what's next |
| [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md) | Test pyramid, fixtures-not-live-APIs policy |
| [docs/TEST_EVIDENCE.md](docs/TEST_EVIDENCE.md) | Exact commands run + results, per phase |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Local dev ops, runbooks |
| [docs/MODEL_GOVERNANCE.md](docs/MODEL_GOVERNANCE.md) | LLM guardrails, confidence calibration policy, strategy-change approval gate |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | How to use the app (grows each phase) |
| [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) | Pinned versions, verified against live registries |

## Known limitations (as of Phase 4)

- No UI yet — every feature through Phase 4 (ingestion, indicators, paper
  trading, scoring, NL query) is API-only; the Next.js frontend is
  scaffolding pending Phase 7.
- No live-order capability exists anywhere in the codebase, by design
  (principle 10) — this isn't a flag waiting to be flipped, it doesn't exist.
- No auth/multi-user support ([ADR-007](docs/DECISIONS.md)) — single-user
  personal tool.
- Docker Compose path for Postgres is documented but not the primary path on
  the current dev machine ([ADR-008](docs/DECISIONS.md)).
- No historical-outcome-based confidence calibration yet — needs completed
  trade history from backtesting (Phase 5) before any confidence number is
  framed as a probability ([docs/MODEL_GOVERNANCE.md](docs/MODEL_GOVERNANCE.md)).
- `/api/v1/ask` is stateless per request — no persisted multi-turn
  conversation history yet ([ADR-019](docs/DECISIONS.md)).
