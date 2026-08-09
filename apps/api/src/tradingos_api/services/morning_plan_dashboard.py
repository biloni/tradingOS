"""The Morning Decision Dashboard read model (Revision Prompt 9) — the
top-status block plus the fixed section hierarchy, composed from
whatever `MorningPlanVersion` already exists (or doesn't) for a given
date. Purely a read/render service — it never generates a plan itself
(`services/morning_plan_generate.py` does that); this module answers
"what should the dashboard show right now," including the several ways
a plan can be legitimately *absent* (market closed, not yet generated,
generation failed).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.models.enums import MorningPlanRunStatus, MorningPlanVersionLabel
from tradingos_api.models.execution import Account, CashLedgerEntry, Position
from tradingos_api.models.identity import RiskPolicy
from tradingos_api.models.market_evidence import MarketRegimeSnapshot
from tradingos_api.models.morning_plan import MorningPlanRun, MorningPlanVersion
from tradingos_api.models.order_authority import ExecutionKillSwitchEvent
from tradingos_api.policy.order_authority import OrderAuthorityMode
from tradingos_api.services.market_calendar import countdown_to_open, resolve_trading_day

CALCULATION_VERSION = "v1"

DashboardPlanStatus = Literal["COMPLETE", "INCOMPLETE", "STALE", "FAILED", "MARKET_CLOSED"]

# A published plan older than this (relative to "now") is shown as
# STALE even if it was COMPLETE when generated — the dashboard's own
# freshness signal, distinct from the plan version's own completeness
# label (which is about evidence coverage at generation time, not
# elapsed wall-clock time since).
STALE_PLAN_AGE = timedelta(hours=6)


@dataclass(frozen=True)
class TopStatus:
    market_date: date
    is_trading_day: bool
    market_closed_reason: str | None
    countdown_to_open_seconds: int | None
    plan_status: DashboardPlanStatus
    plan_version_id: uuid.UUID | None
    plan_version_label: MorningPlanVersionLabel | None
    generated_at: datetime | None
    evidence_cutoff: datetime | None
    provider_broker_status: str
    regime_classification: str | None
    vix_proxy_level: Decimal | None
    vix_percentile: Decimal | None
    total_equity: Decimal
    cash: Decimal
    exposure_pct: Decimal
    risk_budget_pct: Decimal | None
    operating_mode: str
    kill_switch_active: bool


def _latest_version_for_date(db: Session, plan_date: date) -> MorningPlanVersion | None:
    """The most-authoritative version for the date: `FINAL`/`CORRECTION`
    outrank `PRELIMINARY`/`AD_HOC` if both exist, else whatever exists,
    newest `version_number` first."""
    versions = db.scalars(
        select(MorningPlanVersion)
        .where(MorningPlanVersion.plan_date == plan_date)
        .order_by(MorningPlanVersion.version_number.desc())
    ).all()
    if not versions:
        return None
    for label in (MorningPlanVersionLabel.CORRECTION, MorningPlanVersionLabel.FINAL):
        for v in versions:
            if v.version_label == label:
                return v
    return versions[0]


def compute_top_status(
    db: Session, *, plan_date: date, account_id: uuid.UUID, now: datetime | None = None
) -> TopStatus:
    now = now or datetime.now(UTC)
    trading_day = resolve_trading_day(plan_date)
    account = db.get(Account, account_id)
    assert account is not None

    cash = account.starting_cash + (
        db.scalar(
            select(func.coalesce(func.sum(CashLedgerEntry.amount), 0)).where(
                CashLedgerEntry.account_id == account_id
            )
        )
        or Decimal(0)
    )
    positions = db.scalars(select(Position).where(Position.account_id == account_id)).all()
    market_value = sum((p.quantity * p.avg_cost for p in positions), Decimal(0))
    total_equity = cash + market_value
    exposure_pct = (market_value / total_equity * Decimal(100)) if total_equity > 0 else Decimal(0)

    risk_policy = db.scalar(
        select(RiskPolicy).where(RiskPolicy.owner_user_id == account.owner_user_id)
    )
    risk_budget_pct = risk_policy.risk_budget_pct * Decimal(100) if risk_policy else None

    latest_kill_switch = db.scalar(
        select(ExecutionKillSwitchEvent).order_by(ExecutionKillSwitchEvent.activated_at.desc())
    )
    kill_switch_active = (
        latest_kill_switch is not None and latest_kill_switch.deactivated_at is None
    )

    try:
        mode = OrderAuthorityMode(get_settings().operating_mode)
    except ValueError:
        mode = OrderAuthorityMode.RESEARCH_ONLY

    if not trading_day.is_trading_day:
        return TopStatus(
            market_date=plan_date,
            is_trading_day=False,
            market_closed_reason=trading_day.skip_reason,
            countdown_to_open_seconds=None,
            plan_status="MARKET_CLOSED",
            plan_version_id=None,
            plan_version_label=None,
            generated_at=None,
            evidence_cutoff=None,
            provider_broker_status="N/A — market closed",
            regime_classification=None,
            vix_proxy_level=None,
            vix_percentile=None,
            total_equity=total_equity,
            cash=cash,
            exposure_pct=exposure_pct,
            risk_budget_pct=risk_budget_pct,
            operating_mode=mode.value,
            kill_switch_active=kill_switch_active,
        )

    version = _latest_version_for_date(db, plan_date)
    countdown = countdown_to_open(now, trading_day.session_open_utc)
    countdown_seconds = int(countdown.total_seconds()) if countdown is not None else None

    regime = (
        db.get(MarketRegimeSnapshot, version.regime_snapshot_id)
        if version and version.regime_snapshot_id
        else None
    )

    if version is None:
        latest_failed_run = db.scalar(
            select(MorningPlanRun)
            .where(
                MorningPlanRun.plan_date == plan_date,
                MorningPlanRun.status == MorningPlanRunStatus.FAILED,
            )
            .order_by(MorningPlanRun.started_at.desc())
        )
        plan_status: DashboardPlanStatus = "FAILED" if latest_failed_run else "INCOMPLETE"
        return TopStatus(
            market_date=plan_date,
            is_trading_day=True,
            market_closed_reason=None,
            countdown_to_open_seconds=countdown_seconds,
            plan_status=plan_status,
            plan_version_id=None,
            plan_version_label=None,
            generated_at=None,
            evidence_cutoff=None,
            provider_broker_status="unknown — no plan generated yet",
            regime_classification=None,
            vix_proxy_level=None,
            vix_percentile=None,
            total_equity=total_equity,
            cash=cash,
            exposure_pct=exposure_pct,
            risk_budget_pct=risk_budget_pct,
            operating_mode=mode.value,
            kill_switch_active=kill_switch_active,
        )

    is_stale = (now - version.generated_at) > STALE_PLAN_AGE
    plan_status = "STALE" if is_stale else version.completeness_status.value

    return TopStatus(
        market_date=plan_date,
        is_trading_day=True,
        market_closed_reason=None,
        countdown_to_open_seconds=countdown_seconds,
        plan_status=plan_status,
        plan_version_id=version.id,
        plan_version_label=version.version_label,
        generated_at=version.generated_at,
        evidence_cutoff=version.evidence_cutoff,
        provider_broker_status="OK",
        regime_classification=regime.classification.value if regime else None,
        vix_proxy_level=regime.vix_proxy_level if regime else None,
        vix_percentile=regime.vix_percentile if regime else None,
        total_equity=total_equity,
        cash=cash,
        exposure_pct=exposure_pct,
        risk_budget_pct=risk_budget_pct,
        operating_mode=mode.value,
        kill_switch_active=kill_switch_active,
    )
