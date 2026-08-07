"""Golden vectors for the tactical 8-component earnings direction score
(Revision Prompt 5, docs/HYBRID_EARNINGS_STRATEGY.md HES-1). Fixed,
hand-computable input series with a known expected `total_score` for
each of the three canonical cases: all 8 pass, all 8 fail, and a mixed
case exercising `INSUFFICIENT_HISTORY`/`MISSING_DATA` alongside
PASS/FAIL — proving `total_score` is a literal count of `PASS`
components, never a weighted blend."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tradingos_api.services.earnings_score import compute_tactical_earnings_score

AS_OF = date(2026, 8, 6)


def _rising_closes(n: int, start: Decimal = Decimal(100)) -> list[Decimal | None]:
    return [start + Decimal(i) * Decimal("0.5") for i in range(n)]


def _falling_closes(n: int, start: Decimal = Decimal(200)) -> list[Decimal | None]:
    return [start - Decimal(i) * Decimal("0.5") for i in range(n)]


def _flat_volumes(n: int, value: int = 1_000_000) -> list[int | None]:
    return [value for _ in range(n)]


class TestAllEightComponentsPass:
    def test_total_score_is_8_of_8(self) -> None:
        result = compute_tactical_earnings_score(
            instrument_closes=_rising_closes(40),
            spy_closes=_rising_closes(40, start=Decimal(400)),
            instrument_volumes=[1_000_000 + i * 20_000 for i in range(25)],
            consensus_eps_estimate=Decimal("1.20"),
            prior_year_actual_eps=Decimal("1.00"),
            num_analysts=6,
            prior_gap_pcts=[Decimal("1.0"), Decimal("2.0"), Decimal("0.5")],
            as_of=AS_OF,
        )
        assert result.total_score == 8
        assert result.max_score == 8
        assert all(c.status == "PASS" for c in result.components)


class TestAllEightComponentsFail:
    def test_total_score_is_0_of_8(self) -> None:
        result = compute_tactical_earnings_score(
            instrument_closes=_falling_closes(40),
            spy_closes=_falling_closes(40, start=Decimal(400)),
            instrument_volumes=[1_000_000 - i * 20_000 for i in range(25)],
            consensus_eps_estimate=Decimal("0.80"),
            prior_year_actual_eps=Decimal("1.00"),
            num_analysts=2,  # below the full-quality minimum of 4
            prior_gap_pcts=[Decimal("-1.0"), Decimal("-2.0")],
            as_of=AS_OF,
        )
        assert result.total_score == 0
        assert all(c.status == "FAIL" for c in result.components)
        analyst_component = next(
            c for c in result.components if c.component_key == "ANALYST_COVERAGE"
        )
        assert "reduces completeness" in (analyst_component.detail or "")


class TestMixedScoreWithMissingAndInsufficientComponents:
    def test_score_counts_only_pass_and_reports_non_pass_statuses_honestly(self) -> None:
        result = compute_tactical_earnings_score(
            instrument_closes=_rising_closes(40),  # components 1-3 PASS
            spy_closes=_falling_closes(40, start=Decimal(400)),  # components 7 FAIL, 2 FAIL
            instrument_volumes=[1_000_000 for _ in range(10)],  # too short: INSUFFICIENT_HISTORY
            consensus_eps_estimate=None,  # MISSING_DATA
            prior_year_actual_eps=Decimal("1.00"),
            num_analysts=4,  # exactly the full-quality minimum
            prior_gap_pcts=[Decimal("1.5")],  # only 1: INSUFFICIENT_HISTORY
            as_of=AS_OF,
        )
        by_key = {c.component_key: c for c in result.components}
        assert by_key["PRICE_ABOVE_EMA20"].status == "PASS"
        assert by_key["RS_20D_VS_SPY"].status == "PASS"  # instrument up, SPY down
        assert by_key["MOMENTUM_5D"].status == "PASS"
        assert by_key["VOLUME_ACCUMULATION"].status == "INSUFFICIENT_HISTORY"
        assert by_key["FORECAST_EPS_GROWTH"].status == "MISSING_DATA"
        assert by_key["ANALYST_COVERAGE"].status == "PASS"
        assert by_key["SPY_ABOVE_EMA20"].status == "FAIL"
        assert by_key["PRIOR_GAP_BIAS"].status == "INSUFFICIENT_HISTORY"
        # total_score is a raw PASS count, not a weighted or normalized figure.
        assert result.total_score == sum(1 for c in result.components if c.status == "PASS")
        assert result.total_score == 4
