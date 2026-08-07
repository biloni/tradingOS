"""Side-by-side Investment vs. Tactical view (Revision Prompt 6): "For
the same symbol, show investment and tactical conclusions side by side
and explain why they may differ." The explanation is deterministic,
templated text — never an LLM call — matching this project's existing
discipline that anything shown as a *reason* for a decision-relevant
comparison is computed, not synthesized on demand (the same spirit as
`services/market_regime.py`'s classification explanations)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import RecommendationMode, RecommendationStatus
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion

_STRUCTURAL_EXPLANATION = (
    "The Investment Committee and Tactical Trading Desk never share a conclusion or a "
    "horizon by design. The Investment Committee weighs ~3-24 month evidence (business "
    "quality, valuation versus history/sector/growth, durability, long-term relative "
    "strength) into a thesis with its own review date. The Tactical Trading Desk weighs "
    "~1-10 trading day evidence (technical setup, earnings-event risk, momentum, gap "
    "history) into a setup with its own holding window. A name can be a long-term hold "
    "with no tactical setup, a short-term trade with no long-term thesis, or both/neither "
    "at once — agreement or disagreement between the two lanes on any given day is "
    "coincidental to their independent analyses, never a shared judgment."
)


@dataclass(frozen=True)
class LaneConclusion:
    recommendation_id: uuid.UUID
    lane_action: str | None
    confidence: str
    rationale: str
    horizon_days_min: int | None
    horizon_days_max: int | None
    review_date: str | None
    generated_at: str


@dataclass(frozen=True)
class SideBySideView:
    instrument_id: uuid.UUID
    investment: LaneConclusion | None
    tactical: LaneConclusion | None
    divergence_explanation: str


def _latest_active_version(
    db: Session, instrument_id: uuid.UUID, mode: RecommendationMode
) -> LaneConclusion | None:
    row = db.execute(
        select(Recommendation, RecommendationVersion)
        .join(RecommendationVersion, RecommendationVersion.recommendation_id == Recommendation.id)
        .where(
            Recommendation.instrument_id == instrument_id,
            Recommendation.mode == mode,
            Recommendation.status == RecommendationStatus.ACTIVE,
        )
        .order_by(RecommendationVersion.version_number.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    recommendation, version = row
    return LaneConclusion(
        recommendation_id=recommendation.id,
        lane_action=version.lane_action,
        confidence=version.confidence.value,
        rationale=version.rationale,
        horizon_days_min=version.horizon_days_min,
        horizon_days_max=version.horizon_days_max,
        review_date=version.review_date.isoformat() if version.review_date else None,
        generated_at=version.generated_at.isoformat(),
    )


def _specific_divergence_note(
    investment: LaneConclusion | None, tactical: LaneConclusion | None
) -> str:
    if investment is None and tactical is None:
        return "Neither lane has an active recommendation for this symbol yet."
    if investment is None:
        return "Only the Tactical Trading Desk has an active recommendation for this symbol."
    if tactical is None:
        return "Only the Investment Committee has an active recommendation for this symbol."
    investment_positive = investment.lane_action in ("INVEST_BUY", "INVEST_ADD")
    tactical_positive = tactical.lane_action in ("TRADE_ENTER", "TRADE_ADD_CONFIRMED")
    if investment_positive and not tactical_positive:
        return (
            f"Investment is constructive ({investment.lane_action}) on the multi-year business "
            f"case, but Tactical is not currently proposing a short-term entry "
            f"({tactical.lane_action}) — a good long-term hold doesn't require a good "
            "near-term earnings setup."
        )
    if tactical_positive and not investment_positive:
        return (
            f"Tactical has identified a near-term setup ({tactical.lane_action}), but "
            f"Investment is not currently constructive on the multi-year case "
            f"({investment.lane_action}) — a tradeable short-term setup doesn't require a "
            "long-term thesis."
        )
    if investment_positive and tactical_positive:
        return (
            "Both lanes currently lean constructive, but independently — Investment on the "
            "3-24 month business case, Tactical on the 1-10 trading day setup. This is not a "
            "shared conclusion; either could reverse without affecting the other."
        )
    return (
        f"Investment ({investment.lane_action}) and Tactical ({tactical.lane_action}) are "
        "both currently non-positive, reached independently from different evidence."
    )


def get_side_by_side_view(db: Session, instrument_id: uuid.UUID) -> SideBySideView:
    investment = _latest_active_version(db, instrument_id, RecommendationMode.INVESTMENT)
    tactical = _latest_active_version(db, instrument_id, RecommendationMode.TACTICAL)
    explanation = f"{_specific_divergence_note(investment, tactical)}\n\n{_STRUCTURAL_EXPLANATION}"
    return SideBySideView(
        instrument_id=instrument_id,
        investment=investment,
        tactical=tactical,
        divergence_explanation=explanation,
    )
