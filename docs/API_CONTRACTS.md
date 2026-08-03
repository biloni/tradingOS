# API Contracts

Versioning convention for future endpoints: `/api/v1/...`. The only endpoint
that exists as of Phase 1 predates that convention (see note below) and will
be the one exception.

## `GET /health`

No auth (single-user system, ADR-007). No query params.

**Response `200`**
```json
{
  "status": "ok",
  "time_utc": "2026-08-03T13:41:00.416286+00:00"
}
```

Used by `apps/web`'s home page to show a live API-reachability indicator
(see `lib/api-client.ts`, `app/page.tsx`).

**Note on versioning:** `/health` is intentionally unversioned — health
checks are an infrastructure concern, not a product API surface, and
conventionally live outside a version prefix (matches common practice for
load balancer / uptime-check endpoints). Every endpoint added from Phase 2
onward uses `/api/v1/...`.

## Phase 2+ (not yet implemented)

This section will grow with each phase. Planned surface, for forward
reference only (none of this exists yet, no schemas defined):

- `GET /api/v1/symbols` — list tradable universe
- `GET /api/v1/symbols/{ticker}/bars` — price history
- `POST /api/v1/recommendations/query` — the tool-use NL query entrypoint
  (Phase 4)
- `POST /api/v1/paper-orders` — submit a paper order (Phase 3)
- `GET /api/v1/portfolio` — current paper portfolio snapshot (Phase 3)
- `POST /api/v1/backtests` — run a backtest (Phase 5)
