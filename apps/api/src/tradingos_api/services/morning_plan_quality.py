"""Morning-plan quality analytics (Revision Prompt 12) — a read-only
composition over Revision Prompt 9's already-real, already-populated
`MorningPlanRun`/`MorningPlanVersion`/`MorningPlanQualityCheck`/
`MorningPlanItem` data (unlike most of this revision's other services,
this one has no "dead/seed-only table" gap to fill — Prompt 9 already
writes real rows on every plan generation)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    BrokerSubmissionOutcome,
    MorningPlanRunStatus,
    MorningPlanVersionLabel,
    OrderApprovalStatus,
    PlanCompletenessStatus,
    TradeStatus,
)
from tradingos_api.models.execution import Trade
from tradingos_api.models.morning_plan import (
    MorningPlanItem,
    MorningPlanQualityCheck,
    MorningPlanRun,
    MorningPlanSection,
    MorningPlanVersion,
)
from tradingos_api.models.order_authority import BrokerSubmissionAttempt, OrderApproval
from tradingos_api.models.recommendations import RecommendationAttribution
from tradingos_api.services.performance_metrics import TradeStatsResult, compute_trade_stats

CALCULATION_VERSION = "v1"


@dataclass(frozen=True)
class MorningPlanQualitySummary:
    total_runs: int
    completed_runs: int
    failed_runs: int
    on_time_rate_pct: Decimal | None
    """A run counts as "on time" when it actually ran on its own
    `plan_date` (never a day late/early) — the one timing signal
    available without a separate "scheduled at" column; see this
    module's docstring for why a stricter intraday SLA can't be
    computed from the current schema."""
    complete_final_rate_pct: Decimal | None
    """Share of `FINAL` versions whose `completeness_status` is
    `COMPLETE` — `PRELIMINARY`/`AD_HOC`/`CORRECTION` versions are
    excluded, since only the day's official plan is meant to be
    complete by the time it's delivered."""
    check_pass_rate_pct: Decimal | None
    stale_data_check_pass_rate_pct: Decimal | None
    """Same pass-rate computation restricted to checks whose
    `check_name` names a staleness condition — `None` (not 100%) when
    no such check has ever run, so an untested claim of freshness is
    never confused with a verified one."""
    action_days: int
    no_action_days: int


def get_morning_plan_quality_summary(
    db: Session, *, since: date | None = None
) -> MorningPlanQualitySummary:
    runs_stmt = select(MorningPlanRun)
    if since is not None:
        runs_stmt = runs_stmt.where(MorningPlanRun.plan_date >= since)
    runs = db.scalars(runs_stmt).all()

    completed = [r for r in runs if r.status == MorningPlanRunStatus.COMPLETED]
    failed = [r for r in runs if r.status == MorningPlanRunStatus.FAILED]
    on_time = [r for r in completed if r.started_at.date() == r.plan_date]
    on_time_rate = (
        Decimal(len(on_time)) / Decimal(len(completed)) * Decimal(100) if completed else None
    )

    final_versions_stmt = select(MorningPlanVersion).where(
        MorningPlanVersion.version_label == MorningPlanVersionLabel.FINAL
    )
    if since is not None:
        final_versions_stmt = final_versions_stmt.where(MorningPlanVersion.plan_date >= since)
    final_versions = db.scalars(final_versions_stmt).all()
    complete_finals = [
        v for v in final_versions if v.completeness_status == PlanCompletenessStatus.COMPLETE
    ]
    complete_rate = (
        Decimal(len(complete_finals)) / Decimal(len(final_versions)) * Decimal(100)
        if final_versions
        else None
    )

    # Every version (not only FINAL) contributes to the check pass rate
    # — a PRELIMINARY run's quality checks are just as real a signal.
    checks_stmt = select(MorningPlanQualityCheck)
    if since is not None:
        checks_stmt = checks_stmt.join(
            MorningPlanVersion,
            MorningPlanQualityCheck.morning_plan_version_id == MorningPlanVersion.id,
        ).where(MorningPlanVersion.plan_date >= since)
    checks = db.scalars(checks_stmt).all()
    check_pass_rate = (
        Decimal(sum(1 for c in checks if c.passed)) / Decimal(len(checks)) * Decimal(100)
        if checks
        else None
    )
    stale_checks = [c for c in checks if "STALE" in c.check_name.upper()]
    stale_pass_rate = (
        Decimal(sum(1 for c in stale_checks if c.passed))
        / Decimal(len(stale_checks))
        * Decimal(100)
        if stale_checks
        else None
    )

    final_version_ids = [v.id for v in final_versions]
    action_days = 0
    no_action_days = 0
    if final_version_ids:
        items_by_version: dict[uuid.UUID, list[MorningPlanItem]] = {}
        sections = db.scalars(
            select(MorningPlanSection).where(
                MorningPlanSection.morning_plan_version_id.in_(final_version_ids)
            )
        ).all()
        section_ids = [s.id for s in sections]
        if section_ids:
            items = db.scalars(
                select(MorningPlanItem).where(
                    MorningPlanItem.morning_plan_section_id.in_(section_ids)
                )
            ).all()
            section_to_version = {s.id: s.morning_plan_version_id for s in sections}
            for item in items:
                version_id = section_to_version[item.morning_plan_section_id]
                items_by_version.setdefault(version_id, []).append(item)
        for version_id in final_version_ids:
            has_action = any(
                item.action_label is not None for item in items_by_version.get(version_id, [])
            )
            if has_action:
                action_days += 1
            else:
                no_action_days += 1

    return MorningPlanQualitySummary(
        total_runs=len(runs),
        completed_runs=len(completed),
        failed_runs=len(failed),
        on_time_rate_pct=on_time_rate,
        complete_final_rate_pct=complete_rate,
        check_pass_rate_pct=check_pass_rate,
        stale_data_check_pass_rate_pct=stale_pass_rate,
        action_days=action_days,
        no_action_days=no_action_days,
    )


@dataclass(frozen=True)
class SectionResults:
    section_key: str
    stats: TradeStatsResult


def get_realized_results_by_section(db: Session) -> list[SectionResults]:
    """Joins each `FINAL` plan's `MorningPlanItem.recommendation_version_id`
    through `RecommendationAttribution` to whatever closed `Trade` it
    eventually produced — a section with no closed trades yet reports an
    empty (not fabricated) `TradeStatsResult` via `compute_trade_stats([])`."""
    sections = db.scalars(select(MorningPlanSection)).all()
    section_ids_by_key: dict[str, list[uuid.UUID]] = {}
    for s in sections:
        section_ids_by_key.setdefault(s.section_key.value, []).append(s.id)

    results: list[SectionResults] = []
    for key, ids in sorted(section_ids_by_key.items()):
        items = db.scalars(
            select(MorningPlanItem).where(
                MorningPlanItem.morning_plan_section_id.in_(ids),
                MorningPlanItem.recommendation_version_id.is_not(None),
            )
        ).all()
        version_ids = [
            item.recommendation_version_id for item in items if item.recommendation_version_id
        ]
        if not version_ids:
            results.append(SectionResults(key, compute_trade_stats([])))
            continue

        pnls = db.scalars(
            select(Trade.realized_pnl)
            .join(RecommendationAttribution, RecommendationAttribution.trade_id == Trade.id)
            .where(
                RecommendationAttribution.recommendation_version_id.in_(version_ids),
                Trade.status == TradeStatus.CLOSED,
                Trade.realized_pnl.is_not(None),
            )
        ).all()
        results.append(SectionResults(key, compute_trade_stats([p for p in pnls if p is not None])))
    return results


@dataclass(frozen=True)
class ApprovalConversionResult:
    total_approvals: int
    approved: int
    denied_or_expired: int
    approval_to_submission_rate_pct: Decimal | None
    denial_reasons: dict[str, int]


def get_approval_conversion(db: Session) -> ApprovalConversionResult:
    """ "Approval-to-fill conversion" and "rejected/expired proposal
    reasons" — Prompt 12's own required morning-plan-quality metrics.
    A real submission is a `BrokerSubmissionAttempt.outcome=SUCCEEDED`
    row for that approval (Revision Prompt 10's own broker-boundary
    audit trail) — never inferred from `Order`/`Position` state, since
    `services/order_execution.py` is the only writer of that outcome and
    already records it precisely for this purpose."""
    approvals = db.scalars(select(OrderApproval)).all()
    approved = [a for a in approvals if a.status == OrderApprovalStatus.APPROVED]
    denied_or_expired = [
        a
        for a in approvals
        if a.status in (OrderApprovalStatus.REJECTED, OrderApprovalStatus.EXPIRED)
    ]

    approved_ids = [a.id for a in approved]
    succeeded_approval_ids: set[uuid.UUID] = set()
    if approved_ids:
        succeeded_approval_ids = set(
            db.scalars(
                select(BrokerSubmissionAttempt.order_approval_id).where(
                    BrokerSubmissionAttempt.order_approval_id.in_(approved_ids),
                    BrokerSubmissionAttempt.outcome == BrokerSubmissionOutcome.SUCCEEDED,
                )
            ).all()
        )

    conversion_rate = (
        Decimal(len(succeeded_approval_ids)) / Decimal(len(approved)) * Decimal(100)
        if approved
        else None
    )

    denial_reasons: dict[str, int] = {}
    for approval in denied_or_expired:
        reason = approval.status.value
        denial_reasons[reason] = denial_reasons.get(reason, 0) + 1

    return ApprovalConversionResult(
        total_approvals=len(approvals),
        approved=len(approved),
        denied_or_expired=len(denied_or_expired),
        approval_to_submission_rate_pct=conversion_rate,
        denial_reasons=denial_reasons,
    )
