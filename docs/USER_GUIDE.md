# User Guide

_This guide grows with each phase. As of Phase 1, there is no trading feature
to use yet — only a local dev environment to run._

## Running it locally

See README.md "Quickstart" for the exact commands. Once both servers are
running:

- Open http://localhost:3000 — you'll see the TradingOS home page with an
  API status card. It reads "API status: ok (as of <timestamp>)" when the
  API is reachable, or an error message if it isn't.
- The API itself is at http://localhost:8000 — `GET /health` returns a JSON
  status payload (see docs/API_CONTRACTS.md).

## What's not here yet

No trades, no recommendations, no portfolio view, no charts, no NL query
chat — those ship in Phases 2 through 7 (see docs/TASKS.md). This page will
be rewritten section-by-section as each of those lands, with real
screenshots and walkthroughs of the actual features, not placeholders.
