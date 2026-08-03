from decimal import Decimal

# claude-sonnet-5 pricing per million tokens, verified via the claude-api
# skill on 2026-08-03. Intro pricing is in effect through 2026-08-31 — after
# that date, update to $3.00 input / $15.00 output per million tokens.
INPUT_PRICE_PER_MILLION = Decimal("2.00")
OUTPUT_PRICE_PER_MILLION = Decimal("10.00")


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> Decimal:
    """Approximate cost for one LLM call, for `LLMCallLog.cost_usd`
    (principle 8: cost tracking). An approximation, like the payroll
    employer-tax functions — documented, not exact to the cent Anthropic
    bills, since volume discounts/rounding aren't modeled."""
    input_cost = Decimal(input_tokens) / Decimal(1_000_000) * INPUT_PRICE_PER_MILLION
    output_cost = Decimal(output_tokens) / Decimal(1_000_000) * OUTPUT_PRICE_PER_MILLION
    return input_cost + output_cost
