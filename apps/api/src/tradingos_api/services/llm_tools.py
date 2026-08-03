"""Schema-validated tool dispatcher for the /api/v1/ask endpoint.

Five typed, side-effect-free-except-one tools the LLM can call
(principle 7: the model never executes SQL or arbitrary code — every
argument is pydantic-validated against an explicit allow-list before any
DB access happens). `compute_recommendation` is the sole exception to
"side-effect-free": it both computes the deterministic score (via
services/scoring.py) and persists exactly one `Recommendation` row, per
ADR-018 — generating a recommendation *is* the requested action, and it's
fully deterministic/auditable, unlike a real side effect such as placing
an order (which stays behind Phase 3's separate propose/confirm gate).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.indicator import Indicator
from tradingos_api.models.recommendation import Recommendation, RecommendationStatus
from tradingos_api.models.symbol import AssetType, Symbol
from tradingos_api.services.indicators import FORMULA_VERSION
from tradingos_api.services.price_bars import get_latest_price_bars
from tradingos_api.services.scoring import compute_score
from tradingos_api.services.strategy import get_or_create_default_strategy_version


class UnknownToolError(RuntimeError):
    """Raised when the model requests a tool name outside the allow-list."""


class RecommendationDraft(BaseModel):
    """What `compute_recommendation` hands back to the orchestration loop
    (services/ask.py) so it can attach the rationale text once the model
    finishes its turn — the row is already persisted by the time this
    exists, this is just a pointer + the data needed to render it."""

    recommendation_id: int
    symbol_ticker: str
    score: str
    confidence: str
    signal_breakdown: dict[str, int]


class ToolExecutionResult(BaseModel):
    tool_name: str
    output: dict[str, Any]
    recommendation_draft: RecommendationDraft | None = None


class QuerySymbolsArgs(BaseModel):
    tickers: list[str] | None = Field(
        default=None, description="Optional ticker filter, e.g. ['AAPL', 'MSFT']."
    )
    asset_type: str | None = Field(default=None, description="Optional filter: EQUITY or ETF.")


class GetPriceSummaryArgs(BaseModel):
    ticker: str
    lookback_days: int = Field(default=30, ge=1, le=365)


class GetIndicatorsArgs(BaseModel):
    ticker: str


class GetRecommendationsArgs(BaseModel):
    ticker: str | None = Field(default=None)
    status: str | None = Field(default=None, description="ACTIVE or SUPERSEDED.")
    limit: int = Field(default=10, ge=1, le=50)


class ComputeRecommendationArgs(BaseModel):
    ticker: str


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "query_symbols",
        "description": (
            "List tracked symbols, optionally filtered by ticker list or asset type. "
            "Returns id, ticker, name, exchange, asset_type for each match."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of tickers to filter to, e.g. ['AAPL', 'MSFT'].",
                },
                "asset_type": {"type": "string", "description": "Optional filter: EQUITY or ETF."},
            },
        },
    },
    {
        "name": "get_price_summary",
        "description": (
            "Get recent price history summary (latest close, period high/low, simple "
            "return) for one symbol over a lookback window."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "lookback_days": {
                    "type": "integer",
                    "description": "Number of calendar days to look back, default 30.",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_indicators",
        "description": (
            "Get the latest computed technical indicators (SMA_20, SMA_50, RSI_14, "
            "MACD_LINE, MACD_SIGNAL, BB_MID, etc.) for one symbol."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_recommendations",
        "description": (
            "List previously generated recommendations, optionally filtered by ticker "
            "or status (ACTIVE/SUPERSEDED)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "status": {"type": "string", "description": "ACTIVE or SUPERSEDED."},
                "limit": {"type": "integer", "description": "Max rows to return, default 10."},
            },
        },
    },
    {
        "name": "compute_recommendation",
        "description": (
            "Compute a fresh deterministic swing-trade alignment score for one symbol "
            "from its current indicators and persist it as a new recommendation. Use "
            "this when the user asks for a recommendation, score, or analysis of a "
            "specific symbol."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
]

_ARG_MODELS: dict[str, type[BaseModel]] = {
    "query_symbols": QuerySymbolsArgs,
    "get_price_summary": GetPriceSummaryArgs,
    "get_indicators": GetIndicatorsArgs,
    "get_recommendations": GetRecommendationsArgs,
    "compute_recommendation": ComputeRecommendationArgs,
}


def _get_symbol_by_ticker(session: Session, ticker: str) -> Symbol | None:
    stmt = select(Symbol).where(Symbol.ticker == ticker.upper())
    return session.execute(stmt).scalar_one_or_none()


def _query_symbols(session: Session, args: QuerySymbolsArgs) -> dict[str, Any]:
    stmt = select(Symbol)
    if args.tickers:
        upper_tickers = [t.upper() for t in args.tickers]
        stmt = stmt.where(Symbol.ticker.in_(upper_tickers))
    if args.asset_type:
        try:
            asset_type_enum = AssetType(args.asset_type.upper())
        except ValueError:
            return {"error": f"Invalid asset_type '{args.asset_type}'. Must be EQUITY or ETF."}
        stmt = stmt.where(Symbol.asset_type == asset_type_enum)

    symbols = session.execute(stmt.order_by(Symbol.ticker)).scalars().all()
    return {
        "symbols": [
            {
                "id": s.id,
                "ticker": s.ticker,
                "name": s.name,
                "exchange": s.exchange,
                "asset_type": s.asset_type.value,
            }
            for s in symbols
        ]
    }


def _get_price_summary(session: Session, args: GetPriceSummaryArgs) -> dict[str, Any]:
    symbol = _get_symbol_by_ticker(session, args.ticker)
    if symbol is None:
        return {"error": f"No symbol found for ticker '{args.ticker}'."}

    end = date.today()
    start = end - timedelta(days=args.lookback_days)
    bars = get_latest_price_bars(session, symbol.id, start, end)
    if not bars:
        return {
            "error": (
                f"No price history found for '{args.ticker}' in the last {args.lookback_days} days."
            )
        }

    latest = bars[-1]
    earliest = bars[0]
    high = max(b.high for b in bars)
    low = min(b.low for b in bars)
    simple_return = (
        (latest.close - earliest.close) / earliest.close if earliest.close != 0 else Decimal(0)
    )

    return {
        "ticker": symbol.ticker,
        "as_of": latest.as_of.isoformat(),
        "latest_close": str(latest.close),
        "period_high": str(high),
        "period_low": str(low),
        "period_start": earliest.as_of.isoformat(),
        "simple_return_pct": str((simple_return * Decimal(100)).quantize(Decimal("0.01"))),
        "bars_used": len(bars),
    }


def _latest_indicators_for_symbol(
    session: Session, symbol_id: int
) -> tuple[date, dict[str, Decimal]]:
    """Returns (as_of, {indicator_name: value}) for the most recent date that
    has rows under the current `FORMULA_VERSION` — mirrors the exact pattern
    used by `GET /api/v1/symbols/{ticker}/indicators` (routers/symbols.py) so
    the LLM tool and the read API never disagree on "latest"."""
    latest_as_of = session.execute(
        select(Indicator.as_of)
        .where(Indicator.symbol_id == symbol_id, Indicator.version == FORMULA_VERSION)
        .order_by(Indicator.as_of.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest_as_of is None:
        return date.today(), {}

    rows = (
        session.execute(
            select(Indicator).where(
                Indicator.symbol_id == symbol_id,
                Indicator.as_of == latest_as_of,
                Indicator.version == FORMULA_VERSION,
            )
        )
        .scalars()
        .all()
    )
    return latest_as_of, {row.indicator_name.value: row.value for row in rows}


def _get_indicators(session: Session, args: GetIndicatorsArgs) -> dict[str, Any]:
    symbol = _get_symbol_by_ticker(session, args.ticker)
    if symbol is None:
        return {"error": f"No symbol found for ticker '{args.ticker}'."}

    as_of, values = _latest_indicators_for_symbol(session, symbol.id)
    if not values:
        return {"error": f"No indicators computed yet for '{args.ticker}'."}

    return {
        "ticker": symbol.ticker,
        "as_of": as_of.isoformat(),
        "indicators": {name: str(value) for name, value in values.items()},
    }


def _get_recommendations(session: Session, args: GetRecommendationsArgs) -> dict[str, Any]:
    stmt = select(Recommendation).order_by(Recommendation.generated_at.desc()).limit(args.limit)
    if args.ticker:
        symbol = _get_symbol_by_ticker(session, args.ticker)
        if symbol is None:
            return {"error": f"No symbol found for ticker '{args.ticker}'."}
        stmt = stmt.where(Recommendation.symbol_id == symbol.id)
    if args.status:
        try:
            status_enum = RecommendationStatus(args.status.upper())
        except ValueError:
            return {"error": f"Invalid status '{args.status}'. Must be ACTIVE or SUPERSEDED."}
        stmt = stmt.where(Recommendation.status == status_enum)

    rows = session.execute(stmt).scalars().all()
    symbol_ids = {r.symbol_id for r in rows}
    symbols_by_id = {
        s.id: s
        for s in session.execute(select(Symbol).where(Symbol.id.in_(symbol_ids))).scalars().all()
    }
    return {
        "recommendations": [
            {
                "id": r.id,
                "ticker": (
                    symbols_by_id[r.symbol_id].ticker if r.symbol_id in symbols_by_id else None
                ),
                "generated_at": r.generated_at.isoformat(),
                "score": str(r.score),
                "confidence": r.confidence.value,
                "status": r.status.value,
            }
            for r in rows
        ]
    }


def _compute_recommendation(session: Session, args: ComputeRecommendationArgs) -> dict[str, Any]:
    symbol = _get_symbol_by_ticker(session, args.ticker)
    if symbol is None:
        return {"error": f"No symbol found for ticker '{args.ticker}'."}

    end = date.today()
    start = end - timedelta(days=200)
    bars = get_latest_price_bars(session, symbol.id, start, end)
    if not bars:
        return {"error": f"No price history for '{args.ticker}'; cannot compute a recommendation."}
    latest_bar = bars[-1]

    as_of, indicator_values = _latest_indicators_for_symbol(session, symbol.id)
    if not indicator_values:
        return {
            "error": (
                f"No indicators computed yet for '{args.ticker}'; cannot compute a recommendation."
            )
        }

    strategy = get_or_create_default_strategy_version(session)
    result = compute_score(latest_bar.close, indicator_values, strategy.config)

    prior_active = (
        session.execute(
            select(Recommendation).where(
                Recommendation.symbol_id == symbol.id,
                Recommendation.status == RecommendationStatus.ACTIVE,
            )
        )
        .scalars()
        .all()
    )
    for prior in prior_active:
        prior.status = RecommendationStatus.SUPERSEDED

    recommendation = Recommendation(
        symbol_id=symbol.id,
        strategy_version_id=strategy.id,
        generated_at=datetime.now(UTC),
        prompt_version="v1",
        model_response_raw="",
        score=result.score,
        deterministic_score_inputs=result.signal_breakdown,
        confidence=result.confidence,
        rationale="",
        status=RecommendationStatus.ACTIVE,
    )
    session.add(recommendation)
    session.commit()
    session.refresh(recommendation)

    draft = RecommendationDraft(
        recommendation_id=recommendation.id,
        symbol_ticker=symbol.ticker,
        score=str(result.score),
        confidence=result.confidence.value,
        signal_breakdown=result.signal_breakdown,
    )

    return {
        "ticker": symbol.ticker,
        "as_of": as_of.isoformat(),
        "recommendation_id": recommendation.id,
        "score": str(result.score),
        "confidence": result.confidence.value,
        "signal_breakdown": result.signal_breakdown,
        "_draft": draft,
    }


_HANDLERS: dict[str, Any] = {
    "query_symbols": _query_symbols,
    "get_price_summary": _get_price_summary,
    "get_indicators": _get_indicators,
    "get_recommendations": _get_recommendations,
    "compute_recommendation": _compute_recommendation,
}


def execute_tool(
    session: Session, tool_name: str, arguments: dict[str, Any]
) -> ToolExecutionResult:
    """Validate `arguments` against the tool's pydantic model, dispatch to
    its handler, and return the result. Raises `UnknownToolError` for any
    name outside `TOOL_SCHEMAS`'s allow-list; pydantic's `ValidationError`
    propagates for malformed arguments (caller turns both into a tool_result
    error block sent back to the model, never a crash)."""
    if tool_name not in _ARG_MODELS:
        raise UnknownToolError(f"Unknown tool '{tool_name}'.")

    arg_model = _ARG_MODELS[tool_name]
    parsed_args = arg_model.model_validate(arguments)

    handler = _HANDLERS[tool_name]
    output = handler(session, parsed_args)

    draft: RecommendationDraft | None = None
    if isinstance(output, dict) and "_draft" in output:
        draft = output.pop("_draft")

    return ToolExecutionResult(tool_name=tool_name, output=output, recommendation_draft=draft)
