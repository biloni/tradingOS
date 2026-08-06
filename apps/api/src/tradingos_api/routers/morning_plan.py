"""Morning plan latest/version-history/rerun/quality-status (Revision
Prompt R3, docs/MORNING_PLAN_SPEC.md, ADR-047's scheduler-owned
lineage). No plan-generation logic lives here — that is a future
scheduler job's job — `rerun` only records a new, empty
`MorningPlanVersion` (never overwriting a prior one) so the version-
history/quality-status contract can be demonstrated end to end."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.db.session import get_db
from tradingos_api.models.enums import MorningPlanRunStatus, PlanCompletenessStatus
from tradingos_api.models.morning_plan import (
    MorningPlanDeliveryEvent,
    MorningPlanItem,
    MorningPlanQualityCheck,
    MorningPlanRun,
    MorningPlanSection,
    MorningPlanVersion,
)
from tradingos_api.schemas.common import Page
from tradingos_api.schemas.morning_plan import (
    MorningPlanDeliveryEventResponse,
    MorningPlanItemResponse,
    MorningPlanQualityCheckResponse,
    MorningPlanRerunRequest,
    MorningPlanSectionResponse,
    MorningPlanVersionDetailResponse,
    MorningPlanVersionSummaryResponse,
)

router = APIRouter(prefix="/api/v1/morning-plan", tags=["morning-plan"])


def _version_detail(db: Session, version: MorningPlanVersion) -> MorningPlanVersionDetailResponse:
    sections = db.scalars(
        select(MorningPlanSection)
        .where(MorningPlanSection.morning_plan_version_id == version.id)
        .order_by(MorningPlanSection.display_order.asc())
    ).all()
    section_responses = []
    for section in sections:
        items = db.scalars(
            select(MorningPlanItem)
            .where(MorningPlanItem.morning_plan_section_id == section.id)
            .order_by(MorningPlanItem.display_order.asc())
        ).all()
        section_responses.append(
            MorningPlanSectionResponse(
                section_key=section.section_key,
                display_order=section.display_order,
                items=[MorningPlanItemResponse.model_validate(item) for item in items],
            )
        )
    quality_checks = db.scalars(
        select(MorningPlanQualityCheck).where(
            MorningPlanQualityCheck.morning_plan_version_id == version.id
        )
    ).all()
    delivery_events = db.scalars(
        select(MorningPlanDeliveryEvent).where(
            MorningPlanDeliveryEvent.morning_plan_version_id == version.id
        )
    ).all()
    return MorningPlanVersionDetailResponse(
        id=version.id,
        morning_plan_run_id=version.morning_plan_run_id,
        plan_date=version.plan_date,
        version_label=version.version_label,
        version_number=version.version_number,
        evidence_cutoff=version.evidence_cutoff,
        generated_at=version.generated_at,
        completeness_status=version.completeness_status,
        sections=section_responses,
        quality_checks=[
            MorningPlanQualityCheckResponse.model_validate(check) for check in quality_checks
        ],
        delivery_events=[
            MorningPlanDeliveryEventResponse.model_validate(event) for event in delivery_events
        ],
    )


@router.get("/latest", response_model=MorningPlanVersionDetailResponse)
def get_latest_morning_plan(db: Session = Depends(get_db)) -> MorningPlanVersionDetailResponse:
    version = db.scalar(
        select(MorningPlanVersion).order_by(
            MorningPlanVersion.plan_date.desc(), MorningPlanVersion.version_number.desc()
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="No morning plan version exists yet.")
    return _version_detail(db, version)


@router.get("/versions", response_model=Page[MorningPlanVersionSummaryResponse])
def list_morning_plan_versions(
    db: Session = Depends(get_db),
    plan_date_filter: date | None = Query(default=None, alias="plan_date"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[MorningPlanVersionSummaryResponse]:
    """Every version ever written for a given `plan_date`, newest first —
    since a rerun always adds a row rather than mutating one, this list
    is the audit trail of every plan revision that day."""
    stmt = select(MorningPlanVersion).order_by(
        MorningPlanVersion.plan_date.desc(), MorningPlanVersion.version_number.desc()
    )
    if plan_date_filter is not None:
        stmt = stmt.where(MorningPlanVersion.plan_date == plan_date_filter)
    all_rows = db.scalars(stmt).all()
    total = len(all_rows)
    page_rows = all_rows[offset : offset + limit]
    return Page(
        items=[MorningPlanVersionSummaryResponse.model_validate(v) for v in page_rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/versions/{version_id}/quality-status", response_model=list[MorningPlanQualityCheckResponse]
)
def get_quality_status(
    version_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[MorningPlanQualityCheckResponse]:
    if db.get(MorningPlanVersion, version_id) is None:
        raise HTTPException(status_code=404, detail="Morning plan version not found.")
    checks = db.scalars(
        select(MorningPlanQualityCheck).where(
            MorningPlanQualityCheck.morning_plan_version_id == version_id
        )
    ).all()
    return [MorningPlanQualityCheckResponse.model_validate(check) for check in checks]


@router.post("/rerun", response_model=MorningPlanVersionDetailResponse, status_code=201)
def rerun_morning_plan(
    payload: MorningPlanRerunRequest, db: Session = Depends(get_db)
) -> MorningPlanVersionDetailResponse:
    """Records a new run + version for `plan_date` — never edits or
    replaces an existing version (R3's explicit test requirement: "plan
    reruns create versions rather than overwrite"). No plan-generation
    logic runs here, so the new version starts empty/`INCOMPLETE` with a
    quality-check row naming why; a future scheduler job is what
    populates sections/items before marking it `COMPLETE`."""
    if payload.idempotency_key:
        existing_run = db.scalar(
            select(MorningPlanRun).where(MorningPlanRun.idempotency_key == payload.idempotency_key)
        )
        if existing_run is not None:
            existing_version = db.scalar(
                select(MorningPlanVersion).where(
                    MorningPlanVersion.morning_plan_run_id == existing_run.id
                )
            )
            if existing_version is not None:
                return _version_detail(db, existing_version)

    now = datetime.now(UTC)
    run = MorningPlanRun(
        plan_date=payload.plan_date,
        triggered_by=payload.triggered_by,
        status=MorningPlanRunStatus.RUNNING,
        idempotency_key=payload.idempotency_key,
        started_at=now,
    )
    db.add(run)
    db.flush()

    prior_max = db.scalar(
        select(MorningPlanVersion.version_number)
        .where(MorningPlanVersion.plan_date == payload.plan_date)
        .order_by(MorningPlanVersion.version_number.desc())
    )
    next_version_number = (prior_max or 0) + 1

    version = MorningPlanVersion(
        morning_plan_run_id=run.id,
        plan_date=payload.plan_date,
        version_label=payload.version_label,
        version_number=next_version_number,
        evidence_cutoff=now,
        generated_at=now,
        completeness_status=PlanCompletenessStatus.INCOMPLETE,
    )
    db.add(version)
    db.flush()
    db.add(
        MorningPlanQualityCheck(
            morning_plan_version_id=version.id,
            check_name="plan_generation_logic",
            passed=False,
            detail="No plan-generation logic exists yet (Revision Prompt R3 is schema/API only) — "
            "this version was recorded empty by the rerun endpoint.",
        )
    )
    run.status = MorningPlanRunStatus.COMPLETED
    run.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(version)
    return _version_detail(db, version)
