"""Morning plan latest/version-history/generate/dashboard/quality-status
(Revision Prompt R3 schema + Revision Prompt 9 generation/dashboard,
docs/MORNING_PLAN_SPEC.md, ADR-047's scheduler-owned lineage).
`POST /generate` is the one endpoint that actually runs the 12-stage
orchestrator (`services/morning_plan_generate.py`) — an always-on
worker calls it (via `services/morning_plan_scheduler.py::decide_schedule()`
first) on the 05:45/06:10 schedule; a user's manual "run now" button
calls the exact same endpoint with `version_label=AD_HOC`.
`GET /dashboard` is the read-only Morning Decision Dashboard contract,
also what a Cowork scheduled task reads (never `PRELIMINARY`, only
after `FINAL` is published, docs/MORNING_PLAN_SPEC.md's Cowork section)
— no endpoint in this router ever calls a broker."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_current_user_id
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import (
    AlertDeliveryStatus as AlertDeliveryStatusEnum,
)
from tradingos_api.models.enums import (
    AlertSeverity,
    DeliveryChannel,
    MorningPlanRunStatus,
    MorningPlanVersionLabel,
)
from tradingos_api.models.execution import Account
from tradingos_api.models.morning_plan import (
    MorningPlanDeliveryEvent,
    MorningPlanItem,
    MorningPlanQualityCheck,
    MorningPlanRun,
    MorningPlanSection,
    MorningPlanVersion,
)
from tradingos_api.models.operations import Alert
from tradingos_api.schemas.common import Page
from tradingos_api.schemas.morning_plan import (
    DashboardResponse,
    GeneratePlanRequest,
    MorningPlanDeliveryEventResponse,
    MorningPlanItemResponse,
    MorningPlanQualityCheckResponse,
    MorningPlanSectionResponse,
    MorningPlanVersionDetailResponse,
    MorningPlanVersionSummaryResponse,
    TopStatusResponse,
)
from tradingos_api.services.market_calendar import DISPLAY_TIMEZONE
from tradingos_api.services.morning_plan_dashboard import compute_top_status
from tradingos_api.services.morning_plan_export import render_markdown
from tradingos_api.services.morning_plan_generate import generate_morning_plan

router = APIRouter(prefix="/api/v1/morning-plan", tags=["morning-plan"])


def _default_account(db: Session, owner_user_id: uuid.UUID) -> Account:
    account = db.scalar(select(Account).where(Account.owner_user_id == owner_user_id))
    if account is None:
        raise HTTPException(status_code=404, detail="No account exists for this user.")
    return account


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


@router.post("/generate", response_model=MorningPlanVersionDetailResponse, status_code=201)
def generate_plan(
    payload: GeneratePlanRequest,
    db: Session = Depends(get_db),
    owner_user_id: uuid.UUID = Depends(get_current_user_id),
) -> MorningPlanVersionDetailResponse:
    """Runs the real 12-stage orchestrator (Revision Prompt 9) — never
    edits or replaces an existing version, a rerun always adds a new row
    (R3's original test requirement, still true). An always-on worker's
    scheduled call and a user's manual "run now" both land here, the
    only difference being `version_label` (`PRELIMINARY`/`FINAL` for the
    schedule, `AD_HOC` for manual, `CORRECTION` for a later fix).
    `idempotency_key` (matching `MorningPlanRun.idempotency_key`'s
    existing uniqueness) makes a duplicate call — the same scheduled
    slot firing twice, or a network retry after an already-successful
    call — return the prior result rather than generating a second
    version."""
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

    account = _default_account(db, owner_user_id)
    plan_date = payload.plan_date or datetime.now(UTC).astimezone(DISPLAY_TIMEZONE).date()

    prior_max = db.scalar(
        select(MorningPlanVersion.version_number)
        .where(MorningPlanVersion.plan_date == plan_date)
        .order_by(MorningPlanVersion.version_number.desc())
    )
    next_version_number = (prior_max or 0) + 1

    now = datetime.now(UTC)
    run = MorningPlanRun(
        plan_date=plan_date,
        triggered_by=payload.triggered_by,
        status=MorningPlanRunStatus.RUNNING,
        idempotency_key=payload.idempotency_key,
        started_at=now,
    )
    db.add(run)
    db.flush()

    try:
        result = generate_morning_plan(
            db,
            run=run,
            plan_date=plan_date,
            version_label=payload.version_label,
            version_number=next_version_number,
            now=now,
            account_id=account.id,
        )
    except Exception as exc:
        run.status = MorningPlanRunStatus.FAILED
        run.completed_at = datetime.now(UTC)
        run.error_detail = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Plan generation failed: {exc}") from exc

    if result.skipped:
        run.status = MorningPlanRunStatus.COMPLETED
        run.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status_code=422,
            detail=f"No plan generated — {result.skip_reason}",
        )

    run.status = MorningPlanRunStatus.COMPLETED
    run.completed_at = datetime.now(UTC)
    assert result.version is not None

    # "In-app notification when the final plan is ready" — only for
    # FINAL (never PRELIMINARY/AD_HOC), so the notification means what
    # it says: the day's official plan, not an interim draft.
    if payload.version_label == MorningPlanVersionLabel.FINAL:
        db.add(
            Alert(
                owner_user_id=owner_user_id,
                instrument_id=None,
                severity=AlertSeverity.INFO,
                title=f"Morning plan ready — {plan_date.isoformat()}",
                detail=(
                    f"The FINAL morning decision plan for {plan_date.isoformat()} has been "
                    f"published (completeness: {result.version.completeness_status.value})."
                ),
                triggered_at=datetime.now(UTC),
            )
        )
        db.add(
            MorningPlanDeliveryEvent(
                morning_plan_version_id=result.version.id,
                channel=DeliveryChannel.IN_APP,
                status=AlertDeliveryStatusEnum.DELIVERED,
                delivered_at=datetime.now(UTC),
            )
        )

    db.commit()
    db.refresh(result.version)
    return _version_detail(db, result.version)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    owner_user_id: uuid.UUID = Depends(get_current_user_id),
    plan_date_filter: date | None = Query(default=None, alias="plan_date"),
    now_override: datetime | None = Query(
        default=None,
        alias="now",
        description="Controllable clock for tests/demo — production callers omit this.",
    ),
) -> DashboardResponse:
    """The Morning Decision Dashboard — the primary daily operating
    screen. Also the read-only contract a Cowork scheduled task calls:
    this endpoint never writes anything and has no code path into order
    creation, approval, or execution."""
    account = _default_account(db, owner_user_id)
    now = now_override or datetime.now(UTC)
    plan_date = plan_date_filter or now.astimezone(DISPLAY_TIMEZONE).date()

    top_status = compute_top_status(db, plan_date=plan_date, account_id=account.id, now=now)
    version = (
        db.get(MorningPlanVersion, top_status.plan_version_id)
        if top_status.plan_version_id
        else None
    )
    return DashboardResponse(
        top_status=TopStatusResponse.model_validate(top_status),
        version=_version_detail(db, version) if version else None,
    )


@router.get("/versions/{version_id}/export.md")
def export_version_markdown(version_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    """Printable/Markdown export (Revision Prompt 9's "Delivery"
    requirement) — a plain-text render of one immutable version, safe to
    print or paste elsewhere."""
    version = db.get(MorningPlanVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Morning plan version not found.")
    markdown = render_markdown(_version_detail(db, version))
    return Response(content=markdown, media_type="text/markdown")


@router.get("/cowork-brief", response_model=MorningPlanVersionDetailResponse)
def get_cowork_brief(
    db: Session = Depends(get_db),
    owner_user_id: uuid.UUID = Depends(get_current_user_id),
    plan_date_filter: date | None = Query(default=None, alias="plan_date"),
) -> MorningPlanVersionDetailResponse:
    """The Cowork read-only delivery contract (SS-5, ADR-049,
    docs/MORNING_PLAN_SPEC.md's Cowork section): reads and summarizes
    the `FINAL` plan **only after it has been published** — never
    `PRELIMINARY`, never a plan still being assembled, and this function
    has no code path back into order creation, approval, or execution
    (it is a `GET`, full stop). A day with no published `FINAL` yet
    returns `404`, never a `PRELIMINARY` substitute."""
    _ = owner_user_id  # single-user system (ADR-007); required only to gate access to this route
    plan_date = plan_date_filter or datetime.now(UTC).astimezone(DISPLAY_TIMEZONE).date()
    version = db.scalar(
        select(MorningPlanVersion)
        .where(
            MorningPlanVersion.plan_date == plan_date,
            MorningPlanVersion.version_label.in_(
                (MorningPlanVersionLabel.FINAL, MorningPlanVersionLabel.CORRECTION)
            ),
        )
        .order_by(MorningPlanVersion.version_number.desc())
    )
    if version is None:
        raise HTTPException(
            status_code=404,
            detail=f"No FINAL morning plan has been published yet for {plan_date.isoformat()}.",
        )
    db.add(
        MorningPlanDeliveryEvent(
            morning_plan_version_id=version.id,
            channel=DeliveryChannel.COWORK,
            status=AlertDeliveryStatusEnum.DELIVERED,
            delivered_at=datetime.now(UTC),
        )
    )
    db.commit()
    return _version_detail(db, version)
