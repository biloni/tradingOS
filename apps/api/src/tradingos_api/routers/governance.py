"""Controlled learning, calibration, and strategy governance (Revision
Prompt 14). "Create governance screens for calibration, agent
evaluation, change review, approval, activation, and rollback" — this
router is those six screens' read/write surface. No endpoint here can
activate a proposal as a side effect of any other action: `/activate`
is its own endpoint, requiring `APPROVED` as a precondition
(`services/change_governance.py`'s own structural guarantee, not
re-implemented here)."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_current_user_id
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import AgentRole
from tradingos_api.models.learning import (
    ModelChangeApproval,
    ModelChangeProposal,
    StrategyDefinition,
)
from tradingos_api.schemas.common import Page
from tradingos_api.schemas.governance import (
    ActivateRequest,
    AgentEvaluationResponse,
    CalibrationBinResponse,
    DecisionRequest,
    ModelChangeApprovalResponse,
    ModelChangeProposalDetailResponse,
    ModelChangeProposalSummaryResponse,
    ProposeChangeRequest,
    ProposeStrategyParameterChangeRequest,
    RejectRequest,
    RollbackRequest,
)
from tradingos_api.services.agent_evaluation import evaluate_agent_role
from tradingos_api.services.backtest_engine import BacktestRunConfig
from tradingos_api.services.calibration import (
    CalibrationBin,
    calibration_by_event_timing,
    calibration_by_holding_period,
    calibration_by_regime,
    calibration_by_sector,
    calibration_by_strategy,
    get_closed_outcomes,
    reliability_by_confidence_band,
    reliability_by_score_band,
)
from tradingos_api.services.change_governance import (
    ProposalNotFoundError,
    activate_change,
    approve_change,
    propose_change,
    propose_strategy_parameter_change,
    reject_change,
    rollback_change,
    withdraw_change,
)
from tradingos_api.services.lifecycle import InvalidTransitionError

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])

_CALIBRATION_SEGMENTS = {
    "confidence": reliability_by_confidence_band,
    "score": reliability_by_score_band,
    "strategy": calibration_by_strategy,
    "sector": calibration_by_sector,
    "regime": calibration_by_regime,
    "event_timing": calibration_by_event_timing,
    "holding_period": calibration_by_holding_period,
}


def _bin_response(b: CalibrationBin) -> CalibrationBinResponse:
    return CalibrationBinResponse.model_validate(b)


@router.get("/calibration", response_model=list[CalibrationBinResponse])
def get_calibration(
    axis: str = Query(
        ..., description=f"One of: {', '.join(sorted(_CALIBRATION_SEGMENTS))}"
    ),
    since: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[CalibrationBinResponse]:
    """The calibration screen. `axis` selects which of Prompt 14's
    required segmentation dimensions to bucket by — ranking score,
    confidence band, strategy, sector, regime, event timing, or holding
    period — every bin sample-size gated
    (`services/calibration.py::MIN_SAMPLE_SIZE_FOR_CALIBRATION`), never
    a rate computed from a handful of outcomes."""
    grouping_fn = _CALIBRATION_SEGMENTS.get(axis)
    if grouping_fn is None:
        raise HTTPException(
            status_code=422, detail=f"axis must be one of {sorted(_CALIBRATION_SEGMENTS)}"
        )
    outcomes = get_closed_outcomes(db, since=since)
    return [_bin_response(b) for b in grouping_fn(outcomes)]


@router.get("/agent-evaluation", response_model=list[AgentEvaluationResponse])
def get_all_agent_evaluations(db: Session = Depends(get_db)) -> list[AgentEvaluationResponse]:
    """The agent evaluation screen — every committee role's six metrics,
    computed from real `AgentRun`/`AgentOpinion` history joined to real
    outcomes, never a second LLM call grading the first one."""
    return [
        AgentEvaluationResponse.model_validate(evaluate_agent_role(db, role=role))
        for role in AgentRole
    ]


@router.get("/agent-evaluation/{role}", response_model=AgentEvaluationResponse)
def get_agent_evaluation(role: AgentRole, db: Session = Depends(get_db)) -> AgentEvaluationResponse:
    return AgentEvaluationResponse.model_validate(evaluate_agent_role(db, role=role))


def _proposal_detail(
    db: Session, proposal: ModelChangeProposal
) -> ModelChangeProposalDetailResponse:
    approvals = db.scalars(
        select(ModelChangeApproval)
        .where(ModelChangeApproval.proposal_id == proposal.id)
        .order_by(ModelChangeApproval.decided_at.asc())
    ).all()
    summary = ModelChangeProposalSummaryResponse.model_validate(proposal)
    return ModelChangeProposalDetailResponse(
        **summary.model_dump(),
        evidence_package=proposal.evidence_package,
        approvals=[ModelChangeApprovalResponse.model_validate(a) for a in approvals],
    )


@router.post("/proposals", response_model=ModelChangeProposalDetailResponse, status_code=201)
def create_proposal(
    payload: ProposeChangeRequest,
    db: Session = Depends(get_db),
    owner_user_id: uuid.UUID = Depends(get_current_user_id),
) -> ModelChangeProposalDetailResponse:
    """The generic change-review intake — for a feature, threshold,
    prompt, provider, risk, or execution-policy change with no dedicated
    deep-integration helper. `evidence_package` is validated against
    Prompt 14's own "every proposal must contain" list
    (`schemas/governance.py::EvidencePackage`) before this ever reaches
    the service layer."""
    proposal = propose_change(
        db,
        owner_user_id=owner_user_id,
        subject_type=payload.subject_type,
        subject_ref_id=payload.subject_ref_id,
        description=payload.description,
        evidence_package=payload.evidence_package.model_dump(mode="json"),
    )
    db.commit()
    return _proposal_detail(db, proposal)


@router.post(
    "/proposals/strategy-parameter",
    response_model=ModelChangeProposalDetailResponse,
    status_code=201,
)
def create_strategy_parameter_proposal(
    payload: ProposeStrategyParameterChangeRequest,
    db: Session = Depends(get_db),
    owner_user_id: uuid.UUID = Depends(get_current_user_id),
) -> ModelChangeProposalDetailResponse:
    """The deep-integration path — a change to the backtest engine's own
    `BacktestRunConfig` parameters for an earnings-strategy
    `StrategyDefinition`. Runs `services/change_governance.py::run_backtest_splits()`
    (train/validation/out-of-sample/walk-forward, reusing Revision
    Prompt 13's engine verbatim) for both the current and proposed
    configuration and assembles the full evidence package automatically —
    the one proposal type this router does not ask the caller to
    hand-supply backtest results for."""
    if db.get(StrategyDefinition, payload.strategy_definition_id) is None:
        raise HTTPException(status_code=404, detail="Strategy definition not found.")
    current_config = BacktestRunConfig(
        strategy_key=payload.strategy_key,
        score_threshold=payload.current_score_threshold,
        expected_move_threshold_pct=payload.current_expected_move_threshold_pct,
        normal_risk_pct=payload.current_normal_risk_pct,
    )
    proposed_config = BacktestRunConfig(
        strategy_key=payload.strategy_key,
        score_threshold=payload.proposed_score_threshold,
        expected_move_threshold_pct=payload.proposed_expected_move_threshold_pct,
        normal_risk_pct=payload.proposed_normal_risk_pct,
    )
    proposal = propose_strategy_parameter_change(
        db,
        owner_user_id=owner_user_id,
        strategy_definition_id=payload.strategy_definition_id,
        current_config=current_config,
        proposed_config=proposed_config,
        economic_rationale=payload.economic_rationale,
        costs=payload.costs,
        operational_risks=payload.operational_risks,
        rollback_plan=payload.rollback_plan,
        description=payload.description,
    )
    db.commit()
    return _proposal_detail(db, proposal)


@router.get("/proposals", response_model=Page[ModelChangeProposalSummaryResponse])
def list_proposals(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[ModelChangeProposalSummaryResponse]:
    rows = db.scalars(
        select(ModelChangeProposal).order_by(ModelChangeProposal.proposed_at.desc())
    ).all()
    items = [
        ModelChangeProposalSummaryResponse.model_validate(r) for r in rows[offset : offset + limit]
    ]
    return Page(items=items, total=len(rows), limit=limit, offset=offset)


@router.get("/proposals/{proposal_id}", response_model=ModelChangeProposalDetailResponse)
def get_proposal(
    proposal_id: uuid.UUID, db: Session = Depends(get_db)
) -> ModelChangeProposalDetailResponse:
    """The change review screen — full evidence package plus every
    approval decision recorded against this proposal."""
    proposal = db.get(ModelChangeProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return _proposal_detail(db, proposal)


@router.post("/proposals/{proposal_id}/approve", response_model=ModelChangeProposalDetailResponse)
def approve_proposal(
    proposal_id: uuid.UUID, payload: DecisionRequest, db: Session = Depends(get_db)
) -> ModelChangeProposalDetailResponse:
    """The approval screen. Approving never activates — see `/activate`."""
    try:
        proposal = approve_change(
            db, proposal_id=proposal_id, decided_by=payload.decided_by, comment=payload.comment
        )
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _proposal_detail(db, proposal)


@router.post("/proposals/{proposal_id}/reject", response_model=ModelChangeProposalDetailResponse)
def reject_proposal(
    proposal_id: uuid.UUID, payload: RejectRequest, db: Session = Depends(get_db)
) -> ModelChangeProposalDetailResponse:
    try:
        proposal = reject_change(
            db, proposal_id=proposal_id, decided_by=payload.decided_by, comment=payload.comment
        )
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _proposal_detail(db, proposal)


@router.post("/proposals/{proposal_id}/withdraw", response_model=ModelChangeProposalDetailResponse)
def withdraw_proposal(
    proposal_id: uuid.UUID, db: Session = Depends(get_db)
) -> ModelChangeProposalDetailResponse:
    try:
        proposal = withdraw_change(db, proposal_id=proposal_id)
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _proposal_detail(db, proposal)


@router.post("/proposals/{proposal_id}/activate", response_model=ModelChangeProposalDetailResponse)
def activate_proposal(
    proposal_id: uuid.UUID, payload: ActivateRequest, db: Session = Depends(get_db)
) -> ModelChangeProposalDetailResponse:
    """The activation screen — the *only* endpoint in this codebase that
    makes a proposal's change take effect. Requires `APPROVED`
    (`409` otherwise, the state machine's own guarantee that a proposal
    cannot activate itself)."""
    try:
        proposal = activate_change(
            db, proposal_id=proposal_id, activated_by=payload.activated_by
        )
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _proposal_detail(db, proposal)


@router.post("/proposals/{proposal_id}/rollback", response_model=ModelChangeProposalDetailResponse)
def rollback_proposal(
    proposal_id: uuid.UUID, payload: RollbackRequest, db: Session = Depends(get_db)
) -> ModelChangeProposalDetailResponse:
    """The rollback screen — only legal from `ACTIVATED`."""
    try:
        proposal = rollback_change(
            db,
            proposal_id=proposal_id,
            rolled_back_by=payload.rolled_back_by,
            reason=payload.reason,
        )
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _proposal_detail(db, proposal)


__all__ = ["router"]
