"""Alert lifecycle engine (Revision Prompt 11) — `create_or_dedupe_alert()`
is the one function every *new* alert-producing call site
(`services/position_monitor.py`, `services/post_earnings_workflow.py`)
goes through, so "alerts must be deterministic where possible,
deduplicated, expiring, evidence-linked, and audited" (Prompt 11's own
requirement list) is enforced structurally rather than by convention at
each call site. `AlertType`'s docstring (`models/enums.py`) documents the
one exception: two pre-Prompt-11 call sites in `services/ingest_evidence.py`
and `routers/morning_plan.py` predate this engine and construct `Alert`
directly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import ALERT_TRANSITIONS, AlertSeverity, AlertStatus, AlertType
from tradingos_api.models.operations import Alert, AlertStatusEvent
from tradingos_api.services.lifecycle import assert_transition_allowed

DEFAULT_ALERT_TTL: dict[AlertType, timedelta] = {
    # Documented, per-type defaults — not tuned against real usage data
    # (no live user population exists to tune against), but deliberately
    # not a single flat constant: a still-actionable TARGET_REACHED
    # should outlive a session, while a data-freshness signal like
    # DATA_STALE should stop being surfaced once the engine has had a
    # reasonable chance to re-run with fresher data even absent an
    # explicit dismissal.
    AlertType.ENTRY_ZONE_REACHED: timedelta(days=1),
    AlertType.APPROVAL_REQUIRED: timedelta(hours=4),
    AlertType.ORDER_STATUS_CHANGED: timedelta(days=1),
    AlertType.TARGET_REACHED: timedelta(days=3),
    AlertType.STOP_REACHED: timedelta(days=3),
    AlertType.GAP_RISK: timedelta(days=1),
    AlertType.THESIS_INVALIDATED: timedelta(days=7),
    AlertType.EARNINGS_APPROACHING: timedelta(days=7),
    AlertType.RESULTS_AVAILABLE: timedelta(days=3),
    AlertType.GUIDANCE_CONFLICT: timedelta(days=3),
    AlertType.POST_EARNINGS_CONFIRMATION_READY: timedelta(days=1),
    AlertType.POST_EARNINGS_CONFIRMATION_FAILED: timedelta(days=3),
    AlertType.TAKE_PARTIAL_PROFIT_SUGGESTION: timedelta(days=1),
    AlertType.EXIT_SUGGESTION: timedelta(days=1),
    AlertType.DATA_STALE: timedelta(hours=4),
    AlertType.PROVIDER_OUTAGE: timedelta(hours=4),
    AlertType.PORTFOLIO_LIMIT_BREACH: timedelta(days=1),
    AlertType.MARKET_REGIME_CHANGED: timedelta(days=7),
    AlertType.SYSTEM_NOTIFICATION: timedelta(days=30),
}


def create_or_dedupe_alert(
    db: Session,
    *,
    owner_user_id: uuid.UUID,
    alert_type: AlertType,
    severity: AlertSeverity,
    title: str,
    detail: str | None,
    triggered_at: datetime,
    dedup_key: str | None = None,
    evidence_type: str | None = None,
    evidence_id: uuid.UUID | None = None,
    instrument_id: uuid.UUID | None = None,
    ttl: timedelta | None = None,
) -> tuple[Alert, bool]:
    """Returns `(alert, created)`. If an `OPEN` alert with the same
    `dedup_key` already exists, that row is returned unchanged and
    `created=False` — deterministic dedup, never a second row for a
    condition that is still active (mirrors the DB-level guarantee
    `ix_alerts_unique_open_dedup_key` enforces at the schema layer).
    Because the partial unique index only covers `status='OPEN'`, a
    dismissed or expired alert's key is free to fire again: a genuinely
    new occurrence of the same condition after resolution creates a new
    row rather than being silently swallowed forever.

    `ttl=None` (the default) looks up `DEFAULT_ALERT_TTL` for
    `alert_type`; pass an explicit `ttl` to override, or `timedelta()`-
    like zero is not treated specially — pass `ttl=None` and omit the
    type from `DEFAULT_ALERT_TTL` for a genuinely non-expiring alert
    (none of the 19 current types do this, but the mechanism supports it).
    """
    if dedup_key is not None:
        existing = db.scalar(
            select(Alert).where(Alert.dedup_key == dedup_key, Alert.status == AlertStatus.OPEN)
        )
        if existing is not None:
            return existing, False

    effective_ttl = ttl if ttl is not None else DEFAULT_ALERT_TTL.get(alert_type)
    expires_at = triggered_at + effective_ttl if effective_ttl is not None else None

    alert = Alert(
        owner_user_id=owner_user_id,
        instrument_id=instrument_id,
        alert_type=alert_type,
        severity=severity,
        status=AlertStatus.OPEN,
        title=title,
        detail=detail,
        triggered_at=triggered_at,
        expires_at=expires_at,
        dedup_key=dedup_key,
        evidence_type=evidence_type,
        evidence_id=evidence_id,
    )
    db.add(alert)
    db.flush()
    db.add(
        AlertStatusEvent(
            alert_id=alert.id,
            from_status=None,
            to_status=AlertStatus.OPEN,
            changed_at=triggered_at,
            changed_by=None,
        )
    )
    db.flush()
    return alert, True


def transition_alert_status(
    db: Session,
    alert: Alert,
    *,
    to_status: AlertStatus,
    changed_at: datetime,
    changed_by: str | None,
) -> Alert:
    """The one place `Alert.status` is ever mutated after creation —
    always paired with an `AlertStatusEvent` audit row, never a bare
    column write, so every transition (human acknowledge/dismiss via
    `routers/alerts.py`, or a system-driven expiry below) is auditable."""
    assert_transition_allowed("Alert", alert.status, to_status, ALERT_TRANSITIONS)
    from_status = alert.status
    alert.status = to_status
    db.add(
        AlertStatusEvent(
            alert_id=alert.id,
            from_status=from_status,
            to_status=to_status,
            changed_at=changed_at,
            changed_by=changed_by,
        )
    )
    db.flush()
    return alert


def expire_stale_alerts(db: Session, *, now: datetime | None = None) -> list[Alert]:
    """Lazily transitions every `OPEN` alert whose `expires_at` has
    passed to `DISMISSED` — "expiring" per Prompt 11's own requirement,
    implemented without a dedicated `EXPIRED` status: an expiry-driven
    dismissal is distinguished from a human one only by
    `changed_by="system:expiry"` on the resulting `AlertStatusEvent`,
    since no required behavior (routing, display, re-fire eligibility)
    actually depends on telling the two apart at the schema level — both
    free the alert's `dedup_key` identically via the same partial index.
    Call this from any read path that lists alerts (`routers/alerts.py`,
    the alert-center endpoint) before returning results, so an expired
    alert never surfaces as still-open."""
    effective_now = now if now is not None else datetime.now(UTC)
    stale = db.scalars(
        select(Alert).where(
            Alert.status == AlertStatus.OPEN,
            Alert.expires_at.is_not(None),
            Alert.expires_at <= effective_now,
        )
    ).all()
    for alert in stale:
        transition_alert_status(
            db,
            alert,
            to_status=AlertStatus.DISMISSED,
            changed_at=effective_now,
            changed_by="system:expiry",
        )
    return list(stale)
