"""LLM call cost estimation (Revision Prompt 6). Re-created for the
current Phase 8+ schema — the shipped MVP had an equivalent
`services/llm_cost.py`, retired along with the rest of Phase 1-7's
business logic at Phase 8 (ADR-044) and not yet rebuilt until this
revision needed real cost-ceiling enforcement for committee runs.

Pricing verified via the `claude-api` skill at implementation time
(2026-08-06, matching ADR-017's own verification): `claude-sonnet-5`
intro pricing is $2.00/$10.00 per million input/output tokens through
2026-08-31, reverting to $3.00/$15.00 afterward. This module prices
every call at the **standard**, non-intro rate — a cost ceiling
computed against the higher, permanent rate is the conservative choice
and never needs to change again once the intro window lapses."""

from __future__ import annotations

from decimal import Decimal

# $/1M tokens, standard (post-intro) rate — re-verify via the claude-api
# skill before adding a new model or bumping this.
_PRICING_PER_MILLION_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-5": (Decimal("3.00"), Decimal("15.00")),
}
_DEFAULT_PRICING = (Decimal("3.00"), Decimal("15.00"))


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    input_rate, output_rate = _PRICING_PER_MILLION_TOKENS.get(model, _DEFAULT_PRICING)
    million = Decimal(1_000_000)
    return (Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate) / million
