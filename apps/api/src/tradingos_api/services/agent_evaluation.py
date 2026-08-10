"""Agent evaluation (Revision Prompt 14) — six dimensions, every one
computed from real `AgentRun`/`AgentOpinion`/`AgentEvidenceLink`/
`CommitteeSession` data joined to real outcomes
(`RecommendationOutcome`/`HypotheticalTradeOutcome`), never graded by a
second LLM call and never self-reported by the role being evaluated.
docs/MODEL_GOVERNANCE.md's own "Evaluation" section explicitly scoped
"grading committee narrative quality" out — this module does not attempt
that; it measures observable, checkable properties instead:

1. **Factual accuracy** — the fraction of a role's cited evidence
   (`AgentEvidenceLink`) that was never later subject to an
   `EarningsEventCorrection` for the same earnings event. A role that
   frequently cites evidence later found wrong scores lower, regardless
   of how confident its narrative sounded.
2. **Evidence coverage** — cited evidence ids ÷ the full evidence bundle
   offered to that run (`AgentRun.input_snapshot["evidence_ids"]`).
3. **Contradiction detection** — the fraction of this role's sessions in
   which the committee's own stances actually disagreed (more than one
   distinct non-`NEUTRAL` `categorical_stance` among that session's
   roles) — a structural "was disagreement even visible" signal, not a
   claim about whether this specific role personally flagged it in prose.
4. **Directional usefulness** — the fraction of this role's opinions
   whose `categorical_stance` direction matched the eventual outcome
   (`is_win`from a real or hypothetical fill).
5. **Contribution after deterministic features** — directional
   usefulness computed *only* over the subset of opinions where this
   role's stance disagreed with the deterministic score's implied
   direction (`score >= 6` ⇒ bullish-leaning, HES-2's own live
   threshold) — a role that is only ever right when it agrees with the
   deterministic signal is adding no information beyond it; one that
   stays right even when it disagrees is.
6. **Minority-opinion usefulness** — directional usefulness computed
   only over instances where this role's stance was the minority view
   within its own session (differed from that session's modal stance).

Every metric is sample-size gated exactly like `services/calibration.py`
— `None` below `MIN_SAMPLE_SIZE_FOR_AGENT_EVAL`, never a rate computed
from a handful of runs and presented as if it meant something."""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.agents import (
    AgentDefinition,
    AgentEvidenceLink,
    AgentOpinion,
    AgentRun,
    AgentVersion,
)
from tradingos_api.models.enums import AgentRole, AgentRunStatus
from tradingos_api.models.learning import HypotheticalTradeOutcome, RecommendationOutcome
from tradingos_api.models.market_evidence import EarningsEventCorrection
from tradingos_api.models.recommendations import RecommendationVersion

CALCULATION_VERSION = "v1"
MIN_SAMPLE_SIZE_FOR_AGENT_EVAL = 10
"""Documented placeholder (no statistically-derived minimum exists for
this project's own committee-run population yet) — deliberately smaller
than `services/calibration.py::MIN_SAMPLE_SIZE_FOR_CALIBRATION` since a
per-role sample is a strict subset of the recommendation-level sample it
draws from and will always be sparser first."""

_BULLISH_SCORE_THRESHOLD = Decimal(6)
"""HES-2's own live gate threshold (`services/baseline_eligibility.py::_MIN_DIRECTION_SCORE`),
reused here as the deterministic "implied direction" a role's stance is
compared against for the contribution-beyond-deterministic-features
metric — not re-derived independently."""


@dataclass(frozen=True)
class _RunRecord:
    agent_run_id: uuid.UUID
    committee_session_id: uuid.UUID
    stance: str
    cited_evidence_count: int
    offered_evidence_count: int
    correction_tainted_citation_count: int
    is_win: bool | None
    deterministic_score: Decimal | None


@dataclass(frozen=True)
class AgentEvaluationResult:
    agent_role: str
    sample_size: int
    is_adequate: bool
    factual_accuracy_pct: Decimal | None
    evidence_coverage_pct: Decimal | None
    contradiction_detection_rate_pct: Decimal | None
    directional_usefulness_pct: Decimal | None
    contribution_after_deterministic_pct: Decimal | None
    contribution_sample_size: int
    minority_opinion_usefulness_pct: Decimal | None
    minority_sample_size: int
    calculation_version: str = CALCULATION_VERSION


def _pct(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)) * Decimal(100)


def _outcome_by_committee_session(db: Session) -> dict[uuid.UUID, bool]:
    """`committee_session_id -> is_win`, for every session whose
    `RecommendationVersion` has a determined real or hypothetical
    outcome — the same "never blend actual and hypothetical without
    saying so, only include a *determined* result" discipline
    `services/calibration.py::get_closed_outcomes()` already applies."""
    rows = db.execute(
        select(
            RecommendationVersion.committee_session_id,
            RecommendationVersion.recommendation_id,
        ).where(RecommendationVersion.committee_session_id.is_not(None))
    ).all()
    if not rows:
        return {}
    recommendation_ids = [rec_id for _, rec_id in rows]

    real_outcomes: dict[uuid.UUID, bool] = {}
    for o in db.scalars(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id.in_(recommendation_ids),
            RecommendationOutcome.realized_pnl.is_not(None),
        )
    ).all():
        if o.realized_pnl is not None:
            real_outcomes[o.recommendation_id] = o.realized_pnl > 0

    hypothetical_outcomes: dict[uuid.UUID, bool] = {}
    for h in db.scalars(
        select(HypotheticalTradeOutcome)
        .where(
            HypotheticalTradeOutcome.recommendation_id.in_(recommendation_ids),
            HypotheticalTradeOutcome.simulated_pnl_pct.is_not(None),
        )
        .order_by(HypotheticalTradeOutcome.computed_at.desc())
    ).all():
        if h.simulated_pnl_pct is not None:
            hypothetical_outcomes.setdefault(h.recommendation_id, h.simulated_pnl_pct > 0)

    result: dict[uuid.UUID, bool] = {}
    for session_id, rec_id in rows:
        if session_id is None:
            continue
        if rec_id in real_outcomes:
            result[session_id] = real_outcomes[rec_id]
        elif rec_id in hypothetical_outcomes:
            result[session_id] = hypothetical_outcomes[rec_id]
    return result


def _score_by_committee_session(db: Session) -> dict[uuid.UUID, Decimal | None]:
    rows = db.execute(
        select(RecommendationVersion.committee_session_id, RecommendationVersion.score).where(
            RecommendationVersion.committee_session_id.is_not(None)
        )
    ).all()
    return {session_id: score for session_id, score in rows if session_id is not None}


def _correction_tainted_evidence_ids(db: Session) -> set[uuid.UUID]:
    """Every `earnings_event_id` that has ever had a correction recorded
    — an evidence citation pointing at a row tied to one of these events
    is treated as "later found to need revision," the concrete, checkable
    proxy for factual accuracy this module uses (see module docstring)."""
    return set(db.scalars(select(EarningsEventCorrection.earnings_event_id).distinct()).all())


def _session_stances(db: Session, session_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    if not session_ids:
        return {}
    rows = db.execute(
        select(AgentRun.committee_session_id, AgentOpinion.stance)
        .join(AgentOpinion, AgentOpinion.agent_run_id == AgentRun.id)
        .where(AgentRun.committee_session_id.in_(session_ids))
    ).all()
    result: dict[uuid.UUID, list[str]] = {}
    for session_id, stance in rows:
        if stance is not None:
            result.setdefault(session_id, []).append(stance)
    return result


def evaluate_agent_role(db: Session, *, role: AgentRole) -> AgentEvaluationResult:
    """The one entry point — every metric for one committee role, always
    returned together so a caller never sees factual accuracy without
    also seeing directional usefulness for the same underlying sample."""
    records = _fetch_runs_for_role(db, role)
    n = len(records)
    if n == 0:
        return AgentEvaluationResult(
            agent_role=role.value,
            sample_size=0,
            is_adequate=False,
            factual_accuracy_pct=None,
            evidence_coverage_pct=None,
            contradiction_detection_rate_pct=None,
            directional_usefulness_pct=None,
            contribution_after_deterministic_pct=None,
            contribution_sample_size=0,
            minority_opinion_usefulness_pct=None,
            minority_sample_size=0,
        )

    total_cited = sum(r.cited_evidence_count for r in records)
    total_offered = sum(r.offered_evidence_count for r in records)
    total_tainted = sum(r.correction_tainted_citation_count for r in records)

    session_ids = list({r.committee_session_id for r in records})
    stances_by_session = _session_stances(db, session_ids)
    contradiction_sessions = sum(
        1
        for sid in {r.committee_session_id for r in records}
        if len({s for s in stances_by_session.get(sid, []) if s != "NEUTRAL"}) > 1
    )

    directional_hits = 0
    directional_total = 0
    disagreement_hits = 0
    disagreement_total = 0
    minority_hits = 0
    minority_total = 0

    for r in records:
        if r.is_win is None or r.stance == "NEUTRAL":
            continue
        stance_bullish = r.stance == "BULLISH"
        directional_total += 1
        correct = stance_bullish == r.is_win
        if correct:
            directional_hits += 1

        if r.deterministic_score is not None:
            deterministic_bullish = r.deterministic_score >= _BULLISH_SCORE_THRESHOLD
            if stance_bullish != deterministic_bullish:
                disagreement_total += 1
                if correct:
                    disagreement_hits += 1

        session_stances = stances_by_session.get(r.committee_session_id, [])
        non_neutral = [s for s in session_stances if s != "NEUTRAL"]
        if non_neutral:
            modal_stance, _ = Counter(non_neutral).most_common(1)[0]
            if r.stance != modal_stance:
                minority_total += 1
                if correct:
                    minority_hits += 1

    return AgentEvaluationResult(
        agent_role=role.value,
        sample_size=n,
        is_adequate=n >= MIN_SAMPLE_SIZE_FOR_AGENT_EVAL,
        factual_accuracy_pct=(
            _pct(total_cited - total_tainted, total_cited)
            if n >= MIN_SAMPLE_SIZE_FOR_AGENT_EVAL
            else None
        ),
        evidence_coverage_pct=(
            _pct(total_cited, total_offered) if n >= MIN_SAMPLE_SIZE_FOR_AGENT_EVAL else None
        ),
        contradiction_detection_rate_pct=(
            _pct(contradiction_sessions, len(session_ids))
            if n >= MIN_SAMPLE_SIZE_FOR_AGENT_EVAL
            else None
        ),
        directional_usefulness_pct=(
            _pct(directional_hits, directional_total)
            if directional_total >= MIN_SAMPLE_SIZE_FOR_AGENT_EVAL
            else None
        ),
        contribution_after_deterministic_pct=(
            _pct(disagreement_hits, disagreement_total)
            if disagreement_total >= MIN_SAMPLE_SIZE_FOR_AGENT_EVAL
            else None
        ),
        contribution_sample_size=disagreement_total,
        minority_opinion_usefulness_pct=(
            _pct(minority_hits, minority_total)
            if minority_total >= MIN_SAMPLE_SIZE_FOR_AGENT_EVAL
            else None
        ),
        minority_sample_size=minority_total,
    )


def _fetch_runs_for_role(db: Session, role: AgentRole) -> list[_RunRecord]:
    run_rows = db.execute(
        select(AgentRun, AgentOpinion)
        .join(AgentVersion, AgentRun.agent_version_id == AgentVersion.id)
        .join(AgentDefinition, AgentVersion.agent_definition_id == AgentDefinition.id)
        .join(AgentOpinion, AgentOpinion.agent_run_id == AgentRun.id)
        .where(AgentDefinition.role == role, AgentRun.status == AgentRunStatus.SUCCEEDED)
    ).all()
    if not run_rows:
        return []

    run_ids = [run.id for run, _ in run_rows]

    citation_counts: dict[uuid.UUID, int] = {}
    tainted_counts: dict[uuid.UUID, int] = {}
    tainted_earnings_event_ids = _correction_tainted_evidence_ids(db)
    for link in db.scalars(
        select(AgentEvidenceLink).where(AgentEvidenceLink.agent_run_id.in_(run_ids))
    ).all():
        citation_counts[link.agent_run_id] = citation_counts.get(link.agent_run_id, 0) + 1
        if link.evidence_type == "EarningsEvent" and link.evidence_id in tainted_earnings_event_ids:
            tainted_counts[link.agent_run_id] = tainted_counts.get(link.agent_run_id, 0) + 1

    outcome_by_session = _outcome_by_committee_session(db)
    score_by_session = _score_by_committee_session(db)

    records: list[_RunRecord] = []
    for run, opinion in run_rows:
        offered = len(run.input_snapshot.get("evidence_ids", [])) if run.input_snapshot else 0
        records.append(
            _RunRecord(
                agent_run_id=run.id,
                committee_session_id=run.committee_session_id,
                stance=opinion.stance or "NEUTRAL",
                cited_evidence_count=citation_counts.get(run.id, 0),
                offered_evidence_count=offered,
                correction_tainted_citation_count=tainted_counts.get(run.id, 0),
                is_win=outcome_by_session.get(run.committee_session_id),
                deterministic_score=score_by_session.get(run.committee_session_id),
            )
        )
    return records
