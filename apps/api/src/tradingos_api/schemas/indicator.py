from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer

from tradingos_api.models.indicator import IndicatorName


class IndicatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: date
    indicator_name: IndicatorName
    version: str
    value: Decimal
    computed_at: datetime

    @field_serializer("value")
    def _serialize_decimal_as_str(self, value: Decimal) -> str:
        return str(value)
