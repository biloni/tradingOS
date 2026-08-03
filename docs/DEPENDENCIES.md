# Dependencies

Every version below was verified against the live PyPI/npm registry (via
`pip index versions <pkg>` / `npm view <pkg> version`) on 2026-08-03, at the
time this phase was implemented — not guessed or carried over from training
data. Re-verify before bumping.

## `apps/api` (Python, uv-managed, `requires-python = ">=3.12"`, running on
CPython 3.14.6 locally)

| Package | Version | Role |
|---|---|---|
| fastapi | 0.141.1 | Web framework |
| uvicorn[standard] | 0.52.1 | ASGI server |
| pydantic | 2.13.4 | Data validation |
| pydantic-settings | 2.14.2 | Env-based config (`Settings`) |
| sqlalchemy | 2.0.51 | ORM / engine |
| alembic | 1.18.5 | Migrations |
| psycopg[binary] | 3.3.4 | Postgres driver (v3) |
| alpaca-py | 0.43.5 (verified again 2026-08-03, Phase 2; still current, Phase 3) | Official Alpaca SDK (ADR-009) — Phase 2 used `alpaca.data` (market data), Phase 3 added `alpaca.trading` (paper broker) from the same package, no new dependency. Pulls in `pandas`, `numpy`, `websockets`, `requests`, `msgpack`, `sseclient-py` as transitive deps |
| anthropic | 0.120.2 | Official Anthropic Python SDK (ADR-017) — `AnthropicLLMProvider`'s tool-use `messages.create()` calls, model `claude-sonnet-5` |

Dev-only:

| Package | Version | Role |
|---|---|---|
| pytest | 9.1.1 | Test runner |
| httpx2 | 2.9.1 | HTTP client for FastAPI `TestClient` (successor to `httpx`, which Starlette's `TestClient` now flags deprecated in favor of `httpx2`) |
| ruff | 0.16.1 | Lint + format |
| mypy | 2.3.0 | Type checking (`--strict`) |

## `apps/web` (TypeScript, pnpm-managed)

| Package | Version | Role |
|---|---|---|
| next | 16.2.12 | Framework (App Router) |
| react / react-dom | 19.2.4 | UI runtime |
| @tanstack/react-query | 5.101.4 | Server-state/data-fetching (installed, not yet wired to real endpoints beyond `/health`) |
| lightweight-charts | 5.2.0 | Candlestick/price charting (ADR-004) — installed, not yet used (no chart UI until Phase 2+ has data) |

Dev-only:

| Package | Version | Role |
|---|---|---|
| typescript | ^5 (5.9.3 installed; 7.0.2 exists on npm but was not adopted this phase — see note below) | Type checking |
| tailwindcss | ^4 (4.3.3) | Styling |
| eslint / eslint-config-next | ^9 (9.39.5) / 16.2.12 | Linting |
| vitest | 4.1.10 | Test runner |
| @testing-library/react | 16.3.2 | Component testing |
| @testing-library/jest-dom | ^7.0.0 | DOM matchers |
| @vitejs/plugin-react | ^6.0.5 | Vitest/Vite React support |
| jsdom | ^30.0.1 | DOM environment for Vitest |

**Note on TypeScript 7:** npm reports `typescript@7.0.2` as latest (the
native-Go-ported compiler line). `create-next-app@16.2.12` pinned `^5`
itself and the scaffold was left as generated rather than force-upgrading a
major version the framework's own template didn't request — revisit when
`eslint-config-next`/Next.js itself moves to requiring TS 7.

## Infra

| Tool | Version | Role |
|---|---|---|
| PostgreSQL | 16.14 (native Windows install via winget `PostgreSQL.PostgreSQL.16`) | Database — ADR-008 |
| postgres (Docker image, documented alternative) | `postgres:16` | Matches the native major version |

## Tooling versions on the dev machine (not project dependencies, but
relevant to reproducing this setup)

| Tool | Version |
|---|---|
| Node.js | v26.5.1 |
| npm | 11.17.0 |
| pnpm | 11.18.0 (installed via `npm install -g pnpm`) |
| Python | 3.14.6 |
| uv | 0.12.1 (installed via `pip install uv`) |
