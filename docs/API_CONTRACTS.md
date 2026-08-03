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

## `GET /api/v1/symbols`

No query params. Returns every seeded symbol.

**Response `200`**
```json
[
  {"id": 1, "ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "asset_type": "EQUITY", "active": true}
]
```

## `GET /api/v1/symbols/{ticker}/bars`

**Query params:** `start` (date, optional, default: `end - 90 days`), `end`
(date, optional, default: today). Returns the latest (max-`fetched_at`)
`PriceBar` row per date in range — see `services/price_bars.py`.

**Response `200`** — money fields are strings (`Numeric(18,6)`, full stored
precision — never a JSON float; see docs/SECURITY.md / engineering rules on
currency):
```json
[
  {
    "as_of": "2026-07-31",
    "open": "304.810000", "high": "310.690000", "low": "300.000000", "close": "308.910000",
    "volume": 132756799,
    "source": "alpaca", "adjustment": "split",
    "fetched_at": "2026-08-03T07:23:39.309827-07:00"
  }
]
```

**Response `404`** if `ticker` isn't in the seeded `Symbol` table.

## `GET /api/v1/symbols/{ticker}/indicators`

**Query params:** `as_of` (date, optional — defaults to the most recent date
that has any indicator row for this symbol). Returns every indicator value
computed for that one date (up to 12 rows — one per `IndicatorName`).

**Response `200`**
```json
[
  {"as_of": "2026-07-31", "indicator_name": "RSI_14", "version": "v1", "value": "43.243931", "computed_at": "2026-08-03T07:23:39.485828-07:00"}
]
```

**Response `404`** if `ticker` isn't in the seeded `Symbol` table. Returns
`[]` (not 404) if the symbol exists but has no indicators computed yet for
the requested/default date.

## Phase 3+ (not yet implemented)

This section will grow with each phase. Planned surface, for forward
reference only (none of this exists yet, no schemas defined):

- `POST /api/v1/recommendations/query` — the tool-use NL query entrypoint
  (Phase 4)
- `POST /api/v1/paper-orders` — submit a paper order (Phase 3)
- `GET /api/v1/portfolio` — current paper portfolio snapshot (Phase 3)
- `POST /api/v1/backtests` — run a backtest (Phase 5)
