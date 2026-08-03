# Provider Matrix

## Market data + paper brokerage

| Provider | Role | Cost (free tier) | Notes | Status |
|---|---|---|---|---|
| **Alpaca Markets** | Market data (IEX feed) + paper brokerage | Free, unlimited paper trading; IEX data is real-time-ish but exchange-limited (SIP/full-market real-time is a paid add-on) | One account covers both roles; well-documented REST + websocket API; ToS permits programmatic access (licensed API, principle 12) | **Chosen** (ADR-002) |
| Polygon.io | Market data only | Free tier is end-of-day/delayed; real-time is paid | Higher-quality data, but no paper brokerage — would need an in-house paper ledger | Documented fallback, not adopted |
| IEX Cloud | Market data | — | Service was shut down in 2024 | Not viable |
| Twelve Data | Market data | Free tier available, rate-limited | Not brokerage-capable | Not adopted |
| yfinance (unofficial Yahoo Finance) | Market data | Free | Scrapes an endpoint Yahoo's ToS restricts for automated/commercial use | **Rejected** — violates principle 12 |

## LLM

| Provider | Role | Notes | Status |
|---|---|---|---|
| **Anthropic (Claude, `claude-sonnet-*`)** | Synthesis, explanation, scenario analysis, tool-use | Matches the development environment (Claude Code); provider-neutral `LLMProvider` interface means a swap wouldn't require rewriting callers | **Chosen** |

## Deferred / not needed yet

| Candidate | Why deferred |
|---|---|
| Redis | No caching/queueing use case exists yet (ADR-006) — revisit at Phase 2 if a background ingestion job needs one |
| A second market-data vendor for redundancy | Single-vendor is acceptable for a personal MVP; revisit if Alpaca rate limits or an outage becomes a real problem |

## Cost tracking

Every LLM call is logged with token counts and cost
(`LLMCallLog`, docs/DATA_DICTIONARY.md) starting in Phase 4, when the first
LLM call is made. No LLM calls exist in Phase 1.
