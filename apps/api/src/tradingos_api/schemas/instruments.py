from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from tradingos_api.models.enums import AssetType, InstrumentValidationStatus


class InstrumentResponse(BaseModel):
    id: uuid.UUID
    ticker: str
    name: str
    exchange: str
    asset_type: AssetType
    active: bool

    model_config = {"from_attributes": True}


class ValidationEventResponse(BaseModel):
    id: uuid.UUID
    raw_input: str
    status: InstrumentValidationStatus
    canonical_instrument_id: uuid.UUID | None
    reason: str
    source: str
    checked_at: datetime

    model_config = {"from_attributes": True}


class ValidateRequest(BaseModel):
    raw_input: str


class ValidateResponse(BaseModel):
    status: InstrumentValidationStatus
    instrument: InstrumentResponse | None
    reason: str
