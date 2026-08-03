# Model Governance

No LLM code exists yet (that's Phase 4). This document is written now, as
binding policy, so the rules exist before the first line of LLM integration
code is written — not retrofitted after the fact.

## Tool-use, not text-to-SQL

The `LLMProvider` interface (apps/api/src/tradingos_api/providers/llm.py)
returns typed `LLMToolCall` objects with a `tool_name` and validated
`arguments`, never a raw string the caller would parse as a query. When
Phase 4 implements this against Anthropic's API, the model will be given a
small, fixed set of typed tools (query workers/positions/scores — the
trading-domain equivalent of `query_workers`/`get_headcount_summary` style
tools from comparable systems) and will never have direct database access or
the ability to execute arbitrary SQL.

## Grounding

The system prompt instructs the model to answer only from tool results
returned to it and to explicitly say when data is missing, stale, or
conflicting rather than filling the gap — mirroring principle 4/5 at the
prompt level, not just the code level.

## Confidence is not a probability until it's calibrated

Per principle 15: an LLM's self-reported confidence (e.g., "I'm 80% sure")
is never presented to the user as a calibrated probability. Before any
confidence number is surfaced as if it were one, it must be derived from
historical outcome tracking (did recommendations at a given confidence level
actually perform as that confidence implied, over a real sample of
completed trades). Until enough history exists to calibrate against, the
UI shows qualitative confidence bands or the raw rationale, not a percentage
framed as a probability.

## Strategy changes require review, not auto-activation

Per principle 16, any change the learning system proposes to scoring
formulas or thresholds requires: a backtest report, an explicit comparison
against the currently-active `StrategyVersion`, and the user's explicit
approval — before it becomes the active version. There is no code path in
this system's design that activates a new strategy version without that
approval step.

## Cost and prompt versioning

Every LLM call is logged (`LLMCallLog` — docs/DATA_DICTIONARY.md) with the
exact prompt version used, token counts, and cost. Prompt text itself is
versioned (not just referenced by a mutable "latest"), so a past
recommendation can always be traced back to the exact prompt that produced
it.

## Responsible use for HR/individual-risk-style inferences

Although this system's domain is trading rather than HR, the same caution
applies to any inference framed as being "about a person" (e.g., the user's
own risk tolerance or behavior pattern): aggregate-first answers, and no
individual risk-scoring surfaced without explicit governance review — this
system does not, in its current or planned scope, make behavioral inferences
about the user.

## Rate limiting

The NL query endpoint (Phase 4) will be rate-limited server-side to bound
both cost and the blast radius of any single runaway client loop.
