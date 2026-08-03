# Model Governance

This document was written as binding policy before the first line of LLM
integration code existed (Phase 1), and is updated here (Phase 4) to record
how each policy actually landed in code — nothing below was retrofitted
after the fact to match whatever got built.

## Tool-use, not text-to-SQL

**Implemented.** The `LLMProvider` interface
(`apps/api/src/tradingos_api/providers/llm.py`) returns typed `LLMToolCall`
objects with a `tool_name` and validated `arguments`, never a raw string the
caller would parse as a query. `services/llm_tools.py` defines 5 typed
tools (`query_symbols`, `get_price_summary`, `get_indicators`,
`get_recommendations`, `compute_recommendation`) as an explicit allow-list
(`_ARG_MODELS`/`_HANDLERS`) — a tool name outside that list raises
`UnknownToolError`, and every tool's arguments are validated against a
pydantic model before any DB access happens (`execute_tool()`). The model
has no direct database access and no path to execute arbitrary SQL.

## Grounding

**Implemented.** `services/ask.py`'s `SYSTEM_PROMPT` instructs the model:
never estimate/recall/guess a number, always call a tool for any figure it
states, say plainly when a tool returns an error or no data rather than
filling the gap, and never state its own confidence level. This mirrors
principle 4/5 at the prompt level, not just the code level.

## Confidence is not a probability until it's calibrated

**Implemented.** Per principle 15: an LLM's self-reported confidence (e.g.,
"I'm 80% sure") is never presented to the user as a calibrated probability.
`services/scoring.py`'s `_confidence_from_signals()` computes a qualitative
`LOW`/`MEDIUM`/`HIGH` band purely from how many of the 4 signals agree in
direction (net agreement, no LLM call involved) — this is what
`Recommendation.confidence` stores. `services/ask.py`'s system prompt
explicitly instructs the model never to state its own confidence level.
Historical-outcome-based calibration (did a given confidence band's
recommendations actually pan out) needs completed trade history, which
doesn't exist yet — deferred to Phase 5+ (backtesting) before any number is
ever framed as a calibrated probability.

## Strategy changes require review, not auto-activation

Per principle 16, any change the learning system proposes to scoring
formulas or thresholds requires: a backtest report, an explicit comparison
against the currently-active `StrategyVersion`, and the user's explicit
approval — before it becomes the active version. There is no code path in
this system's design that activates a new strategy version without that
approval step.

## Cost and prompt versioning

**Implemented.** Every LLM call is logged (`LLMCallLog` —
docs/DATA_DICTIONARY.md) via `services/ask.py`'s `_log_call()`, with the
exact `prompt_version` (`services/ask.py`'s `PROMPT_VERSION = "ask-v1"`),
token counts, and cost (`services/llm_cost.py`'s `estimate_cost_usd()`,
using a documented per-token pricing constant verified against the
`claude-api` skill — see ADR-017). `Recommendation.prompt_version` is
likewise versioned, so a past recommendation can always be traced back to
the exact prompt that produced it.

## Responsible use for HR/individual-risk-style inferences

Although this system's domain is trading rather than HR, the same caution
applies to any inference framed as being "about a person" (e.g., the user's
own risk tolerance or behavior pattern): aggregate-first answers, and no
individual risk-scoring surfaced without explicit governance review — this
system does not, in its current or planned scope, make behavioral inferences
about the user.

## Rate limiting

**Implemented.** `POST /api/v1/ask` (`routers/ask.py`) is rate-limited via
`core/rate_limit.py`'s in-process `TokenBucketRateLimiter` (ADR-021) — a
5-request burst, 5/min steady-state refill — to bound both Anthropic spend
and the blast radius of a runaway client loop. Exceeding it returns `429`.

## Tool-call budget

**Implemented.** `services/ask.py`'s tool-use orchestration loop is capped
at `MAX_ITERATIONS = 5` Anthropic calls per `/api/v1/ask` request (ADR-019)
— an unbounded or adversarial tool-call sequence can't run indefinitely or
burn unbounded spend on a single request.
