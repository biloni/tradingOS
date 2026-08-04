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

**Implemented, Phase 6.** Per principle 16, any change to scoring
formulas or thresholds requires: a backtest report, an explicit comparison
against the currently-active `StrategyVersion`, and the user's explicit
approval — before it becomes the active version. `services/strategy.py`'s
`propose_strategy_version()` creates a candidate as `PROPOSED` (never
touching the active version); `run_comparison()` and
`approve_strategy_version()` always re-run a fresh backtest for both the
candidate and the active version before activation (ADR-028) — there is
no code path anywhere in this codebase that activates a new strategy
version without going through that comparison first. Note on what "the
learning system" means here (ADR-026): this project has no autonomous
optimizer that invents candidate weights on its own — proposals are
user/operator-submitted via `POST /api/v1/strategy-versions`. The
review/backtest/comparison/approval gate is the actual governance
requirement, regardless of what originates a candidate. The system never
enforces a numeric approval bar (e.g. "candidate must beat active on
return") — the gate's job is to surface the comparison, never to decide
for the human.

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

---

## Refinement: the investment committee (planned, not yet implemented)

Everything below extends the policies above to the 8-role committee
(docs/ARCHITECTURE.md bounded context 5, ADR-038) — no new governance
*mechanism* is introduced; every existing policy on this page (tool-use
not text-to-SQL, grounding, confidence-is-not-a-probability,
review-before-activation, cost/prompt versioning, rate limiting, tool-call
budget) applies identically to each of the 8 roles. This section records
what's specific to running 8 roles instead of 1.

### Per-role prompt/model versions

Each role gets its own `prompt_version` string (e.g. `committee-bull-v1`,
`committee-cio-v1`), independently bumpable — changing the Bear Analyst's
prompt doesn't require re-versioning the other 7. All 8 roles use the same
model (`claude-sonnet-5`, ADR-017) for MVP; a role-specific model choice
(e.g. a cheaper model for a simpler role) is a future optimization, not
adopted without evidence it's needed — matches the existing "don't add
infrastructure without a demonstrated need" posture.

### Structured outputs per role, not free text

Every role returns a schema-validated structured object, not prose alone —
extending the existing tool-use pattern (`llm_tools.py`'s allow-list) to
each role's *output* shape, not just its ability to call tools:

- **Bull / Bear Analyst:** `{ thesis: str, cited_evidence: [evidence_id],
  key_risks_acknowledged: [str] }` — `cited_evidence` must reference actual
  evidence-bundle item ids (FR-17); a citation to a non-existent evidence
  id is a validation failure, not silently accepted.
- **Technical / Fundamental / Macro Strategist:** `{ assessment: str,
  supporting_indicators_or_evidence: [evidence_id], stance: BULLISH |
  BEARISH | NEUTRAL }`.
- **Risk Manager:** `{ narrative: str, position_size_shares: int,
  stop_price: Decimal, target_price: Decimal, risk_flags: [str] }` — the
  numeric fields here are **echoed from the deterministic gates' tool
  result, never independently computed by the model** (principle 6/7); the
  schema includes them so the narrative is checkable against the same
  numbers a human would see, not so the model is trusted to produce them.
- **Portfolio Manager:** `{ narrative: str, portfolio_fit_flags: [str]
  (e.g. sector concentration, correlation) }`, same
  echo-not-compute rule for any numeric limit it references.
- **CIO/Judge:** `{ recommendation: BUY | SELL | HOLD | WATCH | AVOID |
  NO_ACTION, narrative: str, confidence_inputs_summary: str }` — no
  self-reported numeric confidence field (see below).

Every structured output is validated against its pydantic schema
server-side before being persisted or shown — a malformed response is a
handled error state (retry once, then surface as "committee run failed for
this symbol," never silently coerced into a valid-looking shape).

### Grounding, per role

The existing `SYSTEM_PROMPT` policy ("never estimate/recall/guess a
number, always call a tool, say plainly when data is missing") applies to
every one of the 8 role prompts individually — each role's own prompt
restates it, since each is a separate API call with its own system prompt,
not a shared conversation where one instruction covers all 8.

### Confidence is still not a probability — the CIO doesn't get to invent one either

Extending the existing policy: the CIO's structured output has no
self-reported confidence field at all (see the schema above) — the
`Recommendation.confidence` band is still computed the same deterministic
way the shipped MVP already does (`_confidence_from_signals()`-equivalent,
extended to weigh committee-role agreement the same way the existing
4-signal model weighs indicator agreement: net agreement across Bull/Bear/
Technical/Fundamental/Macro stances, not the CIO's self-assessment).

### Evaluation

**Planned, not yet implemented.** Before this ships, a small fixture-based
eval set (a handful of hand-constructed evidence bundles with known
"obviously bullish," "obviously bearish," "clearly missing data," and
"clearly earnings-blocked" cases) should exist and be checked into
`apps/api/tests/` the same way `test_scoring.py`'s hand-verified invariants
work today — asserting each role's structured output is well-formed and
that the CIO's final action respects the deterministic gates (e.g. never
`BUY` when a gate returned `blocked`), not that any qualitative judgment is
"correct" in some absolute sense (grading committee narrative *quality* is
explicitly out of scope for automated tests — that's ongoing human review,
consistent with principle 16 more broadly).

### Confidence calibration tie-in

Unchanged in kind from the existing policy (still deferred pending real
outcome data), now with a concrete data source: docs/PRODUCT_REQUIREMENTS.md's
FR-40–FR-42 (recommendation-vs-reality tracking) is the prerequisite
dataset. Once enough closed, outcome-tracked recommendations exist, a
calibration pass could compare the deterministic confidence band against
actual win rate per band — still explicitly Phase 2, not attempted without
a real sample size (docs/MVP_PLAN.md).

### Drift monitoring

**Planned, not yet implemented.** Two concrete drift signals to watch once
this ships: (1) a rising rate of malformed/schema-invalid role outputs
over time (would indicate a model or prompt regression), tracked via the
existing `LLMCallLog` error/retry fields; (2) a rising rate of
`recommendation-vs-reality` = `IGNORED` (ADR-041) specifically for
high-confidence recommendations, which would be a signal worth a human
looking at (not an automated alert in MVP — see docs/MVP_PLAN.md's
in-app-only alert scope, BLOCKING_DECISIONS.md #9, which doesn't extend to
system self-monitoring alerts in this pass).

### Human approval gates, extended

The existing propose→backtest→compare→approve loop (ADR-026/027/028,
unchanged mechanism) now also governs: any change to a committee role's
prompt version, the committee pre-filter bar (BLOCKING_DECISIONS.md #3),
and the deterministic-gate thresholds (regime bands, risk-budget %,
stop/target parameters) — per FR-45/FR-46, a prompt change is a strategy
change like any other and gets the identical review gate, not a lighter-
weight path just because it's "only a prompt."

### Cost/iteration budget per committee run

**Planned.** A full committee run is bounded at exactly 7 billed Anthropic
calls (5 parallel analyst roles + 1 Risk/PM call + 1 CIO call, ADR-038) —
no retry loop that could silently balloon this, matching the existing
`MAX_ITERATIONS` philosophy from `/ask`. A single malformed-output retry
(see Structured outputs above) adds at most 1 extra call for the specific
role that failed validation, never a whole-committee re-run.
