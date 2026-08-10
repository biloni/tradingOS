"""Active position monitor tests (Revision Prompt 11 task 73) —
`services/position_monitor.py::evaluate_position()`'s alert conditions
and dedup behavior."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import OrderLegRole, OrderSide, OrderStatus, OrderType
from tradingos_api.models.execution import Account, Order, OrderLeg
from tradingos_api.services.position_monitor import PositionMonitorInputs, evaluate_position

_NOW = datetime(2026, 8, 10, 15, 0, tzinfo=UTC)


def _base_inputs(
    seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID, **overrides: object
) -> PositionMonitorInputs:
    defaults: dict[str, object] = {
        "account_id": uuid.uuid4(),
        "instrument_id": seeded_instrument_id,
        "owner_user_id": seeded_user_id,
        "ticker": "AMD",
        "now": _NOW,
        "quote_price": Decimal("150.00"),
        "quote_observed_at": _NOW - timedelta(minutes=1),
        "position_quantity": Decimal("100"),
    }
    defaults.update(overrides)
    return PositionMonitorInputs(**defaults)  # type: ignore[arg-type]


def _alert_types(result: object) -> set[str]:
    return {alert.alert_type.value for alert, _ in result.alerts}  # type: ignore[attr-defined]


class TestProviderOutageShortCircuits:
    def test_outage_fires_only_provider_outage(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            provider_outage=True,
            quote_observed_at=None,  # would also be DATA_STALE if not short-circuited
        )
        result = evaluate_position(db_session, inputs)
        assert _alert_types(result) == {"PROVIDER_OUTAGE"}


class TestDataStale:
    def test_no_quote_ever_observed_is_stale(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(seeded_user_id, seeded_instrument_id, quote_observed_at=None)
        result = evaluate_position(db_session, inputs)
        assert "DATA_STALE" in _alert_types(result)

    def test_aged_out_quote_is_stale(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id, seeded_instrument_id, quote_observed_at=_NOW - timedelta(hours=1)
        )
        result = evaluate_position(db_session, inputs)
        assert "DATA_STALE" in _alert_types(result)

    def test_fresh_quote_is_not_stale(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id, seeded_instrument_id, quote_observed_at=_NOW - timedelta(minutes=2)
        )
        result = evaluate_position(db_session, inputs)
        assert "DATA_STALE" not in _alert_types(result)

    def test_stale_does_not_block_other_checks(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            quote_observed_at=None,
            upcoming_earnings_date=_NOW.date() + timedelta(days=1),
        )
        result = evaluate_position(db_session, inputs)
        assert {"DATA_STALE", "EARNINGS_APPROACHING"} <= _alert_types(result)


class TestStopAndTarget:
    def test_stop_reached(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            quote_price=Decimal("95.00"),
            stop_price=Decimal("100.00"),
        )
        result = evaluate_position(db_session, inputs)
        assert "STOP_REACHED" in _alert_types(result)

    def test_price_above_stop_does_not_fire(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            quote_price=Decimal("101.00"),
            stop_price=Decimal("100.00"),
        )
        result = evaluate_position(db_session, inputs)
        assert "STOP_REACHED" not in _alert_types(result)

    def test_target_reached(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            quote_price=Decimal("205.00"),
            target_prices=[Decimal("200.00"), Decimal("250.00")],
        )
        result = evaluate_position(db_session, inputs)
        assert "TARGET_REACHED" in _alert_types(result)

    def test_no_open_position_never_fires_stop_or_target(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            position_quantity=Decimal("0"),
            quote_price=Decimal("50.00"),
            stop_price=Decimal("100.00"),
            target_prices=[Decimal("10.00")],
        )
        result = evaluate_position(db_session, inputs)
        assert "STOP_REACHED" not in _alert_types(result)
        assert "TARGET_REACHED" not in _alert_types(result)


class TestEntryZone:
    def test_within_tolerance_fires_entry_zone_reached(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            position_quantity=Decimal("0"),
            quote_price=Decimal("100.50"),
            entry_price=Decimal("100.00"),
        )
        result = evaluate_position(db_session, inputs)
        assert "ENTRY_ZONE_REACHED" in _alert_types(result)

    def test_outside_tolerance_does_not_fire(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            position_quantity=Decimal("0"),
            quote_price=Decimal("110.00"),
            entry_price=Decimal("100.00"),
        )
        result = evaluate_position(db_session, inputs)
        assert "ENTRY_ZONE_REACHED" not in _alert_types(result)

    def test_already_filled_position_never_fires_entry_zone(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            position_quantity=Decimal("100"),
            quote_price=Decimal("100.00"),
            entry_price=Decimal("100.00"),
        )
        result = evaluate_position(db_session, inputs)
        assert "ENTRY_ZONE_REACHED" not in _alert_types(result)


class TestGapRisk:
    def test_gap_through_stop_fires_both_gap_risk_and_stop_reached(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            quote_price=Decimal("90.00"),
            stop_price=Decimal("100.00"),
            prior_close=Decimal("105.00"),
        )
        result = evaluate_position(db_session, inputs)
        assert {"GAP_RISK", "STOP_REACHED"} <= _alert_types(result)

    def test_gradual_stop_touch_does_not_fire_gap_risk(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            quote_price=Decimal("99.50"),
            stop_price=Decimal("100.00"),
            prior_close=Decimal("99.80"),  # already below stop yesterday too
        )
        result = evaluate_position(db_session, inputs)
        assert "GAP_RISK" not in _alert_types(result)
        assert "STOP_REACHED" in _alert_types(result)


class TestEarningsApproaching:
    def test_within_window_fires(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            upcoming_earnings_date=_NOW.date() + timedelta(days=2),
        )
        result = evaluate_position(db_session, inputs)
        assert "EARNINGS_APPROACHING" in _alert_types(result)

    def test_outside_window_does_not_fire(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            upcoming_earnings_date=_NOW.date() + timedelta(days=30),
        )
        result = evaluate_position(db_session, inputs)
        assert "EARNINGS_APPROACHING" not in _alert_types(result)

    def test_past_date_does_not_fire(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            upcoming_earnings_date=_NOW.date() - timedelta(days=1),
        )
        result = evaluate_position(db_session, inputs)
        assert "EARNINGS_APPROACHING" not in _alert_types(result)


class TestPortfolioLimitBreach:
    def test_over_cap_fires(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            account_equity=Decimal("100000"),
            position_notional=Decimal("15000"),
            max_position_pct=Decimal("10.0"),
        )
        result = evaluate_position(db_session, inputs)
        assert "PORTFOLIO_LIMIT_BREACH" in _alert_types(result)

    def test_under_cap_does_not_fire(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            account_equity=Decimal("100000"),
            position_notional=Decimal("5000"),
            max_position_pct=Decimal("10.0"),
        )
        result = evaluate_position(db_session, inputs)
        assert "PORTFOLIO_LIMIT_BREACH" not in _alert_types(result)


class TestMarketRegimeChanged:
    def test_changed_regime_fires(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            current_regime="RISK_OFF",
            previous_regime="RISK_ON",
        )
        result = evaluate_position(db_session, inputs)
        assert "MARKET_REGIME_CHANGED" in _alert_types(result)

    def test_unchanged_regime_does_not_fire(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            current_regime="RISK_ON",
            previous_regime="RISK_ON",
        )
        result = evaluate_position(db_session, inputs)
        assert "MARKET_REGIME_CHANGED" not in _alert_types(result)

    def test_no_prior_regime_is_not_a_change(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        inputs = _base_inputs(
            seeded_user_id, seeded_instrument_id, current_regime="RISK_ON", previous_regime=None
        )
        result = evaluate_position(db_session, inputs)
        assert "MARKET_REGIME_CHANGED" not in _alert_types(result)


class TestDeduplicationAcrossRepeatedEvaluations:
    def test_repeated_stop_reached_does_not_duplicate(
        self, db_session: Session, seeded_user_id: uuid.UUID, seeded_instrument_id: uuid.UUID
    ) -> None:
        account_id = uuid.uuid4()
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            account_id=account_id,
            quote_price=Decimal("95.00"),
            stop_price=Decimal("100.00"),
        )
        first = evaluate_position(db_session, inputs)
        second = evaluate_position(db_session, inputs)

        first_stop = next(a for a, _ in first.alerts if a.alert_type.value == "STOP_REACHED")
        second_stop, second_created = next(
            (a, c) for a, c in second.alerts if a.alert_type.value == "STOP_REACHED"
        )
        assert second_created is False
        assert second_stop.id == first_stop.id


class TestWorksWithExistingBracketOrders:
    """Required test category "existing bracket orders" (Revision Prompt
    11) — the monitor must react correctly to stop/target prices sourced
    from a real, already-submitted bracket (Revision Prompt 10's
    `OrderLeg`/`bracket_group_id`), not only from a `RecommendationLevel`.
    `PositionMonitorInputs.stop_price`/`target_prices` are caller-
    assembled, so this proves the caller-supplied-inputs boundary already
    handles a live bracket correctly rather than requiring the monitor to
    special-case it."""

    def _bracket_prices(
        self,
        db_session: Session,
        *,
        account_id: uuid.UUID,
        instrument_id: uuid.UUID,
        stop_price: Decimal,
        target_price: Decimal,
    ) -> tuple[Decimal, Decimal]:
        bracket_group_id = uuid.uuid4()
        primary = Order(
            account_id=account_id,
            instrument_id=instrument_id,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("100"),
            status=OrderStatus.FILLED,
        )
        stop_leg_order = Order(
            account_id=account_id,
            instrument_id=instrument_id,
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            quantity=Decimal("100"),
            stop_price=stop_price,
            status=OrderStatus.SUBMITTED,
        )
        target_leg_order = Order(
            account_id=account_id,
            instrument_id=instrument_id,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100"),
            limit_price=target_price,
            status=OrderStatus.SUBMITTED,
        )
        db_session.add_all([primary, stop_leg_order, target_leg_order])
        db_session.flush()
        db_session.add_all(
            [
                OrderLeg(order_id=primary.id, role=OrderLegRole.PRIMARY),
                OrderLeg(
                    order_id=stop_leg_order.id,
                    role=OrderLegRole.STOP_LOSS,
                    bracket_group_id=bracket_group_id,
                ),
                OrderLeg(
                    order_id=target_leg_order.id,
                    role=OrderLegRole.TAKE_PROFIT,
                    bracket_group_id=bracket_group_id,
                ),
            ]
        )
        db_session.flush()

        # Read the prices back the way a live caller would — via the
        # bracket's own OrderLeg rows, not the test's local variables —
        # so this exercises the real query shape a scheduled job uses.
        stop_row = db_session.execute(
            select(Order.stop_price)
            .join(OrderLeg, OrderLeg.order_id == Order.id)
            .where(
                OrderLeg.role == OrderLegRole.STOP_LOSS,
                OrderLeg.bracket_group_id == bracket_group_id,
            )
        ).scalar_one()
        target_row = db_session.execute(
            select(Order.limit_price)
            .join(OrderLeg, OrderLeg.order_id == Order.id)
            .where(
                OrderLeg.role == OrderLegRole.TAKE_PROFIT,
                OrderLeg.bracket_group_id == bracket_group_id,
            )
        ).scalar_one()
        return stop_row, target_row

    def test_stop_reached_using_a_live_bracket_orders_stop_price(
        self,
        db_session: Session,
        seeded_user_id: uuid.UUID,
        seeded_instrument_id: uuid.UUID,
        fresh_account: Account,
    ) -> None:
        account_id = fresh_account.id
        stop_price, _ = self._bracket_prices(
            db_session,
            account_id=account_id,
            instrument_id=seeded_instrument_id,
            stop_price=Decimal("100.00"),
            target_price=Decimal("200.00"),
        )
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            account_id=account_id,
            quote_price=Decimal("95.00"),
            stop_price=stop_price,
        )
        result = evaluate_position(db_session, inputs)
        assert "STOP_REACHED" in _alert_types(result)

    def test_target_reached_using_a_live_bracket_orders_limit_price(
        self,
        db_session: Session,
        seeded_user_id: uuid.UUID,
        seeded_instrument_id: uuid.UUID,
        fresh_account: Account,
    ) -> None:
        account_id = fresh_account.id
        _, target_price = self._bracket_prices(
            db_session,
            account_id=account_id,
            instrument_id=seeded_instrument_id,
            stop_price=Decimal("100.00"),
            target_price=Decimal("200.00"),
        )
        inputs = _base_inputs(
            seeded_user_id,
            seeded_instrument_id,
            account_id=account_id,
            quote_price=Decimal("205.00"),
            target_prices=[target_price],
        )
        result = evaluate_position(db_session, inputs)
        assert "TARGET_REACHED" in _alert_types(result)
