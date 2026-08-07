"""Position sizing tests (Revision Prompt 7, HES-3) — "notional equals
risk budget divided by selected expected-move percentage, then is
reduced by allocation, sector, correlation, liquidity, speculative-name,
and cash constraints," plus the prompt's own named scenarios:
correlated semiconductor positions and insufficient cash."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradingos_api.services.position_sizing import compute_tactical_position_size


def _base_kwargs() -> dict:
    return {
        "account_equity": Decimal("100000"),
        "risk_budget_pct": Decimal("0.25"),
        "expected_move_pct": Decimal("5.0"),
        "price": Decimal("50.00"),
        "max_position_pct": Decimal("15.00"),
        "max_sector_pct": Decimal("25.00"),
        "sector_current_notional": Decimal("0"),
        "max_correlated_group_pct": Decimal("25.00"),
        "correlated_group_current_notional": Decimal("0"),
        "avg_daily_dollar_volume": Decimal("50_000_000"),
        "max_liquidity_pct_of_adv": Decimal("1.0"),
        "is_speculative_name": False,
        "speculative_position_pct_cap": Decimal("5.00"),
        "available_cash": Decimal("100000"),
    }


class TestUnconstrainedSizing:
    def test_raw_risk_based_notional_is_risk_budget_over_expected_move(self) -> None:
        result = compute_tactical_position_size(**_base_kwargs())
        # $100,000 * 0.25% = $250 risk / 5% expected move = $5,000 notional.
        assert result.raw_risk_based_notional == Decimal("5000.00")
        assert result.final_notional == Decimal("5000.00")
        assert result.final_quantity == 100
        assert result.binding_constraint_keys == []

    def test_zero_or_negative_expected_move_is_rejected(self) -> None:
        kwargs = _base_kwargs()
        kwargs["expected_move_pct"] = Decimal("0")
        with pytest.raises(ValueError, match="expected_move_pct"):
            compute_tactical_position_size(**kwargs)


class TestCorrelatedSemiconductorPositions:
    def test_existing_correlated_group_exposure_caps_the_new_position(self) -> None:
        """Two existing semiconductor positions already consume most of
        the correlated-group budget; a third correlated name's size must
        be capped by the remaining room, not sized as if it were the
        only position in the group."""
        kwargs = _base_kwargs()
        kwargs["risk_budget_pct"] = Decimal("2.0")  # push the raw notional up so the cap binds
        kwargs["max_correlated_group_pct"] = Decimal("10.00")  # $10,000 group ceiling
        kwargs["correlated_group_current_notional"] = Decimal("9000")  # $9,000 already used
        result = compute_tactical_position_size(**kwargs)
        assert "MAX_CORRELATED_GROUP_EXPOSURE" in result.binding_constraint_keys
        assert result.final_notional <= Decimal("1000")

    def test_correlated_group_already_at_its_cap_allows_no_new_notional(self) -> None:
        kwargs = _base_kwargs()
        kwargs["max_correlated_group_pct"] = Decimal("10.00")
        kwargs["correlated_group_current_notional"] = Decimal("10000")  # already at the cap
        result = compute_tactical_position_size(**kwargs)
        assert result.final_notional == Decimal(0)
        assert result.final_quantity == 0


class TestInsufficientCash:
    def test_available_cash_below_the_risk_based_size_caps_the_position(self) -> None:
        kwargs = _base_kwargs()
        kwargs["risk_budget_pct"] = Decimal("2.0")  # raw notional would be $4,000
        kwargs["available_cash"] = Decimal("300")
        result = compute_tactical_position_size(**kwargs)
        assert "AVAILABLE_CASH" in result.binding_constraint_keys
        assert result.final_notional <= Decimal("300")

    def test_zero_available_cash_produces_a_zero_quantity_not_an_error(self) -> None:
        kwargs = _base_kwargs()
        kwargs["available_cash"] = Decimal("0")
        result = compute_tactical_position_size(**kwargs)
        assert result.final_quantity == 0
        assert result.final_notional == Decimal(0)


class TestLiquidityCap:
    def test_thin_average_daily_dollar_volume_caps_the_position(self) -> None:
        kwargs = _base_kwargs()
        kwargs["risk_budget_pct"] = Decimal("1.0")
        kwargs["avg_daily_dollar_volume"] = Decimal("10_000")
        kwargs["max_liquidity_pct_of_adv"] = Decimal("1.0")  # $100 ceiling
        result = compute_tactical_position_size(**kwargs)
        assert "LIQUIDITY_CAP" in result.binding_constraint_keys
        assert result.final_notional <= Decimal("100")


class TestSpeculativeNameCap:
    def test_speculative_flag_applies_its_own_tighter_cap(self) -> None:
        kwargs = _base_kwargs()
        kwargs["risk_budget_pct"] = Decimal("1.0")
        kwargs["is_speculative_name"] = True
        kwargs["speculative_position_pct_cap"] = Decimal("0.50")  # $500 ceiling
        result = compute_tactical_position_size(**kwargs)
        assert "SPECULATIVE_NAME_CAP" in result.binding_constraint_keys
        assert result.final_notional <= Decimal("500")

    def test_non_speculative_name_never_applies_the_speculative_cap(self) -> None:
        kwargs = _base_kwargs()
        kwargs["is_speculative_name"] = False
        kwargs["speculative_position_pct_cap"] = Decimal("0.01")  # would be tiny if applied
        result = compute_tactical_position_size(**kwargs)
        assert "SPECULATIVE_NAME_CAP" not in result.binding_constraint_keys


class TestAllocationAndSectorCaps:
    def test_max_position_allocation_binds_before_sector(self) -> None:
        kwargs = _base_kwargs()
        kwargs["risk_budget_pct"] = Decimal("1.0")  # raw = $2,000
        kwargs["max_position_pct"] = Decimal("1.00")  # $1,000 ceiling
        result = compute_tactical_position_size(**kwargs)
        assert "MAX_POSITION_ALLOCATION" in result.binding_constraint_keys
        assert result.final_notional <= Decimal("1000")

    def test_sector_exposure_near_its_cap_leaves_little_remaining_room(self) -> None:
        kwargs = _base_kwargs()
        kwargs["risk_budget_pct"] = Decimal("1.0")
        kwargs["max_sector_pct"] = Decimal("25.00")  # $25,000 ceiling
        kwargs["sector_current_notional"] = Decimal("24900")  # $100 remaining
        result = compute_tactical_position_size(**kwargs)
        assert "MAX_SECTOR_EXPOSURE" in result.binding_constraint_keys
        assert result.final_notional <= Decimal("100")
