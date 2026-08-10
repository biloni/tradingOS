"""Active position monitor (Revision Prompt 11) — evaluates one open (or
pending-entry) position against MONITORING INPUTS [quote and freshness;
market session; stop/target proximity; sector and market regime;
position, open orders, and portfolio concentration] and emits the
position-lifecycle alerts from Prompt 11's 18-type taxonomy that this
module owns: `ENTRY_ZONE_REACHED`, `TARGET_REACHED`, `STOP_REACHED`,
`GAP_RISK`, `EARNINGS_APPROACHING`, `DATA_STALE`, `PROVIDER_OUTAGE`,
`PORTFOLIO_LIMIT_BREACH`, `MARKET_REGIME_CHANGED`.

The remaining nine alert types (`APPROVAL_REQUIRED`, `ORDER_STATUS_CHANGED`,
`RESULTS_AVAILABLE`, `GUIDANCE_CONFLICT`, `POST_EARNINGS_CONFIRMATION_READY`,
`POST_EARNINGS_CONFIRMATION_FAILED`, `TAKE_PARTIAL_PROFIT_SUGGESTION`,
`EXIT_SUGGESTION`, `THESIS_INVALIDATED`) are owned by
`services/order_authority.py`/`services/order_execution.py` (order/approval
lifecycle, Revision Prompt 10) and `services/post_earnings_workflow.py`
(the post-earnings confirmation stage, Revision Prompt 11) respectively —
this split matches Prompt 11's own MONITORING INPUTS list, which
separates "quote/session/stop-target/portfolio/broker state" from
"filings, earnings releases, guidance, consensus, actuals, post-event
gap/volume/VWAP/ranges."

Every alert here goes through `services/alerts_engine.py::create_or_dedupe_alert()`
— the same "one function, deterministic dedup, expiring, evidence-linked,
audited" discipline every other Prompt 11 alert producer uses. Inputs
are caller-assembled (`PositionMonitorInputs`), the same "pure function,
caller gathers the inputs" boundary `CommitteeInputBundle`/
`PostEarningsMarketContext` already establish — a live caller (a
scheduled job) sources these from `providers/quotes_bars.py`, the
`Position`/`Order` tables, and `models.market_evidence.MarketRegimeSnapshot`;
tests and the demo script supply a fixed instance.

Long-only scope: this project's paper-trading demo never shorts, so
stop/target/gap-risk direction below assumes `position_quantity >= 0`
and a stop below / target above the current price — documented rather
than generalized to a short-position case with no current caller."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from tradingos_api.models.enums import AlertSeverity, AlertType
from tradingos_api.models.operations import Alert
from tradingos_api.services.alerts_engine import create_or_dedupe_alert

DEFAULT_STALE_QUOTE_AFTER = timedelta(minutes=15)
"""Documented default (no live market-data outage has ever been observed
by this project) — chosen to be comfortably longer than a normal
quote-refresh cadence but short enough that a real feed interruption is
caught within one trading session."""

DEFAULT_PROXIMITY_TOLERANCE_PCT = Decimal("1.0")
"""How close the quote must be to an entry price to count as
"in the entry zone" — a flat percentage placeholder, the same
documented-approximation style `DEFAULT_PRICE_MOVE_THRESHOLD_PCT`
(`services/order_authority.py`, Revision Prompt 10) already uses."""

DEFAULT_EARNINGS_APPROACHING_WINDOW_DAYS = 3


@dataclass(frozen=True)
class PositionMonitorInputs:
    account_id: uuid.UUID
    instrument_id: uuid.UUID
    owner_user_id: uuid.UUID
    ticker: str
    now: datetime
    quote_price: Decimal | None
    quote_observed_at: datetime | None
    position_quantity: Decimal
    entry_price: Decimal | None = None
    stop_price: Decimal | None = None
    target_prices: list[Decimal] = field(default_factory=list)
    prior_close: Decimal | None = None
    upcoming_earnings_date: date | None = None
    account_equity: Decimal | None = None
    position_notional: Decimal | None = None
    max_position_pct: Decimal | None = None
    current_regime: str | None = None
    previous_regime: str | None = None
    provider_outage: bool = False
    stale_after: timedelta = DEFAULT_STALE_QUOTE_AFTER
    proximity_tolerance_pct: Decimal = DEFAULT_PROXIMITY_TOLERANCE_PCT
    earnings_approaching_within_days: int = DEFAULT_EARNINGS_APPROACHING_WINDOW_DAYS


@dataclass
class PositionMonitorResult:
    alerts: list[tuple[Alert, bool]] = field(default_factory=list)
    """`(alert, created)` per triggered condition — `created=False` means
    `create_or_dedupe_alert()` returned an already-open alert for the
    same condition rather than a new one (Prompt 11's "deduplicated")."""


def evaluate_position(db: Session, inputs: PositionMonitorInputs) -> PositionMonitorResult:
    result = PositionMonitorResult()

    def _fire(
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        detail: str,
        dedup_suffix: str,
    ) -> Alert:
        alert, created = create_or_dedupe_alert(
            db,
            owner_user_id=inputs.owner_user_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            detail=detail,
            triggered_at=inputs.now,
            dedup_key=(
                f"{alert_type.value.lower()}:{inputs.account_id}:"
                f"{inputs.instrument_id}:{dedup_suffix}"
            ),
            evidence_type="Position",
            evidence_id=inputs.instrument_id,
            instrument_id=inputs.instrument_id,
        )
        result.alerts.append((alert, created))
        return alert

    # PROVIDER_OUTAGE takes precedence over every other price-based
    # check below — a stale-or-missing quote during a known provider
    # outage is an outage, not an independent staleness finding.
    if inputs.provider_outage:
        _fire(
            AlertType.PROVIDER_OUTAGE,
            AlertSeverity.CRITICAL,
            f"{inputs.ticker}: market data provider outage",
            "The market data provider is reporting an outage — every "
            "price-based check for this position is unreliable until it recovers.",
            "outage",
        )
        return result

    # DATA_STALE — a missing or aged-out quote. Staleness does not block
    # the remaining structural checks below (portfolio concentration,
    # earnings timing, regime) since those don't depend on today's price.
    is_stale = (
        inputs.quote_observed_at is None
        or (inputs.now - inputs.quote_observed_at) > inputs.stale_after
    )
    if is_stale:
        age_detail = (
            "no quote has ever been observed"
            if inputs.quote_observed_at is None
            else f"last observed at {inputs.quote_observed_at.isoformat()}"
        )
        _fire(
            AlertType.DATA_STALE,
            AlertSeverity.WARNING,
            f"{inputs.ticker}: quote is stale",
            f"{age_detail} — exceeds the {inputs.stale_after} freshness threshold.",
            "stale",
        )

    price = inputs.quote_price
    has_position = inputs.position_quantity > 0

    if price is not None:
        # GAP_RISK — the stop was blown through overnight/pre-market
        # rather than reached gradually, meaning the actual exit fill
        # will likely be worse than the stop price itself.
        if (
            has_position
            and inputs.stop_price is not None
            and inputs.prior_close is not None
            and inputs.prior_close >= inputs.stop_price
            and price < inputs.stop_price
        ):
            _fire(
                AlertType.GAP_RISK,
                AlertSeverity.CRITICAL,
                f"{inputs.ticker}: gapped through the stop",
                f"Prior close {inputs.prior_close} was at/above the stop "
                f"{inputs.stop_price}; the quote has already gapped to {price} — "
                "expect the actual exit fill to be worse than the stop price.",
                "gap",
            )

        # STOP_REACHED / TARGET_REACHED — checked independently of
        # GAP_RISK above; a gapped-through stop is still a reached stop.
        if has_position and inputs.stop_price is not None and price <= inputs.stop_price:
            _fire(
                AlertType.STOP_REACHED,
                AlertSeverity.CRITICAL,
                f"{inputs.ticker}: stop reached",
                f"Quote {price} has reached or passed the stop price {inputs.stop_price}.",
                "stop",
            )
        for target in inputs.target_prices:
            if has_position and price >= target:
                _fire(
                    AlertType.TARGET_REACHED,
                    AlertSeverity.INFO,
                    f"{inputs.ticker}: target reached",
                    f"Quote {price} has reached or passed the target price {target}.",
                    f"target:{target}",
                )

        # ENTRY_ZONE_REACHED — only meaningful before a position exists;
        # once filled, the entry zone question is moot.
        if not has_position and inputs.entry_price is not None and inputs.entry_price > 0:
            distance_pct = abs(price - inputs.entry_price) / inputs.entry_price * Decimal(100)
            if distance_pct <= inputs.proximity_tolerance_pct:
                _fire(
                    AlertType.ENTRY_ZONE_REACHED,
                    AlertSeverity.INFO,
                    f"{inputs.ticker}: entry zone reached",
                    f"Quote {price} is within {inputs.proximity_tolerance_pct}% of the "
                    f"planned entry {inputs.entry_price}.",
                    "entry",
                )

    # EARNINGS_APPROACHING — independent of price/quote availability.
    if inputs.upcoming_earnings_date is not None:
        days_until = (inputs.upcoming_earnings_date - inputs.now.date()).days
        if 0 <= days_until <= inputs.earnings_approaching_within_days:
            _fire(
                AlertType.EARNINGS_APPROACHING,
                AlertSeverity.INFO,
                f"{inputs.ticker}: earnings approaching",
                f"Reports on {inputs.upcoming_earnings_date.isoformat()} "
                f"({days_until} day(s) away).",
                "earnings",
            )

    # PORTFOLIO_LIMIT_BREACH — this position's share of account equity
    # exceeds the configured cap.
    if (
        inputs.account_equity is not None
        and inputs.account_equity > 0
        and inputs.position_notional is not None
        and inputs.max_position_pct is not None
    ):
        weight_pct = inputs.position_notional / inputs.account_equity * Decimal(100)
        if weight_pct > inputs.max_position_pct:
            _fire(
                AlertType.PORTFOLIO_LIMIT_BREACH,
                AlertSeverity.WARNING,
                f"{inputs.ticker}: position concentration limit breached",
                f"This position is {weight_pct:.2f}% of account equity, "
                f"exceeding the {inputs.max_position_pct}% cap.",
                "concentration",
            )

    # MARKET_REGIME_CHANGED — a genuine change, not the absence of a
    # prior regime to compare against (a first-ever evaluation is not a
    # "change").
    if (
        inputs.current_regime is not None
        and inputs.previous_regime is not None
        and inputs.current_regime != inputs.previous_regime
    ):
        _fire(
            AlertType.MARKET_REGIME_CHANGED,
            AlertSeverity.INFO,
            f"Market regime changed: {inputs.previous_regime} -> {inputs.current_regime}",
            f"Regime moved from {inputs.previous_regime} to {inputs.current_regime}.",
            f"regime:{inputs.previous_regime}:{inputs.current_regime}",
        )

    return result
