"""Guidance parsing with synthetic official releases (Revision Prompt
4's required test #5). `SyntheticCompanyGuidanceProvider` does real
text parsing (`_parse_guidance_release`), not a canned lookup — these
tests exercise it through the public provider interface."""

from __future__ import annotations

import pytest

from tradingos_api.providers.synthetic_evidence import (
    SyntheticCompanyGuidanceProvider,
    _parse_guidance_release,
)


class TestParsesTheSyntheticOfficialRelease:
    def test_metric_and_period_are_extracted(self) -> None:
        [record] = SyntheticCompanyGuidanceProvider().get_guidance("AMD")
        assert record.metric == "revenue"
        assert record.period == "Q3-2026"

    def test_low_high_and_midpoint_are_extracted_and_consistent(self) -> None:
        [record] = SyntheticCompanyGuidanceProvider().get_guidance("AMD")
        assert record.guidance_low is not None
        assert record.guidance_high is not None
        assert record.guidance_midpoint is not None
        low = float(record.guidance_low)
        high = float(record.guidance_high)
        midpoint = float(record.guidance_midpoint)
        assert low == pytest.approx(8_000_000_000.0)
        assert high == pytest.approx(8_400_000_000.0)
        assert midpoint == pytest.approx((low + high) / 2)

    def test_units_and_source_type_are_official(self) -> None:
        [record] = SyntheticCompanyGuidanceProvider().get_guidance("AMD")
        assert record.units == "USD"
        assert record.source_type == "official_ir_release"

    def test_ticker_with_no_fixture_returns_empty(self) -> None:
        assert SyntheticCompanyGuidanceProvider().get_guidance("ZZZZ") == []

    def test_fiscal_period_filter_excludes_non_matching_period(self) -> None:
        assert SyntheticCompanyGuidanceProvider().get_guidance("AMD", fiscal_period="Q1-2020") == []


class TestParserRejectsUnparseableText:
    def test_a_release_missing_the_expected_shape_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not parse"):
            _parse_guidance_release("This press release does not follow the expected format.")
