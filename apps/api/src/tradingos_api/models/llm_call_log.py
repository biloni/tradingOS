from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base
from tradingos_api.db.json_type import PORTABLE_JSON


class LLMCallLog(Base):
    """Every LLM call is logged here — no exceptions (principle 8/9): prompt
    version, model, token counts, and cost, so a past recommendation can
    always be traced back to the exact prompt that produced it and every
    call's cost is auditable. Written only from services/ask.py's
    orchestration loop, once per Anthropic API call (a single /api/v1/ask
    request can produce several rows if the tool-use loop takes multiple
    turns)."""

    __tablename__ = "llm_call_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_version: Mapped[str] = mapped_column(sa.String(20))
    model: Mapped[str] = mapped_column(sa.String(50))
    input_tokens: Mapped[int] = mapped_column(sa.Integer)
    output_tokens: Mapped[int] = mapped_column(sa.Integer)
    cost_usd: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6))
    request_payload: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    response_payload: Mapped[dict[str, Any]] = mapped_column(PORTABLE_JSON)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
