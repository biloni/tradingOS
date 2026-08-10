"""Change proposal governance (Revision Prompt 14). Generalizes the
existing `ModelChangeProposal`/`ModelChangeApproval` tables (schema
fixtures since Revision Prompt R3, previously written only by the seed
script — no live governance service existed before this revision,
confirmed by grep) into a real propose → review → approve/reject →
**activate** → rollback workflow.

**No proposal may activate itself — enforced structurally, not by
convention.** `propose_change()`/`propose_strategy_parameter_change()`
only ever create a `PROPOSED` row. `approve_change()` only ever writes
`APPROVED` plus a `ModelChangeApproval` audit row — it never touches the
subject's live configuration. `activate_change()` is the *only* function
in this codebase that flips a subject's live configuration, and it
requires `APPROVED` as a precondition (`services/lifecycle.py::assert_transition_allowed()`
against `MODEL_CHANGE_PROPOSAL_TRANSITIONS`, which has no `PROPOSED ->
ACTIVATED` edge at all — the state machine itself makes self-activation
unrepresentable, not just discouraged).

**No result may rewrite historical recommendations.** Activation and
rollback only ever mutate `StrategyVersion.status`/`ModelChangeProposal`
rows — neither function imports, queries for update, or writes to
`RecommendationVersion` anywhere in this module. `tests/test_change_governance.py`
proves this directly: every existing `RecommendationVersion` row is
byte-identical before and after an activation.

**Rollback creates a new version rather than resurrecting the old
one.** `StrategyVersionStatus`'s own transition map
(`models/enums.py::STRATEGY_VERSION_TRANSITIONS`) has no edge back out
of `SUPERSEDED` — by design, matching every other append-only lifecycle
in this codebase (a `RecommendationVersion`, once superseded, is never
un-superseded either). A rollback therefore clones the prior config into
a brand-new `StrategyVersion` row and activates *that* — the same
"redeploy the last known-good config as a new version" pattern real
deployment rollbacks already use, not a literal undo. The full lineage
(candidate → activated → rolled back → clone-of-prior activated) stays
fully reconstructable from `StrategyVersion` rows and their
`decision_comment`s, never destroyed.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    MODEL_CHANGE_PROPOSAL_TRANSITIONS,
    STRATEGY_VERSION_TRANSITIONS,
    ModelChangeProposalStatus,
    StrategyVersionStatus,
)
from tradingos_api.models.learning import ModelChangeApproval, ModelChangeProposal, StrategyVersion
from tradingos_api.services.backtest_engine import BacktestResult, BacktestRunConfig, run_backtest
from tradingos_api.services.lifecycle import assert_transition_allowed

CALCULATION_VERSION = "v1"

_WALK_FORWARD_WINDOWS: list[tuple[str, str, str]] = [
    ("TRAIN", "2024-08-01", "2025-07-31"),
    ("VALIDATION", "2025-08-01", "2026-01-31"),
    ("OUT_OF_SAMPLE", "2026-02-01", "2026-07-31"),
]
"""The same three non-overlapping windows `services/backtest_validation.py::run_walk_forward()`
uses — kept as a local, string-date constant here (rather than importing
that module's date objects) so a change proposal's evidence package
always uses the same walk-forward convention regardless of which
strategy the proposal targets, without coupling this module to Prompt
13's specific baseline-scenario constants."""


class ProposalNotFoundError(ValueError):
    def __init__(self, proposal_id: uuid.UUID) -> None:
        super().__init__(f"ModelChangeProposal {proposal_id} not found")


@dataclass(frozen=True)
class BacktestSplitSummary:
    label: str
    date_range_start: str
    date_range_end: str
    num_trades: int
    total_return_pct: str | None
    win_rate_pct: str | None
    profit_factor: str | None
    sharpe_ratio: str | None
    max_drawdown_pct: str | None


def _decimal_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _split_summary(
    label: str, start: str, end: str, result: BacktestResult
) -> BacktestSplitSummary:
    return BacktestSplitSummary(
        label=label,
        date_range_start=start,
        date_range_end=end,
        num_trades=result.trade_stats.num_trades,
        total_return_pct=_decimal_str(result.total_return_pct),
        win_rate_pct=_decimal_str(result.trade_stats.win_rate_pct),
        profit_factor=_decimal_str(result.trade_stats.profit_factor),
        sharpe_ratio=_decimal_str(result.sharpe_ratio),
        max_drawdown_pct=_decimal_str(result.drawdown.max_drawdown_pct),
    )


def _config_snapshot(config: BacktestRunConfig) -> dict[str, Any]:
    snapshot = asdict(config)
    snapshot["strategy_key"] = config.strategy_key.value
    for key in ("start", "end", "universe_start", "universe_end"):
        snapshot[key] = snapshot[key].isoformat()
    for key, value in list(snapshot.items()):
        if isinstance(value, Decimal):
            snapshot[key] = str(value)
    return snapshot


def run_backtest_splits(db: Session, config: BacktestRunConfig) -> dict[str, BacktestSplitSummary]:
    """The `train`/`validation`/`out_of_sample`/`walk_forward` results
    Prompt 14 requires every proposal to carry, for a `BacktestRunConfig`-
    shaped subject — reuses `services/backtest_engine.py::run_backtest()`
    verbatim for each window, the same engine Revision Prompt 13 already
    built and tested, never a second simulation implementation."""
    results: dict[str, BacktestSplitSummary] = {}
    for label, start, end in _WALK_FORWARD_WINDOWS:
        windowed = replace(
            config,
            start=datetime.fromisoformat(start).date(),
            end=datetime.fromisoformat(end).date(),
        )
        results[label] = _split_summary(label, start, end, run_backtest(db, windowed))
    full_result = run_backtest(db, config)
    results["FULL"] = _split_summary(
        "FULL", config.start.isoformat(), config.end.isoformat(), full_result
    )
    return results


def propose_change(
    db: Session,
    *,
    owner_user_id: uuid.UUID,
    subject_type: str,
    subject_ref_id: uuid.UUID | None,
    description: str,
    evidence_package: dict[str, Any],
) -> ModelChangeProposal:
    """The generic path for a proposal type this module has no dedicated
    helper for (a feature, a prompt version, a provider swap, a risk or
    execution-policy change) — the caller assembles `evidence_package`
    itself (validated against `schemas/governance.py::EvidencePackage`
    at the API boundary) rather than this function fabricating any of
    Prompt 14's required fields on the caller's behalf."""
    proposal = ModelChangeProposal(
        owner_user_id=owner_user_id,
        subject_type=subject_type,
        subject_ref_id=subject_ref_id,
        description=description,
        status=ModelChangeProposalStatus.PROPOSED,
        proposed_at=datetime.now(UTC),
        evidence_package=evidence_package,
    )
    db.add(proposal)
    db.flush()
    return proposal


def propose_strategy_parameter_change(
    db: Session,
    *,
    owner_user_id: uuid.UUID,
    strategy_definition_id: uuid.UUID,
    current_config: BacktestRunConfig,
    proposed_config: BacktestRunConfig,
    economic_rationale: str,
    sensitivity: dict[str, BacktestSplitSummary] | None = None,
    costs: dict[str, Any],
    operational_risks: list[str],
    rollback_plan: str,
    description: str,
) -> ModelChangeProposal:
    """The concrete, deeply-integrated proposal type: a change to
    `BacktestRunConfig` parameters (score threshold, expected-move
    threshold, risk budgets, ...) for an earnings-strategy
    `StrategyDefinition`. Creates the actual candidate `StrategyVersion`
    row (status=`PROPOSED`, never `ACTIVE`) alongside the
    `ModelChangeProposal` — "current and proposed version" is therefore
    a real schema row, not only JSON inside `evidence_package`."""
    current_splits = run_backtest_splits(db, current_config)
    proposed_splits = run_backtest_splits(db, proposed_config)

    candidate = StrategyVersion(
        strategy_definition_id=strategy_definition_id,
        config=_config_snapshot(proposed_config),
        status=StrategyVersionStatus.PROPOSED,
    )
    db.add(candidate)
    db.flush()

    evidence_package: dict[str, Any] = {
        "sample_size": proposed_splits["FULL"].num_trades,
        "evidence": [
            "services/backtest_engine.py::run_backtest() against the deterministic "
            "synthetic universe (services/backtest_data.py) — see docs/DECISIONS.md ADR-063 "
            "for why this dev environment's real market/earnings history is insufficient."
        ],
        "current_version_snapshot": _config_snapshot(current_config),
        "proposed_version_snapshot": _config_snapshot(proposed_config),
        "economic_rationale": economic_rationale,
        "train_results": asdict(current_splits["TRAIN"]),
        "validation_results": asdict(current_splits["VALIDATION"]),
        "out_of_sample_results": asdict(current_splits["OUT_OF_SAMPLE"]),
        "walk_forward_results": {
            "current": {k: asdict(v) for k, v in current_splits.items()},
            "proposed": {k: asdict(v) for k, v in proposed_splits.items()},
        },
        "sensitivity": {k: asdict(v) for k, v in (sensitivity or {}).items()},
        "costs": costs,
        "operational_risks": operational_risks,
        "rollback_plan": rollback_plan,
    }

    proposal = ModelChangeProposal(
        owner_user_id=owner_user_id,
        subject_type="STRATEGY_PARAMETER",
        subject_ref_id=candidate.id,
        description=description,
        status=ModelChangeProposalStatus.PROPOSED,
        proposed_at=datetime.now(UTC),
        evidence_package=evidence_package,
    )
    db.add(proposal)
    db.flush()
    return proposal


def _get_proposal(db: Session, proposal_id: uuid.UUID) -> ModelChangeProposal:
    proposal = db.get(ModelChangeProposal, proposal_id)
    if proposal is None:
        raise ProposalNotFoundError(proposal_id)
    return proposal


def _transition(
    db: Session, proposal: ModelChangeProposal, *, to_status: ModelChangeProposalStatus
) -> None:
    assert_transition_allowed(
        "ModelChangeProposal",
        proposal.status.value,
        to_status.value,
        MODEL_CHANGE_PROPOSAL_TRANSITIONS,
    )
    proposal.status = to_status
    db.flush()


def approve_change(
    db: Session, *, proposal_id: uuid.UUID, decided_by: str, comment: str | None = None
) -> ModelChangeProposal:
    proposal = _get_proposal(db, proposal_id)
    _transition(db, proposal, to_status=ModelChangeProposalStatus.APPROVED)
    db.add(
        ModelChangeApproval(
            proposal_id=proposal.id,
            decision=ModelChangeProposalStatus.APPROVED,
            comment=f"{decided_by}: {comment}" if comment else decided_by,
            decided_at=datetime.now(UTC),
        )
    )
    db.flush()
    return proposal


def reject_change(
    db: Session, *, proposal_id: uuid.UUID, decided_by: str, comment: str
) -> ModelChangeProposal:
    proposal = _get_proposal(db, proposal_id)
    _transition(db, proposal, to_status=ModelChangeProposalStatus.REJECTED)
    db.add(
        ModelChangeApproval(
            proposal_id=proposal.id,
            decision=ModelChangeProposalStatus.REJECTED,
            comment=f"{decided_by}: {comment}",
            decided_at=datetime.now(UTC),
        )
    )
    db.flush()
    return proposal


def withdraw_change(
    db: Session, *, proposal_id: uuid.UUID, comment: str | None = None
) -> ModelChangeProposal:
    proposal = _get_proposal(db, proposal_id)
    _transition(db, proposal, to_status=ModelChangeProposalStatus.WITHDRAWN)
    db.add(
        ModelChangeApproval(
            proposal_id=proposal.id,
            decision=ModelChangeProposalStatus.WITHDRAWN,
            comment=comment,
            decided_at=datetime.now(UTC),
        )
    )
    db.flush()
    return proposal


def _activate_strategy_version(db: Session, proposal: ModelChangeProposal) -> None:
    if proposal.subject_ref_id is None:
        return
    candidate = db.get(StrategyVersion, proposal.subject_ref_id)
    if candidate is None:
        return
    previously_active = db.scalar(
        select(StrategyVersion).where(
            StrategyVersion.strategy_definition_id == candidate.strategy_definition_id,
            StrategyVersion.status == StrategyVersionStatus.ACTIVE,
        )
    )
    if previously_active is not None:
        assert_transition_allowed(
            "StrategyVersion",
            previously_active.status.value,
            StrategyVersionStatus.SUPERSEDED.value,
            STRATEGY_VERSION_TRANSITIONS,
        )
        previously_active.status = StrategyVersionStatus.SUPERSEDED
    assert_transition_allowed(
        "StrategyVersion",
        candidate.status.value,
        StrategyVersionStatus.ACTIVE.value,
        STRATEGY_VERSION_TRANSITIONS,
    )
    candidate.status = StrategyVersionStatus.ACTIVE
    candidate.decided_at = datetime.now(UTC)
    candidate.decision_comment = f"Activated via ModelChangeProposal {proposal.id}"


def activate_change(
    db: Session, *, proposal_id: uuid.UUID, activated_by: str
) -> ModelChangeProposal:
    """The one and only function that makes a proposal's change take
    effect — requires `APPROVED` (never callable from `PROPOSED`
    directly; `MODEL_CHANGE_PROPOSAL_TRANSITIONS` has no such edge) and
    always requires its own explicit actor, distinct from whoever
    approved it."""
    proposal = _get_proposal(db, proposal_id)
    _transition(db, proposal, to_status=ModelChangeProposalStatus.ACTIVATED)
    if proposal.subject_type == "STRATEGY_PARAMETER":
        _activate_strategy_version(db, proposal)
    proposal.activated_at = datetime.now(UTC)
    proposal.activated_by = activated_by
    db.flush()
    return proposal


def rollback_change(
    db: Session, *, proposal_id: uuid.UUID, rolled_back_by: str, reason: str
) -> ModelChangeProposal:
    """Only legal from `ACTIVATED`. For a `STRATEGY_PARAMETER` subject,
    clones the config that was active *before* this proposal (read from
    the proposal's own `evidence_package["current_version_snapshot"]` —
    never a second live query that could disagree with what was actually
    proposed) into a brand-new `StrategyVersion`, activated immediately —
    see this module's own docstring for why rollback creates a new
    version rather than resurrecting the superseded one."""
    proposal = _get_proposal(db, proposal_id)
    _transition(db, proposal, to_status=ModelChangeProposalStatus.ROLLED_BACK)

    if proposal.subject_type == "STRATEGY_PARAMETER" and proposal.subject_ref_id is not None:
        candidate = db.get(StrategyVersion, proposal.subject_ref_id)
        if candidate is not None:
            assert_transition_allowed(
                "StrategyVersion",
                candidate.status.value,
                StrategyVersionStatus.SUPERSEDED.value,
                STRATEGY_VERSION_TRANSITIONS,
            )
            candidate.status = StrategyVersionStatus.SUPERSEDED
            prior_snapshot = proposal.evidence_package.get("current_version_snapshot")
            if prior_snapshot is not None:
                restored = StrategyVersion(
                    strategy_definition_id=candidate.strategy_definition_id,
                    config=prior_snapshot,
                    status=StrategyVersionStatus.ACTIVE,
                    decided_at=datetime.now(UTC),
                    decision_comment=(
                        f"Restored via rollback of ModelChangeProposal {proposal.id}: {reason}"
                    ),
                )
                db.add(restored)

    proposal.rolled_back_at = datetime.now(UTC)
    proposal.rolled_back_by = rolled_back_by
    proposal.rollback_reason = reason
    db.flush()
    return proposal


__all__ = [
    "BacktestSplitSummary",
    "ProposalNotFoundError",
    "activate_change",
    "approve_change",
    "propose_change",
    "propose_strategy_parameter_change",
    "reject_change",
    "rollback_change",
    "run_backtest_splits",
    "withdraw_change",
]
