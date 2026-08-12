"""Schema-validated tool dispatcher for `POST /api/v1/ask` (ADR-019),
rebuilt against the current post-Phase-8 schema. Three typed,
read-only tools the LLM can call — the model never executes SQL or
sees a database connection; every argument is pydantic-validated
against an explicit allow-list before any query runs (principle 7 of
the original MVP, preserved here). Unlike the deleted MVP's
`compute_recommendation`, none of these tools write anything —
recommendations already exist as real, committee-generated rows
(`services/committee_orchestrator.py`); `/ask` only ever reads them.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, cast

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import RecommendationMode
from tradingos_api.models.market_evidence import EarningsEvent
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument
from tradingos_api.schemas.ask import RecommendationSummary


class UnknownToolError(RuntimeError):
    """Raised when the model requests a tool name outside the allow-list."""


class ToolExecutionResult(BaseModel):
    tool_name: str
    output: dict[str, Any]
    recommendation_summaries: list[RecommendationSummary] = Field(default_factory=list)


class QueryInstrumentsArgs(BaseModel):
    tickers: list[str] | None = Field(
        default=None, description="Optional ticker filter, e.g. ['AAPL', 'MRVL']."
    )


class GetRecommendationsArgs(BaseModel):
    ticker: str | None = Field(default=None)
    mode: str | None = Field(default=None, description="INVESTMENT or TACTICAL.")
    limit: int = Field(default=10, ge=1, le=50)


class GetUpcomingEarningsArgs(BaseModel):
    days: int = Field(default=14, ge=1, le=180)
    ticker: str | None = Field(default=None)


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "query_instruments",
        "description": (
            "List tracked instruments, optionally filtered by ticker. Returns id, "
            "ticker, name, exchange, asset_type for each match."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of tickers to filter to, e.g. ['AAPL', 'MRVL'].",
                },
            },
        },
    },
    {
        "name": "get_recommendations",
        "description": (
            "List existing recommendations (each already produced by a real "
            "Investment Committee or Tactical Trading Desk run), optionally "
            "filtered by ticker or lane (INVESTMENT/TACTICAL). Returns each "
            "recommendation's current lane_action, confidence, score, and "
            "rationale from its latest version. This tool never generates a new "
            "recommendation — it only reads ones that already exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "mode": {"type": "string", "description": "INVESTMENT or TACTICAL."},
                "limit": {"type": "integer", "description": "Max rows to return, default 10."},
            },
        },
    },
    {
        "name": "get_upcoming_earnings",
        "description": (
            "List earnings events scheduled in the next N days (default 14), "
            "optionally filtered to one ticker. Returns report_date, "
            "fiscal_period, and eps_estimate for each match."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Look-ahead window in days, default 14.",
                },
                "ticker": {"type": "string"},
            },
        },
    },
]

_ARG_MODELS: dict[str, type[BaseModel]] = {
    "query_instruments": QueryInstrumentsArgs,
    "get_recommendations": GetRecommendationsArgs,
    "get_upcoming_earnings": GetUpcomingEarningsArgs,
}


def _get_instrument_by_ticker(db: Session, ticker: str) -> Instrument | None:
    return db.scalar(select(Instrument).where(Instrument.ticker == ticker.upper()))


def _latest_version(db: Session, recommendation_id: Any) -> RecommendationVersion | None:
    return db.scalar(
        select(RecommendationVersion)
        .where(RecommendationVersion.recommendation_id == recommendation_id)
        .order_by(RecommendationVersion.version_number.desc())
    )


def _query_instruments(db: Session, args: QueryInstrumentsArgs) -> ToolExecutionResult:
    stmt = select(Instrument)
    if args.tickers:
        upper_tickers = [t.upper() for t in args.tickers]
        stmt = stmt.where(Instrument.ticker.in_(upper_tickers))
    instruments = db.scalars(stmt.order_by(Instrument.ticker)).all()
    return ToolExecutionResult(
        tool_name="query_instruments",
        output={
            "instruments": [
                {
                    "id": str(inst.id),
                    "ticker": inst.ticker,
                    "name": inst.name,
                    "exchange": inst.exchange,
                    "asset_type": inst.asset_type.value,
                }
                for inst in instruments
            ]
        },
    )


def _get_recommendations(db: Session, args: GetRecommendationsArgs) -> ToolExecutionResult:
    stmt = select(Recommendation).order_by(Recommendation.opened_at.desc()).limit(args.limit)
    if args.ticker:
        instrument = _get_instrument_by_ticker(db, args.ticker)
        if instrument is None:
            return ToolExecutionResult(
                tool_name="get_recommendations",
                output={"error": f"No instrument found for ticker '{args.ticker}'."},
            )
        stmt = stmt.where(Recommendation.instrument_id == instrument.id)
    if args.mode:
        try:
            mode_enum = RecommendationMode(args.mode.upper())
        except ValueError:
            return ToolExecutionResult(
                tool_name="get_recommendations",
                output={"error": f"Invalid mode '{args.mode}'. Must be INVESTMENT or TACTICAL."},
            )
        stmt = stmt.where(Recommendation.mode == mode_enum)

    rows = db.scalars(stmt).all()
    output_rows: list[dict[str, Any]] = []
    summaries: list[RecommendationSummary] = []
    for rec in rows:
        instrument = db.get(Instrument, rec.instrument_id)
        ticker = instrument.ticker if instrument is not None else "UNKNOWN"
        latest = _latest_version(db, rec.id)
        output_rows.append(
            {
                "recommendation_id": str(rec.id),
                "ticker": ticker,
                "mode": rec.mode.value,
                "status": rec.status.value,
                "opened_at": rec.opened_at.isoformat(),
                "lane_action": latest.lane_action if latest else None,
                "confidence": latest.confidence.value if latest else None,
                "score": str(latest.score) if latest and latest.score is not None else None,
                "rationale": latest.rationale if latest else None,
            }
        )
        if latest is not None:
            summaries.append(
                RecommendationSummary(
                    recommendation_id=rec.id,
                    ticker=ticker,
                    mode=rec.mode.value,
                    lane_action=latest.lane_action,
                    confidence=latest.confidence,
                    score=latest.score,
                )
            )
    return ToolExecutionResult(
        tool_name="get_recommendations",
        output={"recommendations": output_rows},
        recommendation_summaries=summaries,
    )


def _get_upcoming_earnings(db: Session, args: GetUpcomingEarningsArgs) -> ToolExecutionResult:
    start = date.today()
    end = start + timedelta(days=args.days)
    stmt = (
        select(EarningsEvent)
        .where(EarningsEvent.report_date >= start, EarningsEvent.report_date <= end)
        .order_by(EarningsEvent.report_date.asc())
    )
    if args.ticker:
        instrument = _get_instrument_by_ticker(db, args.ticker)
        if instrument is None:
            return ToolExecutionResult(
                tool_name="get_upcoming_earnings",
                output={"error": f"No instrument found for ticker '{args.ticker}'."},
            )
        stmt = stmt.where(EarningsEvent.instrument_id == instrument.id)

    rows = db.scalars(stmt).all()
    events: list[dict[str, Any]] = []
    for row in rows:
        instrument = db.get(Instrument, row.instrument_id)
        events.append(
            {
                "ticker": instrument.ticker if instrument is not None else "UNKNOWN",
                "report_date": row.report_date.isoformat(),
                "fiscal_period": row.fiscal_period,
                "eps_estimate": (str(row.eps_estimate) if row.eps_estimate is not None else None),
            }
        )
    return ToolExecutionResult(
        tool_name="get_upcoming_earnings",
        output={"window_start": start.isoformat(), "window_end": end.isoformat(), "events": events},
    )


_HANDLERS: dict[str, Any] = {
    "query_instruments": _query_instruments,
    "get_recommendations": _get_recommendations,
    "get_upcoming_earnings": _get_upcoming_earnings,
}


def execute_tool(db: Session, tool_name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
    """Validate `arguments` against the tool's pydantic model, dispatch to
    its handler, and return the result. Raises `UnknownToolError` for any
    name outside `TOOL_SCHEMAS`'s allow-list; pydantic's `ValidationError`
    propagates for malformed arguments (the caller turns both into a
    `tool_result` error block sent back to the model, never a crash)."""
    if tool_name not in _ARG_MODELS:
        raise UnknownToolError(f"Unknown tool '{tool_name}'.")
    parsed_args = _ARG_MODELS[tool_name].model_validate(arguments)
    return cast(ToolExecutionResult, _HANDLERS[tool_name](db, parsed_args))
