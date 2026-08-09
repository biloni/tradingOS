"""The official exchange calendar (Revision Prompt 9) — NYSE/Nasdaq
trading days, holidays, and early closes, with an America/Los_Angeles
display timezone. This is the one source of truth the scheduler
(`services/morning_plan_scheduler.py`) and every "is today a trading
day" check use — no separate vendor, matching docs/MORNING_PLAN_SPEC.md's
"market-calendar-aware, reusing whatever market-calendar source the
scheduler already needs for job timing."

A hardcoded, documented 2026 holiday calendar (not a live vendor call)
— this project's stated policy throughout ("do not purchase a paid
service," Revision Prompt 4) extends naturally to not adding a calendar
API dependency for a fact (US market holidays) that is public,
published a year in advance, and changes only via a documented,
infrequent SEC/exchange rule change. `EARLY_CLOSE_DATES_2026` is
imported from `services/data_quality.py` (Revision Prompt 4) rather
than duplicated — one list, one source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from tradingos_api.services.data_quality import KNOWN_EARLY_CLOSE_DATES_2026

CALCULATION_VERSION = "v1"

DISPLAY_TIMEZONE = ZoneInfo("America/Los_Angeles")
EXCHANGE_TIMEZONE = ZoneInfo("America/New_York")

# NYSE/Nasdaq 2026 holiday calendar (published, fixed dates) — the
# exchange is closed on each of these; no session occurs.
NYSE_HOLIDAYS_2026: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),  # New Year's Day
        date(2026, 1, 19),  # Martin Luther King Jr. Day
        date(2026, 2, 16),  # Washington's Birthday
        date(2026, 4, 3),  # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),  # Independence Day (observed — July 4 is a Saturday)
        date(2026, 9, 7),  # Labor Day
        date(2026, 11, 26),  # Thanksgiving Day
        date(2026, 12, 25),  # Christmas Day
    }
)

# Regular session: 09:30-16:00 America/New_York. Early-close session:
# 09:30-13:00 America/New_York (the day after Thanksgiving, Christmas
# Eve, etc. — `KNOWN_EARLY_CLOSE_DATES_2026`).
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_EARLY_CLOSE = time(13, 0)


@dataclass(frozen=True)
class TradingDayResolution:
    calendar_date: date
    is_trading_day: bool
    skip_reason: str | None
    is_early_close: bool
    session_open_utc: datetime | None
    session_close_utc: datetime | None


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=Saturday, 6=Sunday


def resolve_trading_day(calendar_date: date) -> TradingDayResolution:
    """ "Skip non-trading days but publish the reason" — `skip_reason` is
    always populated (never `None` masquerading as "nothing to report")
    whenever `is_trading_day` is `False`."""
    if _is_weekend(calendar_date):
        return TradingDayResolution(
            calendar_date=calendar_date,
            is_trading_day=False,
            skip_reason=f"{calendar_date.strftime('%A')} — weekend, no trading session.",
            is_early_close=False,
            session_open_utc=None,
            session_close_utc=None,
        )
    if calendar_date in NYSE_HOLIDAYS_2026:
        return TradingDayResolution(
            calendar_date=calendar_date,
            is_trading_day=False,
            skip_reason=f"{calendar_date.isoformat()} is an NYSE/Nasdaq market holiday.",
            is_early_close=False,
            session_open_utc=None,
            session_close_utc=None,
        )

    is_early_close = calendar_date in KNOWN_EARLY_CLOSE_DATES_2026
    close_time = _EARLY_CLOSE if is_early_close else _REGULAR_CLOSE
    session_open = datetime.combine(calendar_date, _REGULAR_OPEN, tzinfo=EXCHANGE_TIMEZONE)
    session_close = datetime.combine(calendar_date, close_time, tzinfo=EXCHANGE_TIMEZONE)
    return TradingDayResolution(
        calendar_date=calendar_date,
        is_trading_day=True,
        skip_reason=None,
        is_early_close=is_early_close,
        session_open_utc=session_open.astimezone(ZoneInfo("UTC")),
        session_close_utc=session_close.astimezone(ZoneInfo("UTC")),
    )


def next_trading_day(after: date, *, inclusive: bool = False) -> TradingDayResolution:
    """The next real trading session at/after `after` (`inclusive=True`)
    or strictly after it. Handles a run of consecutive holidays/weekends
    (e.g. a Friday holiday running into a weekend) by walking forward
    day by day rather than assuming at most one non-trading day at a
    time."""
    candidate = after if inclusive else after + timedelta(days=1)
    for _ in range(14):  # generous bound — no real gap exceeds a long weekend + one holiday
        resolution = resolve_trading_day(candidate)
        if resolution.is_trading_day:
            return resolution
        candidate += timedelta(days=1)
    raise RuntimeError(f"no trading day found within 14 days of {after.isoformat()}")


def to_display_timezone(moment: datetime) -> datetime:
    """Every user-facing display timestamp is America/Los_Angeles
    (Revision Prompt 9's own stated display timezone) — DST-safe because
    `zoneinfo` resolves the correct UTC offset for the given date, never
    a hardcoded `-08:00`/`-07:00`."""
    return moment.astimezone(DISPLAY_TIMEZONE)


def countdown_to_open(now_utc: datetime, session_open_utc: datetime | None) -> timedelta | None:
    if session_open_utc is None:
        return None
    return session_open_utc - now_utc
