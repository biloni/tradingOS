"""Shared component-result shape (Revision Prompt 5) — both the tactical
8-component score (`services/earnings_score.py`) and the Investment
lane's component scores (`services/investment_quality.py`) return lists
of this same dataclass, matching `models.feature_scoring.FeatureComponentResult`'s
column shape one-to-one so persisting either lane's output is a
mechanical field-for-field copy, never a translation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ComponentStatus = str  # one of models.enums.FeatureComponentStatus's values


@dataclass(frozen=True)
class ComponentResult:
    component_key: str
    component_order: int
    value: Decimal | None
    status: ComponentStatus
    detail: str | None
