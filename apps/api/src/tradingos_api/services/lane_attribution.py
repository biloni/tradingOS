"""Lane attribution (Revision Prompt 8) — the thin layer around
`services/portfolio_accounting.py` that answers "which lane does this
new lot belong to" and "how should the combined broker position and the
per-lane analytical subpositions be presented together." The actual
FIFO/lane-consumption mechanics live in `portfolio_accounting.py`; this
module is about *deriving* and *disclosing* lane facts, not computing
them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from tradingos_api.models.enums import LotLane
from tradingos_api.models.execution import Position
from tradingos_api.policy.recommendation_modes import RecommendationMode
from tradingos_api.services.portfolio_accounting import (
    ApplyExecutionResult,
    SubpositionSummary,
    get_or_create_position,
    get_subpositions_by_lane,
)

CALCULATION_VERSION = "v1"


def derive_lane_from_recommendation_mode(mode: RecommendationMode | None) -> LotLane:
    """ "Attribute every new lot to INVESTMENT, TACTICAL, or
    UNCLASSIFIED" — a fill traceable to a recommendation inherits that
    recommendation's lane; a fill with no recommendation behind it
    (manual entry, CSV import with no linked recommendation) is
    `UNCLASSIFIED`, never guessed at."""
    if mode is None:
        return LotLane.UNCLASSIFIED
    return LotLane(mode.value)


@dataclass(frozen=True)
class CombinedPositionView:
    """ "Show combined broker position and separate analytical
    subpositions" — one response shape carrying both, so a UI never has
    to reconcile two separate calls itself."""

    combined_quantity: Decimal
    combined_avg_cost: Decimal
    subpositions: dict[LotLane, SubpositionSummary]


def get_combined_position_view(
    db: Session, *, account_id: uuid.UUID, instrument_id: uuid.UUID
) -> CombinedPositionView:
    position: Position = get_or_create_position(
        db, account_id=account_id, instrument_id=instrument_id
    )
    subpositions = get_subpositions_by_lane(db, account_id=account_id, instrument_id=instrument_id)
    return CombinedPositionView(
        combined_quantity=position.quantity,
        combined_avg_cost=position.avg_cost,
        subpositions=subpositions,
    )


def describe_lot_selection_certainty(result: ApplyExecutionResult) -> str:
    """The literal, user-facing disclosure text for "document broker
    limitations when tax-lot selection is not guaranteed" — a real
    broker fill event usually reports only a net quantity and price, not
    which specific lots (and therefore which lane) it closed. Called
    whenever an exit's lane attribution should be shown to a user."""
    if result.lane_selection_is_certain:
        return "This exit's lane attribution is a confirmed system record."
    return (
        "This exit's lane attribution is the system's best FIFO inference across "
        "lanes, not a broker-confirmed fact — most brokers do not report which "
        "specific tax lot (or lane) a fill actually closed."
    )
