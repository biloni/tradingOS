from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from tradingos_api.models.enums import AlertSeverity, AlertStatus, AlertType


class AlertResponse(BaseModel):
    id: uuid.UUID
    instrument_id: uuid.UUID | None
    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    title: str
    detail: str | None
    triggered_at: datetime
    expires_at: datetime | None
    dedup_key: str | None
    evidence_type: str | None
    evidence_id: uuid.UUID | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertUpdateRequest(BaseModel):
    expected_updated_at: datetime
    status: AlertStatus
