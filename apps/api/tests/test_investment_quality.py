"""Investment lane feature-engine tests (Revision Prompt 5) — proves the
9 components stay independent (no blended score) and that
`hard_disqualified` is a veto no combination of strong components can
override, the same "AND gate, not a score" philosophy the tactical
lane's baseline eligibility gate uses."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from tradingos_api.services.investment_quality import compute_investment_quality

AS_OF = date(2026, 8, 6)


def _rising_closes(n: int, start: Decimal = Decimal(100)) -> list[Decimal | None]:
    return [start + Decimal(i) * Decimal("0.3") for i in range(n)]


def _healthy_kwargs() -> dict[str, Any]:
    return {
        "revenue_growth_yoy_pct": Decimal("12.0"),
        "earnings_growth_yoy_pct": Decimal("15.0"),
        "margin_trend_bps_yoy": Decimal("50"),
        "debt_to_equity": Decimal("0.8"),
        "free_cash_flow_positive": True,
        "pe_ratio": Decimal("18"),
        "sector_median_pe": Decimal("22"),
        "peg_ratio": Decimal("1.2"),
        "earnings_revision_direction": "UP",
        "sector_name": "Healthcare",
        "instrument_closes": _rising_closes(260),
        "benchmark_closes": _rising_closes(260, start=Decimal(400)),
        "documented_catalyst_count": 2,
        "has_major_unresolved_event_risk": False,
        "position_pct_of_portfolio": Decimal("3.0"),
        "sector_concentration_pct": Decimal("15.0"),
        "max_position_pct": Decimal("5.0"),
        "max_sector_pct": Decimal("25.0"),
        "has_going_concern_flag": False,
        "has_unresolved_data_quality_issue": False,
        "as_of": AS_OF,
    }


class TestHealthyCompanyAllComponentsPass:
    def test_all_nine_components_pass_and_not_disqualified(self) -> None:
        result = compute_investment_quality(**_healthy_kwargs())
        assert len(result.components) == 9
        assert all(c.status == "PASS" for c in result.components)
        assert result.hard_disqualified is False
        assert result.disqualification_reason is None


class TestHardDisqualificationOverridesEveryComponent:
    def test_going_concern_flag_disqualifies_despite_all_passing_components(self) -> None:
        kwargs = _healthy_kwargs()
        kwargs["has_going_concern_flag"] = True
        result = compute_investment_quality(**kwargs)
        assert all(c.status == "PASS" for c in result.components)  # components unaffected
        assert result.hard_disqualified is True
        assert result.disqualification_reason is not None
        assert "going-concern" in result.disqualification_reason

    def test_unresolved_data_quality_issue_disqualifies_independently(self) -> None:
        kwargs = _healthy_kwargs()
        kwargs["has_unresolved_data_quality_issue"] = True
        result = compute_investment_quality(**kwargs)
        assert result.hard_disqualified is True
        assert "data-quality" in (result.disqualification_reason or "")


class TestComponentsFailIndependently:
    def test_negative_growth_fails_only_the_growth_component(self) -> None:
        kwargs = _healthy_kwargs()
        kwargs["revenue_growth_yoy_pct"] = Decimal("-5.0")
        result = compute_investment_quality(**kwargs)
        by_key = {c.component_key: c.status for c in result.components}
        assert by_key["REVENUE_EARNINGS_GROWTH"] == "FAIL"
        assert by_key["MARGIN_TREND"] == "PASS"  # unaffected

    def test_missing_valuation_inputs_is_missing_data_not_fail(self) -> None:
        kwargs = _healthy_kwargs()
        kwargs["pe_ratio"] = None
        kwargs["peg_ratio"] = None
        result = compute_investment_quality(**kwargs)
        valuation = next(c for c in result.components if c.component_key == "VALUATION")
        assert valuation.status == "MISSING_DATA"

    def test_non_durable_sector_fails_durability_component_only(self) -> None:
        kwargs = _healthy_kwargs()
        kwargs["sector_name"] = "Semiconductors"
        result = compute_investment_quality(**kwargs)
        by_key = {c.component_key: c.status for c in result.components}
        assert by_key["BUSINESS_SECTOR_DURABILITY"] == "FAIL"
        assert by_key["VALUATION"] == "PASS"  # not blended together

    def test_over_concentration_fails_diversification_component(self) -> None:
        kwargs = _healthy_kwargs()
        kwargs["position_pct_of_portfolio"] = Decimal("8.0")  # over the 5.0 max
        result = compute_investment_quality(**kwargs)
        diversification = next(
            c for c in result.components if c.component_key == "PORTFOLIO_DIVERSIFICATION"
        )
        assert diversification.status == "FAIL"
