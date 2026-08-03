"""Deterministic technical indicator formulas (principle 6: plain code, no
LLM involvement; principle 4/5: `None` where there isn't enough history yet
— never a fabricated value).

Every function is a pure function over plain `Decimal` lists — no DB/ORM
dependency — so they're trivially unit-testable against hand-verifiable
invariants (see tests/test_indicators.py) rather than half-remembered
"textbook" reference numbers.

Formula version for everything in this module: bump `FORMULA_VERSION` (and
therefore the `Indicator.version` column) whenever a formula changes here —
never overwrite historical rows under the old version string.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from tradingos_api.models.indicator import Indicator, IndicatorName
from tradingos_api.services.price_bars import get_latest_price_bars

FORMULA_VERSION = "v1"


def sma(closes: list[Decimal], window: int) -> list[Decimal | None]:
    """Simple moving average. `None` for the first `window - 1` points."""
    result: list[Decimal | None] = []
    for i in range(len(closes)):
        if i + 1 < window:
            result.append(None)
        else:
            window_slice = closes[i + 1 - window : i + 1]
            result.append(sum(window_slice) / Decimal(window))
    return result


def _ema_raw(values: list[Decimal], span: int) -> list[Decimal]:
    """EMA seeded at `values[0]`, defined for every index (standard
    recursive definition). Callers mask the first `span - 1` points to
    `None` before publishing — see `ema()`."""
    if not values:
        return []
    alpha = Decimal(2) / Decimal(span + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def ema(closes: list[Decimal], span: int) -> list[Decimal | None]:
    """Exponential moving average. `None` for the first `span - 1` points,
    matching the "full window of history required" convention used by every
    other indicator here, even though the recursive formula is technically
    defined from the first point onward (seeded at `closes[0]`)."""
    raw = _ema_raw(closes, span)
    return [None if i + 1 < span else raw[i] for i in range(len(raw))]


def rsi(closes: list[Decimal], period: int = 14) -> list[Decimal | None]:
    """Wilder's RSI. `None` until `period` deltas are available (i.e. index
    `period`). Explicit zero-division convention (documented, not accidental):
    both average gain and average loss are zero (a perfectly flat series) ->
    RSI = 50; average loss is zero with a positive average gain -> RSI = 100.
    """
    n = len(closes)
    result: list[Decimal | None] = [None] * n
    if n <= period:
        return result

    deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains = [d if d > 0 else Decimal(0) for d in deltas]
    losses = [-d if d < 0 else Decimal(0) for d in deltas]

    avg_gain = sum(gains[:period]) / Decimal(period)
    avg_loss = sum(losses[:period]) / Decimal(period)
    result[period] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / Decimal(period)
        avg_loss = (avg_loss * (period - 1) + losses[i]) / Decimal(period)
        result[i + 1] = _rsi_from_averages(avg_gain, avg_loss)

    return result


def _rsi_from_averages(avg_gain: Decimal, avg_loss: Decimal) -> Decimal:
    if avg_gain == 0 and avg_loss == 0:
        return Decimal(50)
    if avg_loss == 0:
        return Decimal(100)
    rs = avg_gain / avg_loss
    return Decimal(100) - (Decimal(100) / (1 + rs))


class MacdResult:
    def __init__(
        self,
        line: list[Decimal | None],
        signal: list[Decimal | None],
        histogram: list[Decimal | None],
    ) -> None:
        self.line = line
        self.signal = signal
        self.histogram = histogram


def macd(closes: list[Decimal], fast: int = 12, slow: int = 26, signal_span: int = 9) -> MacdResult:
    """MACD line = EMA(fast) - EMA(slow); signal = EMA(MACD line, signal_span);
    histogram = MACD line - signal. Masking is based on each output's own
    minimum required history (see module docstring's "None until enough
    history" convention) — internal EMA computation stays fully seeded/raw
    throughout so later values are numerically correct regardless of where
    the public mask cuts off.
    """
    raw_fast = _ema_raw(closes, fast)
    raw_slow = _ema_raw(closes, slow)
    raw_line = [f - s for f, s in zip(raw_fast, raw_slow, strict=True)]
    raw_signal = _ema_raw(raw_line, signal_span)
    raw_hist = [m - s for m, s in zip(raw_line, raw_signal, strict=True)]

    line_min_index = slow - 1
    signal_min_index = slow - 1 + signal_span - 1

    line = [None if i < line_min_index else raw_line[i] for i in range(len(closes))]
    signal = [None if i < signal_min_index else raw_signal[i] for i in range(len(closes))]
    histogram = [None if i < signal_min_index else raw_hist[i] for i in range(len(closes))]
    return MacdResult(line=line, signal=signal, histogram=histogram)


class BollingerBands:
    def __init__(
        self,
        upper: list[Decimal | None],
        mid: list[Decimal | None],
        lower: list[Decimal | None],
    ) -> None:
        self.upper = upper
        self.mid = mid
        self.lower = lower


def bollinger_bands(closes: list[Decimal], window: int = 20, num_std: int = 2) -> BollingerBands:
    """Mid band is exactly `sma(closes, window)` (reused, not
    reimplemented). Upper/lower are mid +/- `num_std` population standard
    deviations of the same window (population, not sample — the original
    Bollinger Bands convention)."""
    mid = sma(closes, window)
    upper: list[Decimal | None] = []
    lower: list[Decimal | None] = []
    for i in range(len(closes)):
        mid_value = mid[i]
        if mid_value is None:
            upper.append(None)
            lower.append(None)
            continue
        window_slice = closes[i + 1 - window : i + 1]
        variance = sum((v - mid_value) ** 2 for v in window_slice) / Decimal(window)
        std_dev = variance.sqrt()
        upper.append(mid_value + num_std * std_dev)
        lower.append(mid_value - num_std * std_dev)
    return BollingerBands(upper=upper, mid=mid, lower=lower)


def atr(
    highs: list[Decimal], lows: list[Decimal], closes: list[Decimal], period: int = 14
) -> list[Decimal | None]:
    """Average True Range (Wilder's smoothing). `None` until `period` true
    ranges are available (i.e. index `period`, since the first true range
    needs no previous close but every subsequent one does)."""
    n = len(closes)
    result: list[Decimal | None] = [None] * n
    if n == 0:
        return result

    true_ranges = [highs[0] - lows[0]]
    for i in range(1, n):
        true_ranges.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        )

    if n < period:
        return result

    current_atr = sum(true_ranges[:period]) / Decimal(period)
    result[period - 1] = current_atr
    for i in range(period, n):
        current_atr = (current_atr * (period - 1) + true_ranges[i]) / Decimal(period)
        result[i] = current_atr
    return result


def compute_indicators_for_symbol(session: Session, symbol_id: int, start: date, end: date) -> int:
    """Read the latest price bars for `symbol_id` in [start, end] (via the
    shared `get_latest_price_bars` derivation helper), compute every
    indicator in this module, and idempotently insert `Indicator` rows
    (insert-if-not-exists on `(symbol_id, as_of, indicator_name, version)` —
    see `Indicator`'s docstring). Returns the number of rows actually
    inserted (rows that already existed under this `FORMULA_VERSION` are
    silently skipped, not counted).
    """
    bars = get_latest_price_bars(session, symbol_id, start, end)
    if not bars:
        return 0

    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    as_of_dates = [b.as_of for b in bars]

    macd_result = macd(closes)
    bb = bollinger_bands(closes)

    series: dict[IndicatorName, list[Decimal | None]] = {
        IndicatorName.SMA_20: sma(closes, 20),
        IndicatorName.SMA_50: sma(closes, 50),
        IndicatorName.EMA_12: ema(closes, 12),
        IndicatorName.EMA_26: ema(closes, 26),
        IndicatorName.RSI_14: rsi(closes, 14),
        IndicatorName.MACD_LINE: macd_result.line,
        IndicatorName.MACD_SIGNAL: macd_result.signal,
        IndicatorName.MACD_HIST: macd_result.histogram,
        IndicatorName.BB_UPPER: bb.upper,
        IndicatorName.BB_MID: bb.mid,
        IndicatorName.BB_LOWER: bb.lower,
        IndicatorName.ATR_14: atr(highs, lows, closes, 14),
    }

    computed_at = datetime.now(UTC)
    rows = [
        {
            "symbol_id": symbol_id,
            "as_of": as_of_dates[i],
            "indicator_name": indicator_name,
            "version": FORMULA_VERSION,
            "value": value,
            "computed_at": computed_at,
        }
        for indicator_name, values in series.items()
        for i, value in enumerate(values)
        if value is not None
    ]
    if not rows:
        return 0

    # `cursor.rowcount` is unreliable across drivers for a bulk multi-row
    # INSERT ... ON CONFLICT DO NOTHING (observed: psycopg3 returns -1 here).
    # `RETURNING` is the portable way to know how many rows Postgres actually
    # inserted — conflicting (skipped) rows are excluded from what it returns.
    stmt = (
        insert(Indicator)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_indicator_identity")
        .returning(Indicator.id)
    )
    result = session.execute(stmt)
    inserted_count = len(result.fetchall())
    session.commit()
    return inserted_count
