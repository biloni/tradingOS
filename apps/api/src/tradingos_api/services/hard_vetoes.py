"""The 10 hard vetoes (Revision Prompt 7) — any single one blocks a
proposal outright, the same AND-gate/veto philosophy every deterministic
gate in this project already uses (HES-2, `baseline_eligibility.py`,
`investment_quality.py`'s `hard_disqualified`). Every veto produces a
`user-readable explanation code` (Revision Prompt 7's own wording) —
`veto_code` is the stable machine-readable identifier, `explanation` is
the plain-English sentence a reviewer reads without cross-referencing
the code elsewhere.

Pure, DB-agnostic functions — the caller (the pipeline orchestrator,
`services/recommendation_pipeline.py`) gathers every input from wherever
it actually lives (Revision Prompt 4's evidence layer, Revision Prompt
5's deterministic features, `RiskPolicy`, `core.config.Settings`'s kill
switch, `BrokerEnvironmentAttestation`), matching this project's
established "pure function, caller assembles inputs" boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

CALCULATION_VERSION = "v1"


@dataclass(frozen=True)
class VetoResult:
    veto_code: str
    triggered: bool
    explanation: str


@dataclass(frozen=True)
class HardVetoInputs:
    """Every boolean/value one of the 10 hard vetoes checks. `None`
    where a value is inapplicable to the current lane/stage (e.g.
    `expected_move_pct` for an Investment-lane proposal) — a veto whose
    inputs don't apply to this proposal simply never triggers, it does
    not raise."""

    # 1. stale required data
    has_stale_required_data: bool
    stale_data_detail: str | None = None
    # 2. unverified event date/time
    event_timing_verified: bool = True
    event_timing_category: str | None = None
    # 3. failed liquidity
    liquidity_passed: bool = True
    avg_daily_dollar_volume: Decimal | None = None
    # 4. risk or sector limit (includes max-concurrent-earnings-trades, HES-3)
    risk_or_sector_limit_breached: bool = False
    risk_or_sector_limit_detail: str | None = None
    # 5. missing price or expected move
    has_current_price: bool = True
    has_expected_move: bool = True
    # 6. evidence leakage (Revision Prompt 4's point-in-time guard tripped)
    evidence_leakage_detected: bool = False
    evidence_leakage_detail: str | None = None
    # 7. kill switch active
    kill_switch_active: bool = False
    # 8. broker environment ambiguity (OA-6)
    broker_environment_ambiguous: bool = False
    broker_environment_detail: str | None = None
    # 9. investment/tactical attribution ambiguity (PM-1/PM-2, ADR-046)
    attribution_ambiguous: bool = False
    attribution_detail: str | None = None
    # 10. expired recommendation
    recommendation_review_date: date | None = None
    as_of: datetime | None = None


def _check_stale_required_data(inputs: HardVetoInputs) -> VetoResult:
    triggered = inputs.has_stale_required_data
    detail = inputs.stale_data_detail or "required evidence is stale"
    return VetoResult(
        "STALE_REQUIRED_DATA", triggered, f"Blocked: {detail}." if triggered else "OK"
    )


def _check_unverified_event_timing(inputs: HardVetoInputs) -> VetoResult:
    triggered = not inputs.event_timing_verified
    category = inputs.event_timing_category or "UNKNOWN"
    return VetoResult(
        "UNVERIFIED_EVENT_TIMING",
        triggered,
        (
            f"Blocked: event date/time is not verified (timing_category={category})."
            if triggered
            else "OK"
        ),
    )


def _check_failed_liquidity(inputs: HardVetoInputs) -> VetoResult:
    triggered = not inputs.liquidity_passed
    return VetoResult(
        "FAILED_LIQUIDITY",
        triggered,
        "Blocked: average daily dollar volume does not clear the liquidity floor."
        if triggered
        else "OK",
    )


def _check_risk_or_sector_limit(inputs: HardVetoInputs) -> VetoResult:
    triggered = inputs.risk_or_sector_limit_breached
    detail = inputs.risk_or_sector_limit_detail or "a risk or sector limit is breached"
    return VetoResult(
        "RISK_OR_SECTOR_LIMIT", triggered, f"Blocked: {detail}." if triggered else "OK"
    )


def _check_missing_price_or_expected_move(inputs: HardVetoInputs) -> VetoResult:
    triggered = not inputs.has_current_price or not inputs.has_expected_move
    missing = []
    if not inputs.has_current_price:
        missing.append("current price")
    if not inputs.has_expected_move:
        missing.append("expected move")
    return VetoResult(
        "MISSING_PRICE_OR_EXPECTED_MOVE",
        triggered,
        f"Blocked: missing {' and '.join(missing)}." if triggered else "OK",
    )


def _check_evidence_leakage(inputs: HardVetoInputs) -> VetoResult:
    triggered = inputs.evidence_leakage_detected
    detail = inputs.evidence_leakage_detail or "evidence usable_at is after the evidence cutoff"
    return VetoResult("EVIDENCE_LEAKAGE", triggered, f"Blocked: {detail}." if triggered else "OK")


def _check_kill_switch(inputs: HardVetoInputs) -> VetoResult:
    triggered = inputs.kill_switch_active
    return VetoResult(
        "KILL_SWITCH_ACTIVE",
        triggered,
        "Blocked: the kill switch is active — operating mode is forced to RESEARCH_ONLY."
        if triggered
        else "OK",
    )


def _check_broker_environment_ambiguous(inputs: HardVetoInputs) -> VetoResult:
    triggered = inputs.broker_environment_ambiguous
    detail = (
        inputs.broker_environment_detail or "account, environment, or broker endpoint is ambiguous"
    )
    return VetoResult(
        "BROKER_ENVIRONMENT_AMBIGUOUS", triggered, f"Blocked: {detail}." if triggered else "OK"
    )


def _check_attribution_ambiguous(inputs: HardVetoInputs) -> VetoResult:
    triggered = inputs.attribution_ambiguous
    detail = inputs.attribution_detail or "this proposal cannot be attributed to a single lane"
    return VetoResult(
        "INVESTMENT_TACTICAL_ATTRIBUTION_AMBIGUOUS",
        triggered,
        f"Blocked: {detail}." if triggered else "OK",
    )


def _check_expired_recommendation(inputs: HardVetoInputs) -> VetoResult:
    if inputs.recommendation_review_date is None or inputs.as_of is None:
        return VetoResult("RECOMMENDATION_EXPIRED", False, "OK")
    review_date = inputs.recommendation_review_date
    as_of_date = inputs.as_of.date()
    triggered = review_date < as_of_date
    return VetoResult(
        "RECOMMENDATION_EXPIRED",
        triggered,
        f"Blocked: recommendation review date {review_date} has passed (as of {as_of_date})."
        if triggered
        else "OK",
    )


_ALL_CHECKS = (
    _check_stale_required_data,
    _check_unverified_event_timing,
    _check_failed_liquidity,
    _check_risk_or_sector_limit,
    _check_missing_price_or_expected_move,
    _check_evidence_leakage,
    _check_kill_switch,
    _check_broker_environment_ambiguous,
    _check_attribution_ambiguous,
    _check_expired_recommendation,
)


def evaluate_hard_vetoes(inputs: HardVetoInputs) -> list[VetoResult]:
    return [check(inputs) for check in _ALL_CHECKS]


def any_veto_triggered(results: list[VetoResult]) -> bool:
    return any(r.triggered for r in results)


def triggered_vetoes(results: list[VetoResult]) -> list[VetoResult]:
    return [r for r in results if r.triggered]
