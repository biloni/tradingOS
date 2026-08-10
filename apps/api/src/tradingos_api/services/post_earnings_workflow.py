"""Post-earnings confirmation workflow orchestrator (Revision Prompt 11)
— the state machine wrapped around the second stage of the hybrid
earnings strategy. This module does not re-implement any scoring,
committee, or sizing logic — it sequences calls into Revision Prompt 5's
`services/post_earnings_confirmation.py`, Revision Prompt 7's
`services/post_confirmation_gate.py` and `services/recommendation_pipeline.py`,
and Revision Prompt 11's own `services/ingest_evidence.py::ingest_earnings_actuals()`.

One `PostEarningsWorkflowRun` row tracks state per
`(earnings_event, instrument, account)`, resumable by a restarted worker
rereading the row (`idempotency_key`) rather than losing track — the
required "worker restart" and "duplicate release" test categories both
follow directly from `run_post_earnings_workflow()` being a pure
re-entrant function: calling it twice with the same event/instrument/
account is always safe, and a terminal run (`CONFIRMED`/`FAILED`/
`INVALIDATED`) is returned unchanged rather than re-evaluated.

Step numbering below matches Revision Prompt 11's own POST-EARNINGS
WORKFLOW list:

 1. detect verified release -> `EarningsActualsProvider.get_actuals()`
 2. ingest and validate official results -> `ingest_earnings_actuals()`
 3. compare actuals vs. frozen pre-event consensus -> EPS/REVENUE surprise
    components
 4. compare formal guidance vs. prior guidance and frozen consensus ->
    GUIDANCE_DIRECTION component
 5. wait for the configured price-confirmation window ->
    `confirmation_window_ends_at`
 6. calculate post-confirmation features -> `compute_post_earnings_confirmation()`
 7. run the Tactical Trading Desk -> `run_recommendation_pipeline(lane=TACTICAL)`
 8. apply deterministic vetoes and portfolio risk ->
    `evaluate_post_confirmation_eligibility()` (HES-6, absolute) plus the
    pipeline's own hard-veto pass
 9. emit TRADE_ADD_CONFIRMED/TRADE_HOLD/TRADE_TAKE_PARTIAL/TRADE_EXIT/NO_ACTION
    -> the resulting `RecommendationVersion.lane_action`
10. create a new order proposal only when allowed, never submit -> the
    pipeline's existing DRAFT/`requires_approval=True` behavior
    (unchanged from Revision Prompt 7)

`PostEarningsWorkflowStatus` (see `models/enums.py`) describes the
*workflow's own* progress, not the trading decision it produces:
`WAITING_FOR_DATA` while results, guidance-frozen-consensus, or price
data remain unavailable/unconfirmed; `INVALIDATED` specifically for "the
initial reaction reversed" (Prompt 11's own invalidation rule, detected
via the `REVERSAL_FAILED_BREAKOUT` component); `FAILED` for every other
way the post-confirmation eligibility gate rejects the add (including
HES-6's absolute "never average down after a negative gap" rule); and
`CONFIRMED` once the workflow has run the Tactical Trading Desk and
published a real decision, whatever that decision turned out to be —
`TRADE_ADD_CONFIRMED` is not the only "successful" outcome; `TRADE_HOLD`
following a full, completed evaluation is just as much a `CONFIRMED`
workflow as an add.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import AlertSeverity, AlertType, PostEarningsWorkflowStatus
from tradingos_api.models.market_evidence import (
    EarningsConsensusSnapshot,
    EarningsEvent,
    EarningsGuidanceItem,
)
from tradingos_api.models.monitoring import PostEarningsWorkflowRun
from tradingos_api.policy.recommendation_modes import RecommendationMode
from tradingos_api.providers.earnings_actuals import EarningsActualsProvider
from tradingos_api.providers.llm import LLMProvider
from tradingos_api.services.alerts_engine import create_or_dedupe_alert
from tradingos_api.services.committee_orchestrator import CommitteeInputBundle
from tradingos_api.services.hard_vetoes import HardVetoInputs
from tradingos_api.services.ingest_evidence import ingest_earnings_actuals
from tradingos_api.services.persist_feature_results import persist_post_earnings_confirmation
from tradingos_api.services.post_confirmation_gate import evaluate_post_confirmation_eligibility
from tradingos_api.services.post_earnings_confirmation import compute_post_earnings_confirmation
from tradingos_api.services.recommendation_pipeline import (
    PipelineResult,
    TacticalSizingContext,
    run_recommendation_pipeline,
)

DEFAULT_CONFIRMATION_WINDOW = timedelta(minutes=30)
"""Documented default, not tuned against real market data (no live
post-earnings session has ever been observed by this project) — the
30-minute figure matches `post_earnings_confirmation.py`'s own
FIRST_30MIN_RANGE component, so the workflow doesn't evaluate the market
reaction before that component even has data to report."""


def _make_idempotency_key(
    earnings_event_id: uuid.UUID, instrument_id: uuid.UUID, account_id: uuid.UUID
) -> str:
    return f"post-earnings:{earnings_event_id}:{instrument_id}:{account_id}"


@dataclass(frozen=True)
class PostEarningsMarketContext:
    """Market-reaction inputs `compute_post_earnings_confirmation()`
    needs, assembled by the caller — the same "pure function, caller
    gathers the inputs" boundary `CommitteeInputBundle`/
    `TacticalSizingContext` (Revision Prompt 7) already establish, so
    this orchestrator stays testable without a live market-data feed
    wired in directly. A live caller (a scheduled job) sources these
    from `providers/quotes_bars.py`/`providers/market_data.py`; the
    demo script and tests supply a fixed instance."""

    gap_pct: Decimal | None
    session_open: Decimal | None
    session_close: Decimal | None
    has_intraday_capability: bool
    range_30min_pct: Decimal | None
    range_60min_pct: Decimal | None
    price_vs_vwap_pct: Decimal | None
    day_volume: int | None
    baseline_avg_volume: int | None
    instrument_return_pct: Decimal | None
    sector_return_pct: Decimal | None
    market_return_pct: Decimal | None
    liquidity_passed: bool


@dataclass(frozen=True)
class TacticalPipelineInputs:
    """Everything `run_recommendation_pipeline()` needs for the TACTICAL
    lane call (steps 7-10) besides the workflow's own state — caller-
    assembled for the same reason `PostEarningsMarketContext` is."""

    bundle: CommitteeInputBundle
    pre_flight_veto_inputs: HardVetoInputs
    llm: LLMProvider
    cost_ceiling_usd: Decimal
    per_call_timeout_seconds: float
    triggered_by: str
    tactical_sizing_context: TacticalSizingContext | None = None
    post_sizing_veto_inputs: HardVetoInputs | None = None


@dataclass
class PostEarningsWorkflowResult:
    run: PostEarningsWorkflowRun
    pipeline_result: PipelineResult | None = None


def _get_or_create_run(
    db: Session,
    *,
    earnings_event_id: uuid.UUID,
    instrument_id: uuid.UUID,
    account_id: uuid.UUID,
    pre_event_recommendation_id: uuid.UUID | None,
) -> PostEarningsWorkflowRun:
    key = _make_idempotency_key(earnings_event_id, instrument_id, account_id)
    existing = db.scalar(
        select(PostEarningsWorkflowRun).where(PostEarningsWorkflowRun.idempotency_key == key)
    )
    if existing is not None:
        return existing
    run = PostEarningsWorkflowRun(
        earnings_event_id=earnings_event_id,
        instrument_id=instrument_id,
        account_id=account_id,
        pre_event_recommendation_id=pre_event_recommendation_id,
        status=PostEarningsWorkflowStatus.WAITING_FOR_DATA,
        reversal_detected=False,
        idempotency_key=key,
    )
    db.add(run)
    db.flush()
    return run


def _latest_prior_guidance_midpoint(
    db: Session, *, instrument_id: uuid.UUID, current_earnings_event_id: uuid.UUID, metric: str
) -> Decimal | None:
    """The most recent guidance the company itself issued for `metric`
    from an *earlier* earnings event than the one being confirmed —
    never the guidance issued alongside the current event's own results
    (that is `new_guidance_midpoint`, a different value entirely)."""
    row = db.execute(
        select(EarningsGuidanceItem.guidance_midpoint)
        .join(EarningsEvent, EarningsGuidanceItem.earnings_event_id == EarningsEvent.id)
        .where(
            EarningsEvent.instrument_id == instrument_id,
            EarningsEvent.id != current_earnings_event_id,
            EarningsGuidanceItem.metric == metric,
        )
        .order_by(EarningsGuidanceItem.issued_at.desc())
        .limit(1)
    ).first()
    return row[0] if row is not None else None


def run_post_earnings_workflow(
    db: Session,
    *,
    owner_user_id: uuid.UUID,
    earnings_event_id: uuid.UUID,
    instrument_id: uuid.UUID,
    account_id: uuid.UUID,
    ticker: str,
    fiscal_period: str,
    actuals_provider: EarningsActualsProvider,
    now: datetime | None = None,
    confirmation_window: timedelta = DEFAULT_CONFIRMATION_WINDOW,
    pre_event_recommendation_id: uuid.UUID | None = None,
    market_context: PostEarningsMarketContext | None = None,
    tactical_pipeline_inputs: TacticalPipelineInputs | None = None,
) -> PostEarningsWorkflowResult:
    effective_now = now if now is not None else datetime.now(UTC)
    run = _get_or_create_run(
        db,
        earnings_event_id=earnings_event_id,
        instrument_id=instrument_id,
        account_id=account_id,
        pre_event_recommendation_id=pre_event_recommendation_id,
    )

    # Idempotent replay / worker restart: a terminal run is never
    # re-evaluated, regardless of how many times this is called again
    # for the same (event, instrument, account).
    if run.status != PostEarningsWorkflowStatus.WAITING_FOR_DATA:
        return PostEarningsWorkflowResult(run=run)

    # Steps 1-2: detect + ingest official results. An empty response
    # means results are not yet officially released — stay WAITING_FOR_DATA.
    actuals = ingest_earnings_actuals(
        db,
        actuals_provider,
        earnings_event_id=earnings_event_id,
        ticker=ticker,
        fiscal_period=fiscal_period,
    )
    actual_by_metric = {a.metric: a.actual_value for a in actuals}
    if "eps" not in actual_by_metric and "revenue" not in actual_by_metric:
        run.detail = "waiting for official results to be released"
        db.flush()
        return PostEarningsWorkflowResult(run=run)

    if run.results_ingested_at is None:
        reported_ats = [a.reported_at for a in actuals]
        run.results_ingested_at = max(reported_ats) if reported_ats else effective_now
        run.confirmation_window_ends_at = run.results_ingested_at + confirmation_window
        db.flush()
        create_or_dedupe_alert(
            db,
            owner_user_id=owner_user_id,
            alert_type=AlertType.RESULTS_AVAILABLE,
            severity=AlertSeverity.INFO,
            title=f"{ticker.upper()} reported results",
            detail=f"Official results for {fiscal_period} are in — awaiting price confirmation.",
            triggered_at=run.results_ingested_at,
            dedup_key=f"results-available:{earnings_event_id}:{instrument_id}",
            evidence_type="EarningsEvent",
            evidence_id=earnings_event_id,
            instrument_id=instrument_id,
        )

    # Step 5: wait for the configured price-confirmation window.
    assert run.confirmation_window_ends_at is not None
    if effective_now < run.confirmation_window_ends_at:
        run.detail = (
            f"waiting for the price-confirmation window to elapse "
            f"(ends {run.confirmation_window_ends_at.isoformat()})"
        )
        db.flush()
        return PostEarningsWorkflowResult(run=run)

    # Step 3 support: the frozen pre-event consensus snapshot must exist
    # — "frozen before the event" (Prompt 11), never computed after the
    # fact.
    consensus = db.scalar(
        select(EarningsConsensusSnapshot)
        .where(EarningsConsensusSnapshot.earnings_event_id == earnings_event_id)
        .order_by(EarningsConsensusSnapshot.as_of.desc())
    )
    if consensus is None:
        run.detail = "waiting for a frozen pre-event consensus snapshot"
        db.flush()
        return PostEarningsWorkflowResult(run=run)

    # Step 4: new guidance (issued alongside these results) vs. prior
    # guidance and the frozen consensus midpoint.
    new_guidance = db.scalar(
        select(EarningsGuidanceItem)
        .where(
            EarningsGuidanceItem.earnings_event_id == earnings_event_id,
            EarningsGuidanceItem.metric == "revenue",
        )
        .order_by(EarningsGuidanceItem.issued_at.desc())
    )
    prior_guidance_midpoint = _latest_prior_guidance_midpoint(
        db,
        instrument_id=instrument_id,
        current_earnings_event_id=earnings_event_id,
        metric="revenue",
    )

    # Step 5 (price data leg): market reaction data must also have
    # arrived — a missing feed is exactly as much a "delayed input" as
    # missing results.
    if market_context is None:
        run.detail = "waiting for post-earnings price/market-reaction data"
        db.flush()
        return PostEarningsWorkflowResult(run=run)

    # Step 6: calculate post-confirmation features.
    confirmation = compute_post_earnings_confirmation(
        actual_eps=actual_by_metric.get("eps"),
        estimate_eps=consensus.consensus_eps,
        actual_revenue=actual_by_metric.get("revenue"),
        estimate_revenue=consensus.consensus_revenue,
        new_guidance_midpoint=new_guidance.guidance_midpoint if new_guidance else None,
        prior_guidance_midpoint=prior_guidance_midpoint,
        consensus_midpoint=consensus.consensus_revenue,
        gap_pct=market_context.gap_pct,
        session_open=market_context.session_open,
        session_close=market_context.session_close,
        has_intraday_capability=market_context.has_intraday_capability,
        range_30min_pct=market_context.range_30min_pct,
        range_60min_pct=market_context.range_60min_pct,
        price_vs_vwap_pct=market_context.price_vs_vwap_pct,
        day_volume=market_context.day_volume,
        baseline_avg_volume=market_context.baseline_avg_volume,
        instrument_return_pct=market_context.instrument_return_pct,
        sector_return_pct=market_context.sector_return_pct,
        market_return_pct=market_context.market_return_pct,
    )

    # Persist the gate results + per-component detail via the same
    # generic subject_type/subject_id shape (ADR-015) Revision Prompt 5's
    # other lane engines already use — this is what makes the
    # confirmation checklist screen (`GET /earnings-events/{id}/
    # post-earnings-confirmation`) show real, queryable data for a
    # workflow-produced confirmation, not just this run's own status field.
    persist_post_earnings_confirmation(
        db,
        earnings_event_id=earnings_event_id,
        as_of=effective_now,
        evidence_cutoff=effective_now,
        calculation_version="v1",
        result=confirmation,
    )

    components_by_key = {c.component_key: c for c in confirmation.components}

    # A guidance direction that contradicts a genuine results beat is a
    # real conflicting signal worth surfacing on its own, independent of
    # whatever the eligibility gate ultimately decides — a trader should
    # see "beat the quarter but guided down" even if the gate later
    # blocks the add for that exact reason.
    guidance_component = components_by_key.get("GUIDANCE_DIRECTION")
    eps_beat = components_by_key["EPS_SURPRISE"].status == "PASS"
    revenue_beat = components_by_key["REVENUE_SURPRISE"].status == "PASS"
    if (
        guidance_component is not None
        and guidance_component.detail == "LOWERED"
        and (eps_beat or revenue_beat)
    ):
        create_or_dedupe_alert(
            db,
            owner_user_id=owner_user_id,
            alert_type=AlertType.GUIDANCE_CONFLICT,
            severity=AlertSeverity.WARNING,
            title=f"{ticker.upper()}: results beat but guidance lowered",
            detail="Results beat consensus while formal guidance was lowered — a conflicting "
            "signal.",
            triggered_at=effective_now,
            dedup_key=f"guidance-conflict:{earnings_event_id}:{instrument_id}",
            evidence_type="EarningsEvent",
            evidence_id=earnings_event_id,
            instrument_id=instrument_id,
        )

    # "If initial reaction reverses, invalidate the add" — checked first
    # and independently of the general eligibility gate, since
    # invalidation is its own distinct outcome, not merely one more way
    # to fail the gate.
    reversal_component = components_by_key["REVERSAL_FAILED_BREAKOUT"]
    if reversal_component.status == "FAIL":
        run.reversal_detected = True
        run.status = PostEarningsWorkflowStatus.INVALIDATED
        run.detail = "initial post-earnings reaction reversed intraday — add invalidated"
        db.flush()
        create_or_dedupe_alert(
            db,
            owner_user_id=owner_user_id,
            alert_type=AlertType.THESIS_INVALIDATED,
            severity=AlertSeverity.WARNING,
            title=f"{ticker.upper()}: post-earnings reaction reversed",
            detail=run.detail,
            triggered_at=effective_now,
            dedup_key=f"thesis-invalidated:{earnings_event_id}:{instrument_id}:{account_id}",
            evidence_type="PostEarningsWorkflowRun",
            evidence_id=run.id,
            instrument_id=instrument_id,
        )
        return PostEarningsWorkflowResult(run=run)

    # Step 8 (gate half): HES-6 (never average down after a negative
    # gap, absolute) plus the three post-earnings confirmation gates.
    eligibility = evaluate_post_confirmation_eligibility(
        post_earnings_result=confirmation,
        gap_pct=market_context.gap_pct if market_context.gap_pct is not None else Decimal(0),
        liquidity_passed=market_context.liquidity_passed,
    )
    if not eligibility.eligible:
        run.status = PostEarningsWorkflowStatus.FAILED
        run.detail = "; ".join(eligibility.reasons)
        db.flush()
        create_or_dedupe_alert(
            db,
            owner_user_id=owner_user_id,
            alert_type=AlertType.POST_EARNINGS_CONFIRMATION_FAILED,
            severity=AlertSeverity.INFO,
            title=f"{ticker.upper()}: post-earnings confirmation failed",
            detail=run.detail,
            triggered_at=effective_now,
            dedup_key=f"confirmation-failed:{earnings_event_id}:{instrument_id}:{account_id}",
            evidence_type="PostEarningsWorkflowRun",
            evidence_id=run.id,
            instrument_id=instrument_id,
        )
        return PostEarningsWorkflowResult(run=run)

    create_or_dedupe_alert(
        db,
        owner_user_id=owner_user_id,
        alert_type=AlertType.POST_EARNINGS_CONFIRMATION_READY,
        severity=AlertSeverity.INFO,
        title=f"{ticker.upper()}: post-earnings confirmation eligible",
        detail="All post-earnings confirmation gates passed — ready for the Tactical Trading Desk.",
        triggered_at=effective_now,
        dedup_key=f"confirmation-ready:{earnings_event_id}:{instrument_id}:{account_id}",
        evidence_type="PostEarningsWorkflowRun",
        evidence_id=run.id,
        instrument_id=instrument_id,
    )

    # Steps 7-10: run the Tactical Trading Desk and (if it proposes an
    # add) size and draft the order proposal — never submitted here.
    if tactical_pipeline_inputs is None:
        run.detail = "eligible for confirmation, waiting for Tactical Trading Desk inputs"
        db.flush()
        return PostEarningsWorkflowResult(run=run)

    pipeline_result = run_recommendation_pipeline(
        db,
        lane=RecommendationMode.TACTICAL,
        bundle=tactical_pipeline_inputs.bundle,
        pre_flight_veto_inputs=tactical_pipeline_inputs.pre_flight_veto_inputs,
        llm=tactical_pipeline_inputs.llm,
        cost_ceiling_usd=tactical_pipeline_inputs.cost_ceiling_usd,
        per_call_timeout_seconds=tactical_pipeline_inputs.per_call_timeout_seconds,
        triggered_by=tactical_pipeline_inputs.triggered_by,
        tactical_sizing_context=tactical_pipeline_inputs.tactical_sizing_context,
        post_sizing_veto_inputs=tactical_pipeline_inputs.post_sizing_veto_inputs,
    )

    # A brand-new Recommendation identity for the post-confirmation
    # trade — never the pre-event one, even when the tactical action is
    # a hold (ADR-046's "pre-event trade and post-confirmation trade
    # retain separate recommendation versions and outcomes").
    run.post_event_recommendation_id = (
        pipeline_result.recommendation.id if pipeline_result.recommendation is not None else None
    )
    run.status = PostEarningsWorkflowStatus.CONFIRMED
    lane_action = (
        pipeline_result.recommendation_version.lane_action
        if pipeline_result.recommendation_version is not None
        else None
    ) or "UNKNOWN"
    run.detail = f"confirmation workflow completed — Tactical Trading Desk emitted {lane_action}"
    db.flush()

    suggestion_alert_type = {
        "TRADE_TAKE_PARTIAL": AlertType.TAKE_PARTIAL_PROFIT_SUGGESTION,
        "TRADE_EXIT": AlertType.EXIT_SUGGESTION,
    }.get(lane_action)
    if suggestion_alert_type is not None:
        create_or_dedupe_alert(
            db,
            owner_user_id=owner_user_id,
            alert_type=suggestion_alert_type,
            severity=AlertSeverity.INFO,
            title=f"{ticker.upper()}: Tactical Trading Desk suggests {lane_action}",
            detail=run.detail,
            triggered_at=effective_now,
            dedup_key=f"{lane_action.lower()}:{earnings_event_id}:{instrument_id}:{account_id}",
            evidence_type="PostEarningsWorkflowRun",
            evidence_id=run.id,
            instrument_id=instrument_id,
        )
    return PostEarningsWorkflowResult(run=run, pipeline_result=pipeline_result)
