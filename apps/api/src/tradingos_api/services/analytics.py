"""Common deterministic technical analytics (Revision Prompt 5). Pure
Python + `decimal.Decimal` throughout — no numpy/pandas runtime
dependency, matching this project's never-float-for-computed-precision
discipline. **No LLM call ever computes a value in this module** —
principle 6/7, restated by this revision's own instruction ("LLMs must
not calculate indicators, expected moves, scores, portfolio risk, or
position size").

Every function returns an `IndicatorResult`: the value (or `None`),
`status` (structured missing-data state), `explanation_code` (machine-
readable reason, always set when `status != OK`), `as_of`, and
`calculation_version` — COMMON ANALYTICS's "structured inputs, values,
versions, as-of times, missing-data states, and explanation codes"
requirement, satisfied identically by every indicator so a diagnostic
UI only has to learn one shape.

Inputs are ordered oldest-to-newest `list[Decimal | None]` (a `None`
element means that session's value is itself missing/not yet usable —
distinct from the list simply being too short).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

CALCULATION_VERSION = "v1"

IndicatorStatus = Literal["OK", "MISSING_DATA", "INSUFFICIENT_HISTORY"]


@dataclass(frozen=True)
class IndicatorResult:
    indicator: str
    value: Decimal | None
    as_of: date
    status: IndicatorStatus
    explanation_code: str | None
    calculation_version: str = CALCULATION_VERSION
    inputs_summary: dict[str, str] = field(default_factory=dict)


def _ok(indicator: str, value: Decimal, as_of: date, **inputs: str) -> IndicatorResult:
    return IndicatorResult(
        indicator=indicator,
        value=value,
        as_of=as_of,
        status="OK",
        explanation_code=None,
        inputs_summary=inputs,
    )


def _insufficient_history(indicator: str, as_of: date, required: int, got: int) -> IndicatorResult:
    return IndicatorResult(
        indicator=indicator,
        value=None,
        as_of=as_of,
        status="INSUFFICIENT_HISTORY",
        explanation_code=f"requires {required} observations, got {got}",
    )


def _missing_data(indicator: str, as_of: date, detail: str) -> IndicatorResult:
    return IndicatorResult(
        indicator=indicator, value=None, as_of=as_of, status="MISSING_DATA", explanation_code=detail
    )


def _clean_window(series: list[Decimal | None], window: int) -> list[Decimal] | None:
    """Returns the last `window` values with no `None` gaps, or `None`
    if the window can't be filled cleanly (caller turns that into the
    appropriate `MISSING_DATA`/`INSUFFICIENT_HISTORY` result)."""
    if len(series) < window:
        return None
    tail = series[-window:]
    if any(v is None for v in tail):
        return None
    return list(tail)  # type: ignore[arg-type]


def sma(closes: list[Decimal | None], window: int, as_of: date) -> IndicatorResult:
    if len(closes) < window:
        return _insufficient_history("SMA", as_of, window, len(closes))
    tail = _clean_window(closes, window)
    if tail is None:
        return _missing_data("SMA", as_of, f"a close within the last {window} sessions is missing")
    value = sum(tail, Decimal(0)) / Decimal(window)
    return _ok("SMA", value, as_of, window=str(window))


def _ewm_series(values: list[Decimal], alpha: Decimal) -> list[Decimal]:
    """Recursive exponentially-weighted mean, seeded by the first value
    and recursed from index 0 — the exact convention pandas'
    `Series.ewm(..., adjust=False).mean()` uses, which the `ta` package
    (this revision's trusted-library comparison) builds on internally
    for `EMAIndicator`, `RSIIndicator`, and `AverageTrueRange`. Matching
    it here (rather than an SMA-seeded variant) is what makes the
    comparison test meaningful rather than "in the same ballpark."""
    series = [values[0]]
    for value in values[1:]:
        series.append(alpha * value + (Decimal(1) - alpha) * series[-1])
    return series


def _ema_series(closes: list[Decimal], window: int) -> list[Decimal]:
    alpha = Decimal(2) / Decimal(window + 1)
    return _ewm_series(closes, alpha)


def ema(closes: list[Decimal | None], window: int, as_of: date) -> IndicatorResult:
    if len(closes) < window:
        return _insufficient_history("EMA", as_of, window, len(closes))
    if any(v is None for v in closes):
        return _missing_data("EMA", as_of, "a close in the requested history is missing")
    series = _ema_series(closes, window)  # type: ignore[arg-type]
    return _ok("EMA", series[-1], as_of, window=str(window))


def rsi(closes: list[Decimal | None], window: int, as_of: date) -> IndicatorResult:
    """Wilder smoothing via `alpha = 1/window` applied as a recursive
    EWM from the first observed gain/loss (matches `ta.momentum.RSIIndicator`
    exactly, not the SMA-seeded textbook variant — see `_ewm_series`).
    A leading `0` is prepended to the gain/loss series before the EWM
    runs, mirroring `pandas.Series.diff(1)`'s first element (which
    `ta` does not drop — `diff.where(diff > 0, 0.0)` maps that leading
    NaN to `0.0` rather than removing it, so it seeds the EWM one step
    earlier than the raw gain/loss list alone would)."""
    if len(closes) < window + 1:
        return _insufficient_history("RSI", as_of, window + 1, len(closes))
    if any(v is None for v in closes):
        return _missing_data("RSI", as_of, "a close in the requested history is missing")
    clean: list[Decimal] = closes  # type: ignore[assignment]
    gains = [Decimal(0)] + [max(clean[i] - clean[i - 1], Decimal(0)) for i in range(1, len(clean))]
    losses = [Decimal(0)] + [max(clean[i - 1] - clean[i], Decimal(0)) for i in range(1, len(clean))]

    alpha = Decimal(1) / Decimal(window)
    avg_gain = _ewm_series(gains, alpha)[-1]
    avg_loss = _ewm_series(losses, alpha)[-1]

    if avg_loss == 0:
        return _ok("RSI", Decimal(100), as_of, window=str(window))
    rs = avg_gain / avg_loss
    value = Decimal(100) - (Decimal(100) / (Decimal(1) + rs))
    return _ok("RSI", value, as_of, window=str(window))


@dataclass(frozen=True)
class MACDResult:
    macd_line: IndicatorResult
    signal_line: IndicatorResult
    histogram: IndicatorResult


def macd(
    closes: list[Decimal | None],
    as_of: date,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MACDResult:
    required = slow + signal
    if len(closes) < required:
        insufficient = _insufficient_history("MACD", as_of, required, len(closes))
        return MACDResult(insufficient, insufficient, insufficient)
    if any(v is None for v in closes):
        missing = _missing_data("MACD", as_of, "a close in the requested history is missing")
        return MACDResult(missing, missing, missing)

    clean: list[Decimal] = closes  # type: ignore[assignment]
    fast_series = _ema_series(clean, fast)
    slow_series = _ema_series(clean, slow)
    macd_series = [f - s for f, s in zip(fast_series, slow_series, strict=True)]
    # `ta.trend.MACD` computes both EMAs with `min_periods=window`
    # (`ta.utils._ema`), so its slow EMA — and therefore its
    # NaN-propagating `macd = emafast - emaslow` — is only defined from
    # index `slow - 1` onward. Its signal EWM then seeds at that first
    # defined point, not at index 0 of a fully-computed macd series.
    # Matching that truncation (not just the recursion convention) is
    # what makes the signal line line up with the trusted library —
    # feeding the full-from-0 series in instead measurably diverges,
    # since a 9-period signal EWM is short enough that its seed point
    # matters.
    mature_macd_series = macd_series[slow - 1 :]
    if len(mature_macd_series) < signal:
        insufficient = _insufficient_history("MACD", as_of, required, len(closes))
        return MACDResult(insufficient, insufficient, insufficient)
    signal_series = _ema_series(mature_macd_series, signal)

    macd_value = macd_series[-1]
    signal_value = signal_series[-1]
    histogram_value = macd_value - signal_value
    return MACDResult(
        macd_line=_ok("MACD_LINE", macd_value, as_of, fast=str(fast), slow=str(slow)),
        signal_line=_ok("MACD_SIGNAL", signal_value, as_of, signal=str(signal)),
        histogram=_ok("MACD_HISTOGRAM", histogram_value, as_of),
    )


def atr(
    highs: list[Decimal | None],
    lows: list[Decimal | None],
    closes: list[Decimal | None],
    window: int,
    as_of: date,
) -> IndicatorResult:
    """Wilder's ATR — true range averaged with Wilder smoothing."""
    shortest = min(len(highs), len(lows), len(closes))
    if shortest < window + 1:
        return _insufficient_history("ATR", as_of, window + 1, shortest)
    if (
        any(v is None for v in highs)
        or any(v is None for v in lows)
        or any(v is None for v in closes)
    ):
        return _missing_data("ATR", as_of, "a high/low/close in the requested history is missing")

    hi: list[Decimal] = highs  # type: ignore[assignment]
    lo: list[Decimal] = lows  # type: ignore[assignment]
    cl: list[Decimal] = closes  # type: ignore[assignment]
    # `ta.volatility.AverageTrueRange` computes true range as
    # `pd.DataFrame({tr1, tr2, tr3}).max(axis=1)` with `skipna=True`
    # (the default) — at bar 0, `tr2`/`tr3` are NaN (no previous close),
    # so the row-max silently falls back to `tr1 = high[0] - low[0]`
    # rather than being NaN itself. Its true-range series is therefore
    # fully defined from index 0, and its seed genuinely averages
    # `window` values (bars 0..window-1) — matched here by giving bar 0
    # the same one-term true range, rather than leaving it undefined.
    true_ranges = [hi[0] - lo[0]]
    for i in range(1, len(hi)):
        true_ranges.append(max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])))

    avg = sum(true_ranges[:window], Decimal(0)) / Decimal(window)
    for tr in true_ranges[window:]:
        avg = (avg * Decimal(window - 1) + tr) / Decimal(window)
    return _ok("ATR", avg, as_of, window=str(window))


def normalized_atr(atr_value: Decimal, close: Decimal, as_of: date) -> IndicatorResult:
    if close == 0:
        return _missing_data("NORMALIZED_ATR", as_of, "close is zero")
    value = (atr_value / close) * Decimal(100)
    return _ok("NORMALIZED_ATR", value, as_of)


def realized_volatility(
    closes: list[Decimal | None], window: int, as_of: date, *, annualize: bool = True
) -> IndicatorResult:
    """Annualized stdev of daily simple returns (×√252) — the standard
    realized-volatility definition."""
    if len(closes) < window + 1:
        return _insufficient_history("REALIZED_VOLATILITY", as_of, window + 1, len(closes))
    tail = _clean_window(closes, window + 1)
    if tail is None:
        return _missing_data(
            "REALIZED_VOLATILITY",
            as_of,
            f"a close within the last {window + 1} sessions is missing",
        )
    returns = [(tail[i] - tail[i - 1]) / tail[i - 1] for i in range(1, len(tail))]
    mean = sum(returns, Decimal(0)) / Decimal(len(returns))
    variance = sum(((r - mean) ** 2 for r in returns), Decimal(0)) / Decimal(len(returns))
    stdev = variance.sqrt()
    value = stdev * Decimal(252).sqrt() * Decimal(100) if annualize else stdev * Decimal(100)
    return _ok("REALIZED_VOLATILITY", value, as_of, window=str(window), annualized=str(annualize))


def rolling_volume(volumes: list[int | None], window: int, as_of: date) -> IndicatorResult:
    if len(volumes) < window:
        return _insufficient_history("ROLLING_VOLUME", as_of, window, len(volumes))
    tail = volumes[-window:]
    if any(v is None for v in tail):
        return _missing_data(
            "ROLLING_VOLUME", as_of, f"a volume within the last {window} sessions is missing"
        )
    value = Decimal(sum(tail)) / Decimal(window)  # type: ignore[arg-type]
    return _ok("ROLLING_VOLUME", value, as_of, window=str(window))


def relative_strength(
    instrument_closes: list[Decimal | None],
    benchmark_closes: list[Decimal | None],
    window: int,
    as_of: date,
) -> IndicatorResult:
    """`(instrument_return - benchmark_return)` over `window` trading
    days, in percentage points."""
    inst_tail = _clean_window(instrument_closes, window + 1)
    bench_tail = _clean_window(benchmark_closes, window + 1)
    if inst_tail is None or bench_tail is None:
        if len(instrument_closes) < window + 1 or len(benchmark_closes) < window + 1:
            return _insufficient_history(
                "RELATIVE_STRENGTH",
                as_of,
                window + 1,
                min(len(instrument_closes), len(benchmark_closes)),
            )
        return _missing_data(
            "RELATIVE_STRENGTH", as_of, "a close in the requested history is missing"
        )
    inst_return = (inst_tail[-1] - inst_tail[0]) / inst_tail[0]
    bench_return = (bench_tail[-1] - bench_tail[0]) / bench_tail[0]
    value = (inst_return - bench_return) * Decimal(100)
    return _ok("RELATIVE_STRENGTH", value, as_of, window=str(window))


@dataclass(frozen=True)
class SupportResistanceResult:
    support: IndicatorResult
    resistance: IndicatorResult


def support_resistance(
    highs: list[Decimal | None], lows: list[Decimal | None], window: int, as_of: date
) -> SupportResistanceResult:
    high_tail = _clean_window(highs, window)
    low_tail = _clean_window(lows, window)
    if high_tail is None or low_tail is None:
        if len(highs) < window or len(lows) < window:
            insufficient = _insufficient_history(
                "SUPPORT_RESISTANCE", as_of, window, min(len(highs), len(lows))
            )
            return SupportResistanceResult(insufficient, insufficient)
        missing = _missing_data("SUPPORT_RESISTANCE", as_of, "a high/low in the window is missing")
        return SupportResistanceResult(missing, missing)
    return SupportResistanceResult(
        support=_ok("SUPPORT", min(low_tail), as_of, window=str(window)),
        resistance=_ok("RESISTANCE", max(high_tail), as_of, window=str(window)),
    )


def trend(
    closes: list[Decimal | None], short_window: int, long_window: int, as_of: date
) -> IndicatorResult:
    """`UP` (1), `DOWN` (-1), or `FLAT` (0) by comparing the short and
    long SMAs — encoded numerically so the result composes with other
    numeric components without a separate string-status branch."""
    short = sma(closes, short_window, as_of)
    long_ = sma(closes, long_window, as_of)
    if short.status != "OK" or long_.status != "OK":
        return _insufficient_history("TREND", as_of, long_window, len(closes))
    assert short.value is not None and long_.value is not None
    if short.value > long_.value:
        value = Decimal(1)
    elif short.value < long_.value:
        value = Decimal(-1)
    else:
        value = Decimal(0)
    return _ok("TREND", value, as_of, short_window=str(short_window), long_window=str(long_window))


def momentum(closes: list[Decimal | None], window: int, as_of: date) -> IndicatorResult:
    tail = _clean_window(closes, window + 1)
    if tail is None:
        if len(closes) < window + 1:
            return _insufficient_history("MOMENTUM", as_of, window + 1, len(closes))
        return _missing_data("MOMENTUM", as_of, "a close in the requested history is missing")
    if tail[0] == 0:
        return _missing_data("MOMENTUM", as_of, "starting close is zero")
    value = ((tail[-1] - tail[0]) / tail[0]) * Decimal(100)
    return _ok("MOMENTUM", value, as_of, window=str(window))


def liquidity(
    volumes: list[int | None], closes: list[Decimal | None], window: int, as_of: date
) -> IndicatorResult:
    """Average daily dollar volume — `avg(volume * close)` over
    `window` sessions."""
    if len(volumes) < window or len(closes) < window:
        return _insufficient_history("LIQUIDITY", as_of, window, min(len(volumes), len(closes)))
    vol_tail = volumes[-window:]
    close_tail = closes[-window:]
    if any(v is None for v in vol_tail) or any(c is None for c in close_tail):
        return _missing_data("LIQUIDITY", as_of, "a volume/close in the window is missing")
    clean_vols: list[int] = vol_tail  # type: ignore[assignment]
    clean_closes: list[Decimal] = close_tail  # type: ignore[assignment]
    dollar_volumes = [Decimal(v) * c for v, c in zip(clean_vols, clean_closes, strict=True)]
    value = sum(dollar_volumes, Decimal(0)) / Decimal(window)
    return _ok("LIQUIDITY", value, as_of, window=str(window))


def correlation(
    series_a: list[Decimal | None], series_b: list[Decimal | None], as_of: date
) -> IndicatorResult:
    """Pearson correlation of the two series' simple returns."""
    n = min(len(series_a), len(series_b))
    if n < 3:
        return _insufficient_history("CORRELATION", as_of, 3, n)
    a_tail = _clean_window(series_a, n)
    b_tail = _clean_window(series_b, n)
    if a_tail is None or b_tail is None:
        return _missing_data("CORRELATION", as_of, "a value in one of the two series is missing")
    a_returns = [(a_tail[i] - a_tail[i - 1]) / a_tail[i - 1] for i in range(1, len(a_tail))]
    b_returns = [(b_tail[i] - b_tail[i - 1]) / b_tail[i - 1] for i in range(1, len(b_tail))]
    if len(a_returns) < 2:
        return _insufficient_history("CORRELATION", as_of, 3, n)

    mean_a = sum(a_returns, Decimal(0)) / Decimal(len(a_returns))
    mean_b = sum(b_returns, Decimal(0)) / Decimal(len(b_returns))
    covariance = sum(
        ((x - mean_a) * (y - mean_b) for x, y in zip(a_returns, b_returns, strict=True)), Decimal(0)
    )
    var_a = sum(((x - mean_a) ** 2 for x in a_returns), Decimal(0))
    var_b = sum(((y - mean_b) ** 2 for y in b_returns), Decimal(0))
    denominator = (var_a * var_b).sqrt()
    if denominator == 0:
        return _missing_data("CORRELATION", as_of, "zero variance in one of the two series")
    value = covariance / denominator
    return _ok("CORRELATION", value, as_of)
