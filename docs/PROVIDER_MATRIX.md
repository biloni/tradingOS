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
| **Anthropic (Claude, `claude-sonnet-5`)** | Synthesis, explanation, scenario analysis, tool-use | Matches the development environment (Claude Code); provider-neutral `LLMProvider` interface means a swap wouldn't require rewriting callers; model verified current via the `claude-api` skill at implementation time (ADR-017) | **Chosen, implemented Phase 4** |

## Deferred / not needed yet

| Candidate | Why deferred |
|---|---|
| Redis | No caching/queueing use case exists yet (ADR-006) — revisit at Phase 2 if a background ingestion job needs one |
| A second market-data vendor for redundancy | Single-vendor is acceptable for a personal MVP; revisit if Alpaca rate limits or an outage becomes a real problem |

## Cost tracking

**Implemented, Phase 4.** Every LLM call is logged with token counts and
cost (`LLMCallLog`, docs/DATA_DICTIONARY.md), written once per Anthropic API
call by `services/ask.py`'s orchestration loop.

---

## Refinement: new evidence providers (candidates only — none selected)

**No provider below has been chosen or contracted.** This section exists to
support docs/BLOCKING_DECISIONS.md #1 and #2, which are open questions for
you to confirm. Per PROJECT_INSTRUCTIONS.md, no paid tier is adopted without
your explicit approval. Exact current pricing/rate limits for every
candidate below must be re-verified against the vendor's own live
documentation at implementation time (the same discipline ADR-017 already
applies to Anthropic model pricing) — the notes below describe each
vendor's general free-tier shape from public knowledge, not a verified
snapshot, and should not be treated as a quote.

### Fundamentals + earnings calendar (BLOCKING_DECISIONS.md #1)

| Provider | Free-tier shape (verify before use) | Notes | Status |
|---|---|---|---|
| **Financial Modeling Prep** | Free tier historically includes basic fundamentals, ratios, and an earnings-calendar endpoint, rate-limited per day | Broad single-vendor coverage (fundamentals + earnings in one API) — simplest integration if the free tier's rate limit proves sufficient for 48 symbols on a daily/weekly refresh cadence | Candidate, recommended default (BLOCKING_DECISIONS.md #1) |
| **Finnhub** | Free tier historically includes company profile/fundamentals, earnings calendar, and basic company news, rate-limited per minute | Also covers the news-headline need in one vendor; per-minute (not per-day) limiting may fit a scheduled-job usage pattern better than a per-day cap | Candidate, viable alternative |
| A paid fundamentals/sentiment vendor (e.g. a licensed news-sentiment API) | Real cost, better coverage/reliability | Deferred to Phase 2 (docs/MVP_PLAN.md) — only pursued with your explicit sign-off on the specific vendor and price | Deferred, not adopted |

### News headlines (MVP)

| Provider | Notes | Status |
|---|---|---|
| **Alpaca's existing news endpoint** | Already covered by the existing Alpaca account/credentials — zero new vendor, zero new cost, zero new secret. Headlines only, no sentiment score. | **Recommended default for MVP** |
| Finnhub / FMP news endpoint (if that vendor is chosen for fundamentals anyway) | Could consolidate to one fewer vendor if its news coverage is adequate | Candidate, revisit once #1 is decided |

### Sentiment scoring (Phase 2, not MVP)

Explicitly deferred (docs/MVP_PLAN.md) — MVP's committee reads raw
headlines as evidence rather than a pre-computed sentiment score.
Candidates to evaluate when this is picked back up: a dedicated
news-sentiment API, or an LLM-computed sentiment pass over headlines
(which would itself need to stay clearly labeled as a model inference, not
a fact, per principle 2/4 — sentiment-from-headlines is qualitatively
different from a vendor-supplied sentiment *score* and that distinction
should survive into whatever gets built).

### VIX / macro-regime data (BLOCKING_DECISIONS.md #2)

| Provider | Notes | Status |
|---|---|---|
| **VIXY / VIXM via the existing Alpaca `MarketDataProvider`** | Zero new vendor. ETP-tracks VIX futures, not the spot CBOE index tick-for-tick — a documented approximation, adequate for level/percentile/rate-of-change classification at a daily cadence | **Recommended default** |
| A dedicated CBOE/macro data feed for exact spot VIX + real term structure | Real cost; needed only if the ETP proxy's accuracy turns out to matter for precise percentile/term-structure math | Deferred, not adopted |

### Symbol reference/validation (BLOCKING_DECISIONS.md #7)

| Provider | Notes | Status |
|---|---|---|
| **Alpaca's asset reference endpoint** (`GET /v2/assets`) | Already the incumbent, already licensed; answers exactly the question that matters ("could this system ever place a paper/live order against this ticker") | **Recommended default** |
| A dedicated securities-reference/master-data vendor | Broader coverage (e.g. OTC/foreign listings Alpaca doesn't support) but solves a problem this product doesn't have — Tier 1 is US-listed equities/ETFs only (ADR-003, unchanged) | Not adopted, no identified need |

---

## Cost estimate — light personal-use deployment

Anthropic pricing per docs/DECISIONS.md's ADR-017 (`claude-sonnet-5`,
verified current as of the cited date — re-verify via the `claude-api`
skill before implementation, since intro pricing has an end date). All
figures below are **rough planning estimates**, not guarantees — actual
token counts depend on evidence-bundle size and prompt design not yet
written.

**Assumptions:** a full committee run (5 parallel analyst calls + Risk/PM
call + CIO call = 3 round-trips, ADR-038) averages roughly 3,000–6,000
input tokens and 400–800 output tokens per call across the 7 role-calls a
full run makes (5 analysts batched as roughly-parallel individual calls +
1 Risk/PM combined or sequential call + 1 CIO call — treat as ~7 billed
calls per full committee run for this estimate). New evidence-vendor free
tiers assumed to have $0 marginal cost within their rate limit.

| Scenario | Full-committee runs/day | Est. committee LLM cost/day | Est. committee LLM cost/month | Evidence vendor cost | Notes |
|---|---|---|---|---|---|
| **Low** (few pre-filtered names, occasional `/ask` use) | 3–5 names/day | ~$0.15–$0.35 | ~$5–$10 | $0 (within free tiers) | Matches BLOCKING_DECISIONS.md #3's default pre-filter bar (top 8, often fewer clear that bar) |
| **Normal** (default pre-filter bar of 8 names/day, daily `/ask` use) | 8 names/day | ~$0.25–$0.55 | ~$8–$17 | $0 (within free tiers, assuming daily/weekly refresh cadence stays under free-tier rate limits) | The expected steady-state MVP cost |
| **Heavy** (pre-filter bar raised, e.g. all 48 names get full committee daily, plus frequent manual `/ask` re-runs) | 48 names/day | ~$1.50–$3.30 | ~$45–$100 | Possible free-tier overage → paid tier needed (BLOCKING_DECISIONS.md #1, requires your approval) | This is the scenario that would most likely force a paid evidence-vendor decision, not the LLM cost itself |

**Existing shipped-MVP `/ask` usage** (unchanged, already measured live —
docs/TEST_EVIDENCE.md Phase 4) is roughly $0.015/question and adds
negligibly to any scenario above at personal-use call volumes.

**The one real cost lever is BLOCKING_DECISIONS.md #3** (the committee
pre-filter bar) — it's deliberately the single config value that scales
this entire estimate, versioned and auditable (principle 8) rather than a
hardcoded constant, specifically so cost can be dialed without a code
change if the estimate above turns out to be wrong in practice.
