from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.json_type import PORTABLE_JSON


class RecommendationConfidence(StrEnum):
    """A deterministic qualitative band computed in code from how many of
    the four scoring signals agree in direction (services/scoring.py) — never
    the LLM's self-reported confidence. Per principle 15, no number is
    presented as a calibrated probability until real historical outcomes
    exist to calibrate against (docs/MODEL_GOVERNANCE.md)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RecommendationStatus(StrEnum):
    """A recompute for the same symbol supersedes the prior row rather than
    deleting or updating it in place — history stays intact."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class Recommendation(Base):
    """A model inference (principle 6/7): `score` and `confidence` are
    computed by services/scoring.py — pure code, no LLM involvement.
    `rationale` is the LLM's synthesis, grounded only in the tool results it
    was given during the /api/v1/ask tool-use loop (services/ask.py) — the
    model never determines the score itself.
    """

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_id: Mapped[int] = mapped_column(sa.ForeignKey("symbols.id"))
    strategy_version_id: Mapped[int] = mapped_column(sa.ForeignKey("strategy_versions.id"))
    generated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))

    prompt_version: Mapped[str] = mapped_column(sa.String(20))
    model_response_raw: Mapped[str] = mapped_column(sa.Text)

    score: Mapped[Decimal] = mapped_column(sa.Numeric(6, 2))
    deterministic_score_inputs: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    confidence: Mapped[RecommendationConfidence] = mapped_column(
        sa.Enum(RecommendationConfidence, name="recommendation_confidence")
    )
    rationale: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[RecommendationStatus] = mapped_column(
        sa.Enum(RecommendationStatus, name="recommendation_status")
    )
