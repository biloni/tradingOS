"""Split-adjusted historical gap tests (Revision Prompt 4's required
test #6). Demonstrates why bars must be split-adjusted before computing
an overnight gap: an unadjusted price series across a 2:1 split shows a
~50% false "gap" that is really just the split ratio, not a real
overnight move — exactly what `check_missing_split_adjustment` exists to
catch."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tradingos_api.services.data_quality import check_missing_split_adjustment
from tradingos_api.services.gap_analysis import compute_overnight_gap_pct

# A 2:1 forward split, ex-dated the session between the two closes below.
SPLIT_EX_DATE = date(2026, 8, 5)
PRIOR_CLOSE_RAW = Decimal("200.00")  # the day before the split
POST_SPLIT_OPEN_RAW = Decimal("101.00")  # unadjusted: looks like a ~50% gap down
POST_SPLIT_OPEN_ADJUSTED = Decimal("101.00")
PRIOR_CLOSE_ADJUSTED = Decimal("100.00")  # split-adjusted: same session, halved


class TestUnadjustedBarsShowAFalseGap:
    def test_raw_prices_across_a_split_look_like_a_huge_overnight_move(self) -> None:
        gap_pct = compute_overnight_gap_pct(PRIOR_CLOSE_RAW, POST_SPLIT_OPEN_RAW)
        assert gap_pct < Decimal("-49")  # a ~50% "gap" that isn't real


class TestSplitAdjustedBarsShowTheRealGap:
    def test_adjusted_prices_across_the_same_split_show_a_small_real_gap(self) -> None:
        gap_pct = compute_overnight_gap_pct(PRIOR_CLOSE_ADJUSTED, POST_SPLIT_OPEN_ADJUSTED)
        assert abs(gap_pct) < Decimal("2")


class TestMissingSplitAdjustmentGateCatchesTheUnadjustedCase:
    def test_unadjusted_bar_on_or_after_a_split_ex_date_is_flagged(self) -> None:
        finding = check_missing_split_adjustment(
            bar_adjusted=False,
            bar_as_of=SPLIT_EX_DATE,
            split_ex_dates=[SPLIT_EX_DATE],
        )
        assert finding is not None
        assert "split" in finding.detail.lower()

    def test_adjusted_bar_is_not_flagged(self) -> None:
        finding = check_missing_split_adjustment(
            bar_adjusted=True,
            bar_as_of=SPLIT_EX_DATE,
            split_ex_dates=[SPLIT_EX_DATE],
        )
        assert finding is None

    def test_unadjusted_bar_before_any_split_is_not_flagged(self) -> None:
        finding = check_missing_split_adjustment(
            bar_adjusted=False,
            bar_as_of=date(2026, 8, 1),
            split_ex_dates=[SPLIT_EX_DATE],
        )
        assert finding is None


def test_zero_prior_close_raises() -> None:
    with pytest.raises(ValueError, match="zero"):
        compute_overnight_gap_pct(Decimal("0"), Decimal("10"))
