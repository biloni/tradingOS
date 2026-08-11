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

**Current status:** the shipped app (Phases 1–7) is complete and unchanged.
A **product & architecture refinement pass** (2026-08-03, planning only —
no code changed) has since defined a much larger scope: a symbol-validated,
tiered watchlist; an 8-role investment committee (Bull/Bear/Technical/
Fundamental/Macro/Risk Manager/Portfolio Manager/CIO) sitting behind
deterministic risk gates; regime/VIX-aware sizing; a broker-agnostic trade
journal; an active trade monitor; and recommendation-vs-reality tracking.
See [docs/MVP_PLAN.md](docs/MVP_PLAN.md) for scope,
[docs/BLOCKING_DECISIONS.md](docs/BLOCKING_DECISIONS.md) for the open
decisions awaiting your confirmation before any of it is built, and
[docs/STATUS.md](docs/STATUS.md) for the full picture.

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
    `docker compose -f infra/docker-compose.yml up -d postgres` (reads
    `POSTGRES_PASSWORD` from your shell env)

Or skip all three prerequisites and run the whole stack in containers —
`docker compose -f infra/docker-compose.yml --env-file infra/.env up --build`
(copy `infra/.env.example` to `infra/.env` first) brings up Postgres,
runs migrations, then starts both the API and web app. See
[docs/OPERATIONS.md](docs/OPERATIONS.md#containers-revision-prompt-16-task-dockerfiles--docker-compose--deployment-docs)
for the full details, including one build-time-vs-runtime env var gotcha.

### 1. API

```bash
cd apps/api
cp .env.example .env   # then fill in DATABASE_URL with your real password
uv sync
uv run uvicorn tradingos_api.main:app --reload
```
Runs on http://localhost:8000. Check `GET /health`.

Every route except `/health` and `/api/v1/auth/*` requires a logged-in
session ([ADR-066](docs/DECISIONS.md)). Set the one app password once,
after seeding:
```bash
uv run python -m tradingos_api.scripts.set_password <your-choice>
```
There is no self-service registration/reset endpoint by design — this
CLI script, run with local machine access, is the only way to set it.

### 2. Web

```bash
cd apps/web
cp .env.local.example .env.local   # defaults are fine for local dev
pnpm install
pnpm dev
```
Runs on http://localhost:3000 — redirects to `/login` until you sign in
with the password set above.

### Running checks

`mypy` is scoped to `src/` only, not `.` — `tests/` has known, pre-existing
strict-mode errors from minimal fake test doubles that deliberately
implement only part of a Protocol (`_FixedQuote`, `_FakePositionsBroker`,
etc.); not yet triaged (a real gap, flagged for follow-up, not swept
under the rug).

```bash
# apps/api
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest -v

# apps/web
pnpm lint && pnpm typecheck && pnpm test

# apps/web e2e (Playwright) — requires both servers above already running
pnpm test:e2e
```

## Documentation index

| Doc | What's in it |
|---|---|
| [PROJECT_INSTRUCTIONS.md](PROJECT_INSTRUCTIONS.md) | The governing brief for this whole project — read this first |
| [docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md) | Mission, MVP scope, explicit out-of-scope list, phase roadmap |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component diagram, fact/calc/inference/decision pipeline, provider abstraction pattern |
| [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | Every entity in the data model, and which phase implements it |
| [docs/ER_DIAGRAM.md](docs/ER_DIAGRAM.md) | Mermaid ER diagrams — a context map plus one detailed diagram per bounded context |
| [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md) | Endpoint contracts |
| [docs/SECURITY.md](docs/SECURITY.md) | Secrets handling, least privilege, authn/authz posture |
| [docs/PROVIDER_MATRIX.md](docs/PROVIDER_MATRIX.md) | Vendor choices and alternatives considered |
| [docs/DECISIONS.md](docs/DECISIONS.md) | ADR log |
| [docs/TASKS.md](docs/TASKS.md) | Phase-by-phase checklist |
| [docs/STATUS.md](docs/STATUS.md) | Current phase, what's done, what's next |
| [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md) | Test pyramid, fixtures-not-live-APIs policy |
| [docs/TEST_EVIDENCE.md](docs/TEST_EVIDENCE.md) | Exact commands run + results, per phase |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Local dev ops, runbooks |
| [docs/RELEASE_GATE_PROOFS.md](docs/RELEASE_GATE_PROOFS.md) | Provenance, risk/invalidation, audit trail, and morning-plan deadline proven against real code and tests, ahead of tagging paper beta |
| [docs/MODEL_GOVERNANCE.md](docs/MODEL_GOVERNANCE.md) | LLM guardrails, confidence calibration policy, strategy-change approval gate |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | How to use the app (grows each phase) |
| [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) | Pinned versions, verified against live registries |
| [docs/MVP_PLAN.md](docs/MVP_PLAN.md) | *(Refinement, planning only)* MVP / Phase 2 / Future scope split for the refined product |
| [docs/UX_MAP.md](docs/UX_MAP.md) | *(Refinement, planning only)* Pages, navigation, key actions, empty/error/stale states |
| [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) | *(Refinement, planning only)* STRIDE-style walk of the refinement's new trust boundaries |
| [docs/RISK_REGISTER.md](docs/RISK_REGISTER.md) | *(Refinement, planning only)* Product/technical/vendor/regulatory risks, likelihood/impact/mitigation |
| [docs/BLOCKING_DECISIONS.md](docs/BLOCKING_DECISIONS.md) | *(Refinement, planning only)* 10 open decisions with recommended defaults — nothing here is acted on without your confirmation |

## Known limitations (as of Revision Prompt 16, paper beta)

- **The refined product described in docs/PRODUCT_REQUIREMENTS.md,
  docs/ARCHITECTURE.md, docs/MVP_PLAN.md, docs/UX_MAP.md,
  docs/THREAT_MODEL.md, and docs/RISK_REGISTER.md was a planning artifact
  only as of Phase 7 — it has since been built.** The 8-role investment
  committee, regime/VIX-aware sizing, the broker-agnostic trade journal,
  the active-position monitor, the order-authority governance chain
  (propose → policy-evaluation → approval → submit), a real always-on
  scheduler, and real password-gated authentication (below) all exist
  today, each with its own test coverage — see
  [docs/STATUS.md](docs/STATUS.md) for the current phase-by-phase
  picture and [docs/RELEASE_GATE_PROOFS.md](docs/RELEASE_GATE_PROOFS.md)
  for what's specifically been proven ahead of tagging this paper beta.
  What's still genuinely not built: any **live** (real-money) broker
  execution capability — see the next bullet — and the items below it.
- No live-order capability exists anywhere in the codebase, by design
  (principle 10) — this isn't a flag waiting to be flipped, it doesn't
  exist. "Revision Prompt 17" (limited live-confirmed broker execution)
  is deliberately not started; it requires this paper-beta release to be
  complete, stable, and explicitly approved to begin first.
- No SMA/indicator overlay line on the symbol-detail candlestick chart —
  the real indicators endpoint only returns a single day's snapshot, not
  a ranged series; a text readout is shown instead
  ([docs/USER_GUIDE.md](docs/USER_GUIDE.md)).
- Single-user, password-gated ([ADR-066](docs/DECISIONS.md)) — real
  login/session/step-up-reauth exist (Revision Prompt 16), but there is
  no multi-user support and no self-service registration; the one
  password is set via a local CLI script, by design.
- The operator-configured baseline order-authority mode
  (`Settings.operating_mode`) is only enforced by the frontend choosing
  a matching value today — not yet cross-checked server-side in the
  actual proposal-evaluation/submit endpoints (the kill switch itself
  *is* correctly, independently enforced). Documented in detail in
  [docs/RELEASE_GATE_PROOFS.md](docs/RELEASE_GATE_PROOFS.md) §2, with a
  follow-up filed; practical risk is low today (single-user app, one
  real caller).
- Docker Compose can now run the whole stack (Postgres + API + web,
  `infra/docker-compose.yml`) but isn't the primary path on the current
  dev machine ([ADR-008](docs/DECISIONS.md)), and the Dockerfiles/compose
  file haven't been build-verified here — this machine doesn't have
  Docker installed (see docs/OPERATIONS.md's "Containers" section).
- No historical-outcome-based confidence calibration yet — still needs a
  real sample of completed trades post-activation before any confidence
  number is framed as a probability
  ([docs/MODEL_GOVERNANCE.md](docs/MODEL_GOVERNANCE.md)).
- No historical index-constituent/delisting reconstruction — backtests use
  every known symbol regardless of today's `active` flag, but this is a
  fixed 30-name watchlist, not an index replication ([ADR-025](docs/DECISIONS.md)).
- No autonomous strategy-proposal system — candidates are user/operator-
  submitted ([ADR-026](docs/DECISIONS.md)); the review gate itself is
  fully built and doesn't depend on what originates a candidate.
- `/api/v1/ask` is stateless per request — no persisted multi-turn
  conversation history yet ([ADR-019](docs/DECISIONS.md)).
- Only one Playwright e2e journey exists (the paper-order flow,
  [ADR-030](docs/DECISIONS.md)) — not a full end-to-end suite across
  every page.
