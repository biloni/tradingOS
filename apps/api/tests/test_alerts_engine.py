"""Alert lifecycle engine tests (Revision Prompt 11 task 71) — dedup,
expiry, evidence-link, and audit-trail behavior of
`services/alerts_engine.py`, the one function every new Prompt 11
alert-producing call site goes through."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import AlertSeverity, AlertStatus, AlertType
from tradingos_api.models.operations import Alert, AlertStatusEvent
from tradingos_api.services.alerts_engine import create_or_dedupe_alert, expire_stale_alerts

_NOW = datetime(2026, 8, 10, 14, 0, tzinfo=UTC)


class TestCreation:
    def test_creates_an_open_alert_with_a_status_event(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        alert, created = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.STOP_REACHED,
            severity=AlertSeverity.CRITICAL,
            title="Stop reached",
            detail="AMD hit its stop price.",
            triggered_at=_NOW,
        )
        assert created is True
        assert alert.status == AlertStatus.OPEN
        events = db_session.scalars(
            select(AlertStatusEvent).where(AlertStatusEvent.alert_id == alert.id)
        ).all()
        assert len(events) == 1
        assert events[0].from_status is None
        assert events[0].to_status == AlertStatus.OPEN

    def test_default_ttl_sets_expires_at_from_triggered_at(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        alert, _ = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.STOP_REACHED,
            severity=AlertSeverity.CRITICAL,
            title="Stop reached",
            detail=None,
            triggered_at=_NOW,
        )
        assert alert.expires_at == _NOW + timedelta(days=3)

    def test_explicit_ttl_overrides_the_default(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        alert, _ = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.STOP_REACHED,
            severity=AlertSeverity.CRITICAL,
            title="Stop reached",
            detail=None,
            triggered_at=_NOW,
            ttl=timedelta(hours=1),
        )
        assert alert.expires_at == _NOW + timedelta(hours=1)

    def test_evidence_link_is_persisted(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        evidence_id = uuid.uuid4()
        alert, _ = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.TARGET_REACHED,
            severity=AlertSeverity.INFO,
            title="Target reached",
            detail=None,
            triggered_at=_NOW,
            evidence_type="Position",
            evidence_id=evidence_id,
        )
        assert alert.evidence_type == "Position"
        assert alert.evidence_id == evidence_id


class TestDeduplication:
    def test_second_call_with_the_same_open_dedup_key_returns_the_existing_alert(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        key = f"stop-reached:{uuid.uuid4()}"
        first, first_created = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.STOP_REACHED,
            severity=AlertSeverity.CRITICAL,
            title="Stop reached",
            detail=None,
            triggered_at=_NOW,
            dedup_key=key,
        )
        second, second_created = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.STOP_REACHED,
            severity=AlertSeverity.CRITICAL,
            title="Stop reached (re-fired)",
            detail=None,
            triggered_at=_NOW + timedelta(minutes=5),
            dedup_key=key,
        )
        assert first_created is True
        assert second_created is False
        assert second.id == first.id
        assert second.title == "Stop reached"  # unchanged, not overwritten

        rows = db_session.scalars(select(Alert).where(Alert.dedup_key == key)).all()
        assert len(rows) == 1

    def test_a_new_alert_with_the_same_key_can_fire_again_once_the_prior_one_is_dismissed(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        key = f"stop-reached:{uuid.uuid4()}"
        first, _ = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.STOP_REACHED,
            severity=AlertSeverity.CRITICAL,
            title="Stop reached",
            detail=None,
            triggered_at=_NOW,
            dedup_key=key,
        )
        first.status = AlertStatus.DISMISSED
        db_session.flush()

        second, second_created = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.STOP_REACHED,
            severity=AlertSeverity.CRITICAL,
            title="Stop reached again",
            detail=None,
            triggered_at=_NOW + timedelta(days=1),
            dedup_key=key,
        )
        assert second_created is True
        assert second.id != first.id

        rows = db_session.scalars(select(Alert).where(Alert.dedup_key == key)).all()
        assert len(rows) == 2


class TestExpiry:
    def test_expire_stale_alerts_dismisses_only_past_expiry(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        expired, _ = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.DATA_STALE,
            severity=AlertSeverity.WARNING,
            title="Stale quote",
            detail=None,
            triggered_at=_NOW,
        )
        not_yet_expired, _ = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.MARKET_REGIME_CHANGED,
            severity=AlertSeverity.INFO,
            title="Regime changed",
            detail=None,
            triggered_at=_NOW,
        )
        db_session.flush()

        expired_list = expire_stale_alerts(db_session, now=_NOW + timedelta(hours=5))

        assert [a.id for a in expired_list] == [expired.id]
        db_session.refresh(expired)
        db_session.refresh(not_yet_expired)
        assert expired.status == AlertStatus.DISMISSED
        assert not_yet_expired.status == AlertStatus.OPEN

        events = db_session.scalars(
            select(AlertStatusEvent)
            .where(AlertStatusEvent.alert_id == expired.id)
            .order_by(AlertStatusEvent.changed_at)
        ).all()
        assert len(events) == 2
        assert events[-1].to_status == AlertStatus.DISMISSED
        assert events[-1].changed_by == "system:expiry"

    def test_an_expired_alerts_dedup_key_becomes_reusable(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        key = f"data-stale:{uuid.uuid4()}"
        create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.DATA_STALE,
            severity=AlertSeverity.WARNING,
            title="Stale quote",
            detail=None,
            triggered_at=_NOW,
            dedup_key=key,
        )
        db_session.flush()
        expire_stale_alerts(db_session, now=_NOW + timedelta(hours=5))

        _, created = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.DATA_STALE,
            severity=AlertSeverity.WARNING,
            title="Stale quote again",
            detail=None,
            triggered_at=_NOW + timedelta(hours=6),
            dedup_key=key,
        )
        assert created is True

    def test_alerts_without_a_ttl_default_never_expire(
        self, db_session: Session, seeded_user_id: uuid.UUID
    ) -> None:
        alert, _ = create_or_dedupe_alert(
            db_session,
            owner_user_id=seeded_user_id,
            alert_type=AlertType.STOP_REACHED,
            severity=AlertSeverity.CRITICAL,
            title="Stop reached",
            detail=None,
            triggered_at=_NOW,
            ttl=None,
        )
        assert alert.expires_at is not None  # STOP_REACHED has a default TTL

        no_ttl_alert = Alert(
            owner_user_id=seeded_user_id,
            alert_type=AlertType.STOP_REACHED,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.OPEN,
            title="Manually constructed, no expiry",
            triggered_at=_NOW,
            expires_at=None,
        )
        db_session.add(no_ttl_alert)
        db_session.flush()

        expire_stale_alerts(db_session, now=_NOW + timedelta(days=365))
        db_session.refresh(no_ttl_alert)
        assert no_ttl_alert.status == AlertStatus.OPEN
