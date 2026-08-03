from pydantic import BaseModel, ConfigDict

from tradingos_api.models.symbol import AssetType


class SymbolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str
    exchange: str
    asset_type: AssetType
    active: bool
