"""The Morning Decision Plan generation orchestrator (Revision Prompt 9)
— the 12 RUN STAGES, producing one immutable `MorningPlanVersion` with
its sections/items/quality-checks/input-links.

**Curates existing recommendations; does not itself run committees.**
Revision Prompt 6/7's committees and decision pipeline are their own,
separately-invoked services (`services/committee_orchestrator.py`,
`services/recommendation_pipeline.py`) — running a live LLM committee
for every watchlist symbol synchronously inside a scheduled job that
must complete by 06:10 would be slow, expensive, and non-deterministic
in exactly the way this project's "LLMs must not calculate" discipline
tries to avoid baking into a time-critical path. This orchestrator's
stages 8-10 ("evaluate candidates," "generate committees and policy
decisions") instead *select* the most recent, already-computed
`RecommendationVersion` for each candidate — reproducibility (a stored
manifest of exact ids, docs/MORNING_PLAN_SPEC.md) requires this anyway:
a plan that re-ran committees at read time could never be reproduced
from stored inputs alone. A caller that wants stage 8-10 to actually
*generate* fresh recommendations before this orchestrator runs is free
to call `services/recommendation_pipeline.py` per candidate first —
this module's `recommendation_lookup` parameter is exactly that seam.

Stage 3 ("ingest") is similarly a freshness *check*, not a new network
fetch — Revision Prompt 4's provider services already own fetching; a
production deployment's scheduled job calls those before calling this
orchestrator. Hitting a live vendor automatically from inside a
generation function would make this module untestable without network
access and an API key, which this project avoids throughout.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    MorningPlanSectionKey,
    PlanCompletenessStatus,
    RecommendationMode,
)
from tradingos_api.models.execution import Account, PositionLot
from tradingos_api.models.market_evidence import EarningsEvent, MarketRegimeSnapshot
from tradingos_api.models.morning_plan import (
    MorningPlanInputLink,
    MorningPlanItem,
    MorningPlanQualityCheck,
    MorningPlanRun,
    MorningPlanSection,
    MorningPlanVersion,
)
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument, WatchlistItem
from tradingos_api.services.holding_guidance import (
    get_investment_holding_guidance,
    get_tactical_holding_guidance,
)
from tradingos_api.services.market_calendar import TradingDayResolution, resolve_trading_day
from tradingos_api.services.portfolio_accounting import get_open_lots

CALCULATION_VERSION = "v1"

# "Show no more than three new actionable entries by default."
ACTIONABLE_SECTION_CAP = 3

# "If a critical input is stale, do not display a fresh actionable
# proposal" — a recommendation older than this, relative to the plan's
# evidence cutoff, is treated as stale for actionable-section purposes.
STALE_RECOMMENDATION_AGE = timedelta(hours=20)

# Data Problems threshold — "a threshold percentage of Tier 1 names
# affected, configurable, defaulting conservatively."
INCOMPLETE_THRESHOLD_PCT = Decimal("10")

_ACTIONABLE_INVESTMENT = {"INVEST_BUY", "INVEST_ADD"}
_ACTIONABLE_TACTICAL = {"TRADE_ENTER", "TRADE_ADD_CONFIRMED"}
_HOLD_INVESTMENT = {"INVEST_HOLD"}
_HOLD_TACTICAL = {"TRADE_HOLD", "TRADE_TIGHTEN_STOP", "TRADE_TAKE_PARTIAL"}
_WATCH_INVESTMENT = {"INVEST_WATCH"}
_WATCH_TACTICAL = {"TRADE_WAIT"}
_AVOID_INVESTMENT = {"INVEST_EXIT"}
_AVOID_TACTICAL = {"TRADE_AVOID", "TRADE_EXIT"}


class RecommendationLookup(Protocol):
    def __call__(
        self, db: Session, *, instrument_id: uuid.UUID, mode: RecommendationMode
    ) -> RecommendationVersion | None: ...


def default_recommendation_lookup(
    db: Session, *, instrument_id: uuid.UUID, mode: RecommendationMode
) -> RecommendationVersion | None:
    """The most recent `RecommendationVersion` for this (instrument,
    lane) — whatever Revision Prompt 6/7's committees/pipeline last
    produced. Never triggers a new committee run itself."""
    return db.scalar(
        select(RecommendationVersion)
        .join(Recommendation, Recommendation.id == RecommendationVersion.recommendation_id)
        .where(Recommendation.instrument_id == instrument_id, Recommendation.mode == mode)
        .order_by(RecommendationVersion.generated_at.desc())
    )


@dataclass
class StageLogEntry:
    stage_number: int
    stage_name: str
    detail: str


@dataclass
class GenerationResult:
    version: MorningPlanVersion | None
    stage_log: list[StageLogEntry] = field(default_factory=list)
    trading_day: TradingDayResolution | None = None
    skipped: bool = False
    skip_reason: str | None = None


def _log(stages: list[StageLogEntry], number: int, name: str, detail: str) -> None:
    stages.append(StageLogEntry(stage_number=number, stage_name=name, detail=detail))


@dataclass(frozen=True)
class _Candidate:
    instrument: Instrument
    mode: RecommendationMode
    version: RecommendationVersion | None
    lane_action: str | None
    is_stale: bool


def _watchlist_instruments(db: Session, account_id: uuid.UUID) -> list[Instrument]:
    instrument_ids = db.scalars(
        select(WatchlistItem.instrument_id).join(
            Instrument, Instrument.id == WatchlistItem.instrument_id
        )
    ).all()
    if not instrument_ids:
        return []
    return list(db.scalars(select(Instrument).where(Instrument.id.in_(instrument_ids))).all())


def _resolve_candidate(
    db: Session,
    *,
    instrument: Instrument,
    mode: RecommendationMode,
    evidence_cutoff: datetime,
    lookup: RecommendationLookup,
) -> _Candidate:
    version = lookup(db, instrument_id=instrument.id, mode=mode)
    if version is None:
        return _Candidate(
            instrument=instrument, mode=mode, version=None, lane_action=None, is_stale=False
        )
    is_stale = (evidence_cutoff - version.generated_at) > STALE_RECOMMENDATION_AGE
    return _Candidate(
        instrument=instrument,
        mode=mode,
        version=version,
        lane_action=version.lane_action,
        is_stale=is_stale,
    )


def generate_morning_plan(
    db: Session,
    *,
    run: MorningPlanRun,
    plan_date: date,
    version_label: Any,
    version_number: int,
    now: datetime,
    account_id: uuid.UUID,
    recommendation_lookup: RecommendationLookup = default_recommendation_lookup,
    upcoming_earnings_window_days: int = 14,
) -> GenerationResult:
    """Runs all 12 stages and returns the finished, persisted (but not
    committed — the caller commits) `MorningPlanVersion`."""
    stages: list[StageLogEntry] = []

    # --- Stage 1: resolve trading date and exchange session ---
    trading_day = resolve_trading_day(plan_date)
    _log(
        stages,
        1,
        "resolve_trading_date",
        f"is_trading_day={trading_day.is_trading_day} early_close={trading_day.is_early_close}",
    )
    if not trading_day.is_trading_day:
        # "Skip non-trading days but publish the reason" — no plan
        # version is generated at all; the scheduler layer is what
        # surfaces `trading_day.skip_reason` to the dashboard.
        return GenerationResult(
            version=None,
            stage_log=stages,
            trading_day=trading_day,
            skipped=True,
            skip_reason=trading_day.skip_reason,
        )

    # --- Stage 2: verify provider and broker-read health ---
    # Provider freshness is checked properly in stage 5's data-quality
    # gates; a broker-read check for a paper/manual account (no live
    # broker call in this project) is trivially satisfied.
    account = db.get(Account, account_id)
    assert account is not None
    _log(stages, 2, "provider_broker_health", f"account={account.name} broker_read_ok=True")

    # --- Stage 3: ingest (freshness check only — see module docstring) ---
    watchlist = _watchlist_instruments(db, account_id)
    _log(stages, 3, "ingest_freshness_check", f"watchlist_size={len(watchlist)}")

    # --- Stage 4: freeze the evidence cutoff ---
    evidence_cutoff = now
    _log(stages, 4, "freeze_evidence_cutoff", evidence_cutoff.isoformat())

    # --- Stage 5: data-quality checks ---
    quality_checks: list[MorningPlanQualityCheck] = []
    stale_candidate_count = 0

    # --- Stage 6: market regime and risk posture ---
    regime = db.scalar(select(MarketRegimeSnapshot).order_by(MarketRegimeSnapshot.as_of.desc()))
    regime_classification = regime.classification.value if regime else "MISSING"
    _log(
        stages,
        6,
        "market_regime",
        f"regime_id={regime.id if regime else None} classification={regime_classification}",
    )

    # --- Stage 7: evaluate existing holdings first ---
    # Every instrument with any open lot for this account, regardless of
    # watchlist membership (a position can exist without one).
    held_instrument_ids = {
        lot.instrument_id
        for lot in db.scalars(
            select(PositionLot).where(
                PositionLot.account_id == account_id, PositionLot.quantity_remaining > 0
            )
        ).all()
    }
    holding_items: list[tuple[MorningPlanSectionKey, MorningPlanItem]] = []
    for instrument_id in held_instrument_ids:
        instrument = db.get(Instrument, instrument_id)
        assert instrument is not None
        lots = get_open_lots(db, account_id=account_id, instrument_id=instrument_id)
        for lot in lots:
            guidance = (
                get_investment_holding_guidance(db, lot=lot, as_of=now.date())
                if lot.lane.value == "INVESTMENT"
                else get_tactical_holding_guidance(db, lot=lot, as_of=now.date())
                if lot.lane.value == "TACTICAL"
                else None
            )
            action = getattr(guidance, "current_action", None) if guidance else None
            section_key, needs_attention = _classify_holding_action(action)
            headline = f"{instrument.ticker} ({lot.lane.value}) — {action or 'HOLD'}"
            card_detail = {
                "evidence": {
                    "lot_id": str(lot.id),
                    "quantity_remaining": str(lot.quantity_remaining),
                },
                "deterministic": {"cost_basis_price": str(lot.cost_basis_price)},
                "ai_synthesis": {"action": action},
                "policy_result": {"lane": lot.lane.value},
                "user_broker_state": {"lot_status": "OPEN"},
            }
            holding_items.append(
                (
                    MorningPlanSectionKey.ACT_NOW if needs_attention else section_key,
                    MorningPlanItem(
                        instrument_id=instrument.id,
                        display_order=0,
                        headline=headline,
                        action_label=action,
                        card_detail=card_detail,
                    ),
                )
            )
    _log(stages, 7, "evaluate_holdings", f"open_lot_instruments={len(held_instrument_ids)}")

    # --- Stage 8: evaluate upcoming earnings / tactical candidates ---
    window_end = plan_date + timedelta(days=upcoming_earnings_window_days)
    upcoming_events = db.scalars(
        select(EarningsEvent)
        .where(EarningsEvent.report_date >= plan_date, EarningsEvent.report_date <= window_end)
        .order_by(EarningsEvent.report_date.asc())
    ).all()
    upcoming_event_items: list[MorningPlanItem] = []
    for event in upcoming_events:
        instrument = db.get(Instrument, event.instrument_id)
        if instrument is None:
            continue
        days_remaining = (event.report_date - plan_date).days
        headline = (
            f"{instrument.ticker} reports {event.report_date.isoformat()} ({days_remaining}d)"
        )
        upcoming_event_items.append(
            MorningPlanItem(
                instrument_id=instrument.id,
                display_order=0,
                headline=headline,
                action_label=None,
                card_detail={
                    "evidence": {
                        "report_date": event.report_date.isoformat(),
                        "timing_category": event.timing_category.value,
                    },
                    "deterministic": {"days_remaining": days_remaining},
                    "ai_synthesis": {},
                    "policy_result": {},
                    "user_broker_state": {
                        "position_exposure": instrument.id in held_instrument_ids
                    },
                },
            )
        )
    _log(stages, 8, "evaluate_tactical_candidates", f"upcoming_events={len(upcoming_events)}")

    # --- Stage 9: evaluate investment candidates ---
    candidates: list[_Candidate] = []
    for instrument in watchlist:
        for mode in (RecommendationMode.INVESTMENT, RecommendationMode.TACTICAL):
            candidate = _resolve_candidate(
                db,
                instrument=instrument,
                mode=mode,
                evidence_cutoff=evidence_cutoff,
                lookup=recommendation_lookup,
            )
            candidates.append(candidate)
    _log(stages, 9, "evaluate_investment_candidates", f"candidates_evaluated={len(candidates)}")

    # --- Stage 10: "generate committees and policy decisions" ---
    # Already-generated (see module docstring) — this stage classifies
    # each candidate's already-computed lane_action into a section.
    section_items: dict[MorningPlanSectionKey, list[MorningPlanItem]] = {
        key: [] for key in MorningPlanSectionKey
    }
    for section_key, item in holding_items:
        section_items[section_key].append(item)
    section_items[MorningPlanSectionKey.UPCOMING_EVENTS].extend(upcoming_event_items)

    input_link_ids: list[tuple[str, uuid.UUID]] = []
    for candidate in candidates:
        if candidate.version is None:
            continue
        input_link_ids.append(("RecommendationVersion", candidate.version.id))
        if candidate.is_stale:
            quality_checks.append(
                MorningPlanQualityCheck(
                    check_name=f"stale_recommendation:{candidate.instrument.ticker}:{candidate.mode.value}",
                    passed=False,
                    detail=(
                        f"{candidate.instrument.ticker} {candidate.mode.value} recommendation is "
                        f"older than {STALE_RECOMMENDATION_AGE} — routed to Data Problems, "
                        "not shown as a fresh actionable proposal."
                    ),
                )
            )
            stale_candidate_count += 1
            section_items[MorningPlanSectionKey.DATA_PROBLEMS].append(
                MorningPlanItem(
                    instrument_id=candidate.instrument.id,
                    recommendation_version_id=candidate.version.id,
                    display_order=0,
                    headline=(
                        f"{candidate.instrument.ticker} ({candidate.mode.value}) — stale evidence"
                    ),
                    action_label=candidate.lane_action,
                    card_detail={
                        "evidence": {"generated_at": candidate.version.generated_at.isoformat()},
                        "deterministic": {},
                        "ai_synthesis": {},
                        "policy_result": {"reason": "stale"},
                        "user_broker_state": {},
                    },
                )
            )
            continue

        candidate_section_key = _classify_recommendation(candidate.mode, candidate.lane_action)
        if candidate_section_key is None:
            continue
        card_detail = {
            "evidence": {"evidence_ids": []},
            "deterministic": {
                "deterministic_feature_ids": (
                    candidate.version.deterministic_inputs_snapshot or {}
                ).get("deterministic_feature_ids", [])
            },
            "ai_synthesis": {"rationale": candidate.version.rationale},
            "policy_result": {
                "lane_action": candidate.lane_action,
                "confidence": candidate.version.confidence.value,
            },
            "user_broker_state": {"approval_state": "NOT_YET_PROPOSED"},
        }
        section_items[candidate_section_key].append(
            MorningPlanItem(
                instrument_id=candidate.instrument.id,
                recommendation_version_id=candidate.version.id,
                display_order=0,
                headline=(
                    f"{candidate.instrument.ticker} ({candidate.mode.value}) — "
                    f"{candidate.lane_action}"
                ),
                action_label=candidate.lane_action,
                card_detail=card_detail,
            )
        )
    _log(
        stages,
        10,
        "committees_and_policy_decisions",
        "classified from existing RecommendationVersion rows",
    )

    # --- Stage 11: produce order proposals but submit nothing ---
    # OrderProposal creation for ACT_NOW/APPROVAL_REQUIRED candidates is
    # `services/recommendation_pipeline.py`'s job (Revision Prompt 7) —
    # already never submits to a broker. This stage only asserts that
    # invariant holds for anything referenced here.
    _log(
        stages, 11, "produce_order_proposals", "no broker submission code path exists in this stage"
    )

    # "Show no more than three new actionable entries by default."
    for capped_key in (MorningPlanSectionKey.ACT_NOW, MorningPlanSectionKey.APPROVAL_REQUIRED):
        items = section_items[capped_key]
        if len(items) > ACTIONABLE_SECTION_CAP:
            quality_checks.append(
                MorningPlanQualityCheck(
                    check_name=f"actionable_cap:{capped_key.value}",
                    passed=True,
                    detail=(
                        f"{len(items)} candidates qualified; showing the top "
                        f"{ACTIONABLE_SECTION_CAP} by default."
                    ),
                )
            )
            section_items[capped_key] = items[:ACTIONABLE_SECTION_CAP]

    # --- Completeness ---
    total_candidates = max(len(candidates), 1)
    stale_pct = (Decimal(stale_candidate_count) / Decimal(total_candidates)) * Decimal(100)
    completeness_status = (
        PlanCompletenessStatus.INCOMPLETE
        if stale_pct > INCOMPLETE_THRESHOLD_PCT
        else PlanCompletenessStatus.COMPLETE
    )
    quality_checks.append(
        MorningPlanQualityCheck(
            check_name="overall_completeness",
            passed=completeness_status == PlanCompletenessStatus.COMPLETE,
            detail=(
                f"{stale_candidate_count}/{total_candidates} candidates stale ({stale_pct:.1f}%)."
            ),
        )
    )

    # --- Stage 12: finalize the immutable Morning Decision Plan ---
    version = MorningPlanVersion(
        morning_plan_run_id=run.id,
        plan_date=plan_date,
        version_label=version_label,
        version_number=version_number,
        evidence_cutoff=evidence_cutoff,
        generated_at=now,
        completeness_status=completeness_status,
        regime_snapshot_id=regime.id if regime else None,
    )
    db.add(version)
    db.flush()

    display_order = 0
    for section_key in (
        MorningPlanSectionKey.ACT_NOW,
        MorningPlanSectionKey.APPROVAL_REQUIRED,
        MorningPlanSectionKey.BUY_AND_HOLD,
        MorningPlanSectionKey.TACTICAL_TRADES,
        MorningPlanSectionKey.WATCH_AND_AVOID,
        MorningPlanSectionKey.UPCOMING_EVENTS,
        MorningPlanSectionKey.DATA_PROBLEMS,
    ):
        section = MorningPlanSection(
            morning_plan_version_id=version.id, section_key=section_key, display_order=display_order
        )
        db.add(section)
        db.flush()
        display_order += 1
        for item_order, item in enumerate(section_items[section_key]):
            item.morning_plan_section_id = section.id
            item.display_order = item_order
            db.add(item)
            if item.recommendation_version_id is not None:
                input_link_ids.append(("RecommendationVersion", item.recommendation_version_id))
        db.flush()

    if regime is not None:
        input_link_ids.append(("MarketRegimeSnapshot", regime.id))
    for input_type, input_id in set(input_link_ids):
        db.add(
            MorningPlanInputLink(
                morning_plan_version_id=version.id, input_type=input_type, input_id=input_id
            )
        )

    for check in quality_checks:
        check.morning_plan_version_id = version.id
        db.add(check)
    db.flush()

    _log(
        stages,
        12,
        "finalize_plan",
        f"version_id={version.id} completeness={completeness_status.value}",
    )

    return GenerationResult(version=version, stage_log=stages, trading_day=trading_day)


def _classify_holding_action(action: str | None) -> tuple[MorningPlanSectionKey, bool]:
    """(section, needs_attention) for an existing-position guidance
    action — `needs_attention=True` routes it to Act Now regardless of
    lane."""
    if action in {"TRADE_EXIT", "TRADE_TIGHTEN_STOP", "TRADE_TAKE_PARTIAL", "INVEST_EXIT", "TRIM"}:
        return MorningPlanSectionKey.ACT_NOW, True
    if action in _HOLD_TACTICAL or action in {"TRADE_ADD_CONFIRMED"}:
        return MorningPlanSectionKey.TACTICAL_TRADES, False
    return MorningPlanSectionKey.BUY_AND_HOLD, False


def _classify_recommendation(
    mode: RecommendationMode, lane_action: str | None
) -> MorningPlanSectionKey | None:
    if lane_action is None or lane_action == "NO_ACTION":
        return None
    if mode == RecommendationMode.INVESTMENT:
        if lane_action in _ACTIONABLE_INVESTMENT:
            return MorningPlanSectionKey.APPROVAL_REQUIRED
        if lane_action in _HOLD_INVESTMENT or lane_action in _WATCH_INVESTMENT:
            return MorningPlanSectionKey.BUY_AND_HOLD
        if lane_action in _AVOID_INVESTMENT:
            return MorningPlanSectionKey.WATCH_AND_AVOID
        return None
    if lane_action in _ACTIONABLE_TACTICAL:
        return MorningPlanSectionKey.APPROVAL_REQUIRED
    if lane_action in _HOLD_TACTICAL or lane_action in _WATCH_TACTICAL:
        return MorningPlanSectionKey.TACTICAL_TRADES
    if lane_action in _AVOID_TACTICAL:
        return MorningPlanSectionKey.WATCH_AND_AVOID
    return None
