"""Persists a deterministic lane engine's output (Revision Prompt 5) into
its parent snapshot row plus one `FeatureComponentResult` per component,
using the generic subject_type/subject_id shape (ADR-015) so the
diagnostic UI (`routers/feature_diagnostics.py`) has one table to query
regardless of which lane produced the components. Append-only — each
call creates a new parent snapshot row and a fresh set of component
rows; nothing here mutates a prior run's rows, matching this project's
effective-dated/immutable-history convention used throughout.

`source` on every `FeatureComponentResult` row names the deterministic
module that computed it (never "model" or "LLM" — principle 6/7: no
LLM ever calculates a component in this layer)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from tradingos_api.models.enums import FeatureComponentStatus
from tradingos_api.models.feature_scoring import (
    FeatureComponentResult,
    InvestmentQualityFeatureSnapshot,
)
from tradingos_api.models.market_evidence import (
    EarningsFeatureSnapshot,
    PostEarningsConfirmationSnapshot,
)
from tradingos_api.services.earnings_score import TacticalScoreResult
from tradingos_api.services.investment_quality import InvestmentQualityResult
from tradingos_api.services.post_earnings_confirmation import PostEarningsConfirmationResult
from tradingos_api.services.scoring_common import ComponentResult

_TACTICAL_SOURCE = "deterministic:earnings_score"
_INVESTMENT_SOURCE = "deterministic:investment_quality"
_POST_EARNINGS_SOURCE = "deterministic:post_earnings_confirmation"


def _write_components(
    db: Session,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    components: list[ComponentResult],
    source: str,
    calculation_version: str,
    as_of: datetime,
) -> None:
    for component in components:
        db.add(
            FeatureComponentResult(
                subject_type=subject_type,
                subject_id=subject_id,
                component_key=component.component_key,
                component_order=component.component_order,
                value=component.value,
                status=FeatureComponentStatus(component.status),
                source=source,
                detail=component.detail,
                calculation_version=calculation_version,
                as_of=as_of,
            )
        )


def persist_tactical_score(
    db: Session,
    *,
    earnings_event_id: uuid.UUID,
    as_of: datetime,
    evidence_cutoff: datetime,
    result: TacticalScoreResult,
) -> EarningsFeatureSnapshot:
    """The fixed `component_*` columns on `EarningsFeatureSnapshot` predate
    this revision's precisely-named 8 components (they were an earlier,
    looser placeholder set) and are intentionally left null here —
    `total_score`/`calculation_version` are this table's summary fields;
    the named component detail lives exclusively in the
    `FeatureComponentResult` children this function writes."""
    snapshot = EarningsFeatureSnapshot(
        earnings_event_id=earnings_event_id,
        as_of=as_of,
        evidence_cutoff=evidence_cutoff,
        is_pre_event=True,
        total_score=result.total_score,
        calculation_version=result.calculation_version,
    )
    db.add(snapshot)
    db.flush()
    _write_components(
        db,
        subject_type="EarningsFeatureSnapshot",
        subject_id=snapshot.id,
        components=result.components,
        source=_TACTICAL_SOURCE,
        calculation_version=result.calculation_version,
        as_of=as_of,
    )
    return snapshot


def persist_investment_quality(
    db: Session,
    *,
    instrument_id: uuid.UUID,
    as_of: date,
    evidence_cutoff: datetime,
    result: InvestmentQualityResult,
) -> InvestmentQualityFeatureSnapshot:
    snapshot = InvestmentQualityFeatureSnapshot(
        instrument_id=instrument_id,
        as_of=as_of,
        evidence_cutoff=evidence_cutoff,
        calculation_version=result.calculation_version,
        hard_disqualified=result.hard_disqualified,
        disqualification_reason=result.disqualification_reason,
    )
    db.add(snapshot)
    db.flush()
    _write_components(
        db,
        subject_type="InvestmentQualityFeatureSnapshot",
        subject_id=snapshot.id,
        components=result.components,
        source=_INVESTMENT_SOURCE,
        calculation_version=result.calculation_version,
        as_of=evidence_cutoff,
    )
    return snapshot


def persist_post_earnings_confirmation(
    db: Session,
    *,
    earnings_event_id: uuid.UUID,
    as_of: datetime,
    evidence_cutoff: datetime,
    calculation_version: str,
    result: PostEarningsConfirmationResult,
) -> PostEarningsConfirmationSnapshot:
    snapshot = PostEarningsConfirmationSnapshot(
        earnings_event_id=earnings_event_id,
        as_of=as_of,
        evidence_cutoff=evidence_cutoff,
        results_gate_passed=result.results_gate_passed,
        guidance_gate_passed=result.guidance_gate_passed,
        market_reaction_gate_passed=result.market_reaction_gate_passed,
        all_gates_passed=result.all_gates_passed,
    )
    db.add(snapshot)
    db.flush()
    _write_components(
        db,
        subject_type="PostEarningsConfirmationSnapshot",
        subject_id=snapshot.id,
        components=result.components,
        source=_POST_EARNINGS_SOURCE,
        calculation_version=calculation_version,
        as_of=as_of,
    )
    return snapshot
