from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.strategy_version import StrategyVersion, StrategyVersionStatus
from tradingos_api.schemas.backtest import ResultsSummaryOut
from tradingos_api.schemas.strategy import ComparisonDelta
from tradingos_api.services.audit import record_audit_event

if TYPE_CHECKING:
    # services/backtest.py imports get_or_create_default_strategy_version
    # from this module, so importing it back at module scope here would be
    # a circular import — deferred (function-local) imports below break the
    # cycle at runtime; this TYPE_CHECKING import is only for type hints.
    from tradingos_api.models.backtest_run import BacktestRun

DEFAULT_CONFIG: dict[str, Any] = {
    "weights": {"trend": 1.0, "momentum": 1.0, "macd": 1.0, "bollinger": 1.0},
    "rsi_bullish_low": 50,
    "rsi_bullish_high": 70,
    "rsi_oversold": 30,
}


def get_or_create_default_strategy_version(session: Session) -> StrategyVersion:
    """The MVP has exactly one ACTIVE `StrategyVersion` at a time, lazily
    created on first use (same pattern as Phase 3's
    `get_or_create_default_portfolio`). This is the *first* version, not a
    proposed change, so it's created directly as ACTIVE rather than going
    through the propose -> compare -> approve gate below (principle 16)."""
    strategy = session.execute(
        select(StrategyVersion).where(StrategyVersion.status == StrategyVersionStatus.ACTIVE)
    ).scalar_one_or_none()
    if strategy is not None:
        return strategy

    strategy = StrategyVersion(
        name="Plan of Record v1",
        config=DEFAULT_CONFIG,
        status=StrategyVersionStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    session.add(strategy)
    session.commit()
    session.refresh(strategy)
    return strategy


def propose_strategy_version(
    session: Session, name: str, config: dict[str, Any]
) -> StrategyVersion:
    """Phase 6's entry point into the review gate (principle 16). A
    proposal is a user/operator-submitted candidate config (ADR-026) —
    this system has no autonomous optimizer inventing weights on its own.
    Never touches the currently active version."""
    strategy = StrategyVersion(
        name=name,
        config=config,
        status=StrategyVersionStatus.PROPOSED,
        created_at=datetime.now(UTC),
    )
    session.add(strategy)
    session.flush()
    record_audit_event(
        session,
        record_type="STRATEGY_VERSION_PROPOSED",
        ref_id=strategy.id,
        snapshot={"name": name, "config": config},
    )
    session.commit()
    session.refresh(strategy)
    return strategy


def compute_comparison_delta(
    candidate: ResultsSummaryOut, active: ResultsSummaryOut
) -> ComparisonDelta:
    """Pure, DB-free (candidate minus active, per numeric summary metric)
    — mirrors services/scoring.py's/services/backtest.py's pure-core
    convention, unit-testable with hand-built `ResultsSummaryOut` fixtures.
    Never used to auto-decide anything (ADR-028) — the system surfaces the
    comparison, a human decides."""
    return ComparisonDelta(
        total_return_pct=candidate.total_return_pct - active.total_return_pct,
        max_drawdown_pct=candidate.max_drawdown_pct - active.max_drawdown_pct,
        win_rate_pct=candidate.win_rate_pct - active.win_rate_pct,
        avg_win_pct=candidate.avg_win_pct - active.avg_win_pct,
        avg_loss_pct=candidate.avg_loss_pct - active.avg_loss_pct,
        num_trades=candidate.num_trades - active.num_trades,
    )


def run_comparison(
    session: Session,
    candidate: StrategyVersion,
    active: StrategyVersion,
    date_range_start: date,
    date_range_end: date,
    **backtest_kwargs: Any,
) -> tuple[BacktestRun, BacktestRun, ComparisonDelta]:
    """Always re-runs both backtests fresh (ADR-028) — candidate and the
    currently active version, with identical params, so the comparison is
    never stale or based on a client-supplied result. Persists two real
    `BacktestRun` rows (nothing ephemeral) — mechanically identical to
    calling `POST /api/v1/backtests` twice yourself and diffing."""
    # Deferred import: services/backtest.py imports
    # get_or_create_default_strategy_version from this module, so a
    # module-scope import here would be circular.
    from tradingos_api.services.backtest import run_backtest

    candidate_run = run_backtest(
        session,
        date_range_start,
        date_range_end,
        strategy_version_id=candidate.id,
        **backtest_kwargs,
    )
    active_run = run_backtest(
        session, date_range_start, date_range_end, strategy_version_id=active.id, **backtest_kwargs
    )
    candidate_summary = ResultsSummaryOut.model_validate(candidate_run.results_summary)
    active_summary = ResultsSummaryOut.model_validate(active_run.results_summary)
    delta = compute_comparison_delta(candidate_summary, active_summary)
    return candidate_run, active_run, delta


def approve_strategy_version(
    session: Session,
    candidate: StrategyVersion,
    date_range_start: date,
    date_range_end: date,
    comment: str | None,
    **backtest_kwargs: Any,
) -> StrategyVersion:
    """The explicit approval action (principle 16) — never automatic, and
    never gated on the comparison's numbers (ADR-028): the system's job is
    only to surface the comparison, a human decides. Re-runs the
    comparison itself (never trusts a prior `/compare` call) to produce
    the audit snapshot, then activates the candidate and supersedes the
    previously active version."""
    if candidate.status != StrategyVersionStatus.PROPOSED:
        raise ValueError(
            f"Only a PROPOSED strategy version can be approved "
            f"(this one is {candidate.status.value})."
        )

    active = get_or_create_default_strategy_version(session)
    if candidate.id == active.id:
        raise AssertionError("invariant violated: candidate is already the active version")

    candidate_run, active_run, delta = run_comparison(
        session, candidate, active, date_range_start, date_range_end, **backtest_kwargs
    )

    previous_active_id = active.id
    active.status = StrategyVersionStatus.SUPERSEDED
    candidate.status = StrategyVersionStatus.ACTIVE
    candidate.decided_at = datetime.now(UTC)
    candidate.decision_comment = comment

    record_audit_event(
        session,
        record_type="STRATEGY_VERSION_APPROVED",
        ref_id=candidate.id,
        snapshot={
            "candidate_backtest_run_id": candidate_run.id,
            "active_backtest_run_id": active_run.id,
            "previous_active_strategy_version_id": previous_active_id,
            "delta": delta.model_dump(mode="json"),
            "comment": comment,
        },
    )
    session.commit()
    session.refresh(candidate)
    return candidate


def reject_strategy_version(
    session: Session, candidate: StrategyVersion, comment: str | None
) -> StrategyVersion:
    """No backtest re-run — there's nothing to activate on a rejection."""
    if candidate.status != StrategyVersionStatus.PROPOSED:
        raise ValueError(
            f"Only a PROPOSED strategy version can be rejected "
            f"(this one is {candidate.status.value})."
        )

    candidate.status = StrategyVersionStatus.REJECTED
    candidate.decided_at = datetime.now(UTC)
    candidate.decision_comment = comment

    record_audit_event(
        session,
        record_type="STRATEGY_VERSION_REJECTED",
        ref_id=candidate.id,
        snapshot={"comment": comment},
    )
    session.commit()
    session.refresh(candidate)
    return candidate
