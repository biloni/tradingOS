"""Market calendar tests (Revision Prompt 9) — the required "weekday,
holiday, early close, DST transition, and weekend" category.

No database is needed here — `services/market_calendar.py` is pure
functions over a hardcoded, documented 2026 calendar, so these tests run
against fixed dates chosen deliberately: a plain Tuesday, a fixed-date
holiday (Juneteenth) and an observed holiday (July 3 — July 4 falls on a
Saturday in 2026), a known early-close date that is *not* also a
holiday, and the actual 2026 US DST transition dates (spring-forward
March 8, fall-back November 1)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from tradingos_api.services.market_calendar import (
    DISPLAY_TIMEZONE,
    EXCHANGE_TIMEZONE,
    countdown_to_open,
    next_trading_day,
    resolve_trading_day,
    to_display_timezone,
)

UTC = ZoneInfo("UTC")


class TestWeekday:
    def test_a_plain_tuesday_is_a_trading_day(self) -> None:
        resolution = resolve_trading_day(date(2026, 8, 11))  # a Tuesday
        assert resolution.is_trading_day is True
        assert resolution.skip_reason is None
        assert resolution.is_early_close is False
        assert resolution.session_open_utc is not None
        assert resolution.session_close_utc is not None


class TestWeekend:
    def test_saturday_is_not_a_trading_day_with_a_published_reason(self) -> None:
        resolution = resolve_trading_day(date(2026, 8, 8))  # a Saturday
        assert resolution.is_trading_day is False
        assert resolution.skip_reason is not None
        assert "weekend" in resolution.skip_reason.lower()
        assert resolution.session_open_utc is None

    def test_sunday_is_not_a_trading_day(self) -> None:
        resolution = resolve_trading_day(date(2026, 8, 9))  # a Sunday
        assert resolution.is_trading_day is False
        assert "weekend" in (resolution.skip_reason or "").lower()


class TestHoliday:
    def test_fixed_date_holiday_is_not_a_trading_day(self) -> None:
        resolution = resolve_trading_day(date(2026, 6, 19))  # Juneteenth
        assert resolution.is_trading_day is False
        assert resolution.skip_reason is not None
        assert "holiday" in resolution.skip_reason.lower()

    def test_observed_holiday_for_a_weekend_fixed_date_is_not_a_trading_day(self) -> None:
        # July 4, 2026 is a Saturday, so the observed closure moves to
        # Friday July 3 — a real-world wrinkle the hardcoded calendar
        # must encode explicitly, not derive.
        resolution = resolve_trading_day(date(2026, 7, 3))
        assert resolution.is_trading_day is False
        assert "holiday" in (resolution.skip_reason or "").lower()


class TestEarlyClose:
    def test_day_after_thanksgiving_is_a_trading_day_with_an_early_close(self) -> None:
        resolution = resolve_trading_day(date(2026, 11, 27))
        assert resolution.is_trading_day is True
        assert resolution.is_early_close is True
        assert resolution.session_close_utc is not None
        close_local = resolution.session_close_utc.astimezone(EXCHANGE_TIMEZONE)
        assert close_local.time().hour == 13

    def test_regular_trading_day_closes_at_4pm_exchange_time(self) -> None:
        resolution = resolve_trading_day(date(2026, 8, 11))  # a plain Tuesday
        assert resolution.is_early_close is False
        assert resolution.session_close_utc is not None
        close_local = resolution.session_close_utc.astimezone(EXCHANGE_TIMEZONE)
        assert close_local.time().hour == 16


class TestDstTransition:
    def test_spring_forward_shifts_the_utc_session_open_by_one_hour(self) -> None:
        # 2026 US DST begins Sunday March 8 — Monday March 2 is still
        # standard time (EST, UTC-5); Monday March 9 is daylight time
        # (EDT, UTC-4). The *local* 09:30 open is unchanged in both
        # cases; only its UTC representation shifts, proving `zoneinfo`
        # resolves the offset per-date rather than using a fixed one.
        before = resolve_trading_day(date(2026, 3, 2))
        after = resolve_trading_day(date(2026, 3, 9))
        assert before.session_open_utc is not None
        assert after.session_open_utc is not None
        assert before.session_open_utc.astimezone(EXCHANGE_TIMEZONE).time().hour == 9
        assert after.session_open_utc.astimezone(EXCHANGE_TIMEZONE).time().hour == 9
        assert before.session_open_utc.hour == 14  # EST: 09:30 -> 14:30 UTC
        assert after.session_open_utc.hour == 13  # EDT: 09:30 -> 13:30 UTC

    def test_fall_back_shifts_the_utc_session_open_back_by_one_hour(self) -> None:
        # 2026 US DST ends Sunday November 1 — Monday October 26 is
        # still daylight time (EDT); Monday November 2 is standard time
        # (EST).
        before = resolve_trading_day(date(2026, 10, 26))
        after = resolve_trading_day(date(2026, 11, 2))
        assert before.session_open_utc is not None
        assert after.session_open_utc is not None
        assert before.session_open_utc.hour == 13  # EDT: 09:30 -> 13:30 UTC
        assert after.session_open_utc.hour == 14  # EST: 09:30 -> 14:30 UTC

    def test_display_timezone_conversion_is_also_dst_safe(self) -> None:
        # America/Los_Angeles is 3 hours behind America/New_York
        # year-round (both observe DST on the same US schedule), so the
        # displayed local hour should be identical on both sides of the
        # transition even though the UTC instant shifted.
        before = resolve_trading_day(date(2026, 3, 2))
        after = resolve_trading_day(date(2026, 3, 9))
        assert before.session_open_utc is not None
        assert after.session_open_utc is not None
        before_display = to_display_timezone(before.session_open_utc)
        after_display = to_display_timezone(after.session_open_utc)
        assert before_display.time().hour == 6  # 09:30 ET == 06:30 PT, either side of DST
        assert after_display.time().hour == 6
        assert before_display.tzinfo is DISPLAY_TIMEZONE
        assert after_display.tzinfo is DISPLAY_TIMEZONE


class TestNextTradingDaySkipsRunsOfNonTradingDays:
    def test_walks_forward_across_a_holiday_that_abuts_a_weekend(self) -> None:
        # Friday Sept 4, 2026 is a normal trading day; Labor Day (Mon
        # Sept 7) immediately follows the weekend, so the next trading
        # day after Friday should be Tuesday Sept 8, skipping Sat/Sun/Mon
        # in one walk rather than assuming at most one gap day.
        resolution = next_trading_day(date(2026, 9, 4))
        assert resolution.calendar_date == date(2026, 9, 8)
        assert resolution.is_trading_day is True

    def test_inclusive_true_returns_the_same_day_if_it_is_already_a_trading_day(self) -> None:
        resolution = next_trading_day(date(2026, 8, 11), inclusive=True)
        assert resolution.calendar_date == date(2026, 8, 11)


class TestCountdownToOpen:
    def test_countdown_is_none_when_there_is_no_session(self) -> None:
        assert countdown_to_open(datetime.now(UTC), None) is None

    def test_countdown_is_positive_before_the_open_and_negative_after(self) -> None:
        resolution = resolve_trading_day(date(2026, 8, 11))
        assert resolution.session_open_utc is not None
        before_open = countdown_to_open(
            resolution.session_open_utc - timedelta(hours=1), resolution.session_open_utc
        )
        after_open = countdown_to_open(
            resolution.session_open_utc + timedelta(hours=1), resolution.session_open_utc
        )
        assert before_open is not None and before_open.total_seconds() > 0
        assert after_open is not None and after_open.total_seconds() < 0
