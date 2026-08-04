"""Database constraint & index tests (docs/TASKS.md Phase 8 requirement).

Exercises real Postgres uniqueness/FK constraints and confirms the
indexes documented in the model docstrings actually exist — not just
that the ORM classes declare them. Every test runs inside `db_session`
(see conftest.py), which rolls back afterward.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    AccountType,
    CashLedgerEntryType,
    OrderSide,
    OrderStatus,
    OrderType,
)
from tradingos_api.models.execution import Account, CashLedgerEntry, Order, Position
from tradingos_api.models.security_master import Instrument, WatchlistItem


def _seeded_instrument_id(db_session: Session) -> uuid.UUID:
    row = db_session.execute(text("SELECT id FROM instruments LIMIT 1")).first()
    assert row is not None, "seed data must exist for constraint tests to run against"
    return cast(uuid.UUID, row[0])


def _seeded_watchlist_id(db_session: Session) -> uuid.UUID:
    row = db_session.execute(text("SELECT id FROM watchlists LIMIT 1")).first()
    assert row is not None
    return cast(uuid.UUID, row[0])


def _seeded_user_id(db_session: Session) -> uuid.UUID:
    row = db_session.execute(text("SELECT id FROM user_profile LIMIT 1")).first()
    assert row is not None
    return cast(uuid.UUID, row[0])


class TestUniqueConstraints:
    def test_instrument_ticker_must_be_unique(self, db_session: Session) -> None:
        db_session.add(
            Instrument(ticker="ZZZTEST", name="Dup Test 1", exchange="NYSE", asset_type="EQUITY")
        )
        db_session.flush()
        db_session.add(
            Instrument(ticker="ZZZTEST", name="Dup Test 2", exchange="NASDAQ", asset_type="EQUITY")
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_watchlist_item_rejects_duplicate_instrument_on_same_watchlist(
        self, db_session: Session
    ) -> None:
        watchlist_id = _seeded_watchlist_id(db_session)
        instrument_id = _seeded_instrument_id(db_session)
        existing = db_session.execute(
            text("SELECT 1 FROM watchlist_items WHERE watchlist_id=:w AND instrument_id=:i"),
            {"w": watchlist_id, "i": instrument_id},
        ).first()
        assert existing is not None, (
            "expected this instrument to already be seeded onto the watchlist"
        )
        db_session.add(
            WatchlistItem(
                watchlist_id=watchlist_id,
                instrument_id=instrument_id,
                tier=1,
                priority=999,
                active=True,
                monitoring_frequency="DAILY",
                added_at=datetime.now(UTC).date(),
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_position_rejects_duplicate_account_instrument_pair(self, db_session: Session) -> None:
        account = Account(
            account_type=AccountType.MANUAL,
            name="Constraint Test Acct",
            owner_user_id=_seeded_user_id(db_session),
        )
        db_session.add(account)
        db_session.flush()
        instrument_id = _seeded_instrument_id(db_session)
        db_session.add(
            Position(account_id=account.id, instrument_id=instrument_id, quantity=Decimal(1))
        )
        db_session.flush()
        db_session.add(
            Position(account_id=account.id, instrument_id=instrument_id, quantity=Decimal(2))
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_order_idempotency_key_must_be_unique(self, db_session: Session) -> None:
        account = Account(
            account_type=AccountType.MANUAL,
            name="Idempotency Test Acct",
            owner_user_id=_seeded_user_id(db_session),
        )
        db_session.add(account)
        db_session.flush()
        instrument_id = _seeded_instrument_id(db_session)
        key = f"dup-key-{uuid.uuid4()}"
        db_session.add(
            Order(
                account_id=account.id,
                instrument_id=instrument_id,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal(1),
                status=OrderStatus.DRAFT,
                idempotency_key=key,
            )
        )
        db_session.flush()
        db_session.add(
            Order(
                account_id=account.id,
                instrument_id=instrument_id,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=Decimal(1),
                status=OrderStatus.DRAFT,
                idempotency_key=key,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_cash_ledger_idempotency_key_must_be_unique(self, db_session: Session) -> None:
        account = Account(
            account_type=AccountType.MANUAL,
            name="Ledger Idempotency Acct",
            owner_user_id=_seeded_user_id(db_session),
        )
        db_session.add(account)
        db_session.flush()
        key = f"dup-ledger-key-{uuid.uuid4()}"
        now = datetime.now(UTC)
        db_session.add(
            CashLedgerEntry(
                account_id=account.id,
                entry_type=CashLedgerEntryType.TRADE_DEBIT,
                amount=Decimal("-100.00"),
                occurred_at=now,
                idempotency_key=key,
            )
        )
        db_session.flush()
        db_session.add(
            CashLedgerEntry(
                account_id=account.id,
                entry_type=CashLedgerEntryType.TRADE_CREDIT,
                amount=Decimal("100.00"),
                occurred_at=now,
                idempotency_key=key,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_news_item_dedup_hash_must_be_unique(self, db_session: Session) -> None:
        dedup_hash = f"hash-{uuid.uuid4().hex}"
        db_session.execute(
            text(
                "INSERT INTO news_items "
                "(id, canonical_url, publisher, headline, published_at, ingested_at, "
                "dedup_hash, license_metadata) "
                "VALUES (gen_random_uuid(), :url1, 'Reuters', 'Headline 1', now(), now(), "
                ":h, '{}')"
            ),
            {"url1": f"https://example.com/{uuid.uuid4()}", "h": dedup_hash},
        )
        db_session.flush()
        with pytest.raises(IntegrityError):
            db_session.execute(
                text(
                    "INSERT INTO news_items "
                    "(id, canonical_url, publisher, headline, published_at, ingested_at, "
                    "dedup_hash, license_metadata) "
                    "VALUES (gen_random_uuid(), :url2, 'Bloomberg', 'Headline 2', now(), now(), "
                    ":h, '{}')"
                ),
                {"url2": f"https://example.com/{uuid.uuid4()}", "h": dedup_hash},
            )
            db_session.flush()


class TestForeignKeys:
    def test_watchlist_item_rejects_unknown_instrument(self, db_session: Session) -> None:
        watchlist_id = _seeded_watchlist_id(db_session)
        db_session.add(
            WatchlistItem(
                watchlist_id=watchlist_id,
                instrument_id=uuid.uuid4(),
                tier=1,
                priority=1,
                active=True,
                monitoring_frequency="DAILY",
                added_at=datetime.now(UTC).date(),
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_order_rejects_unknown_account(self, db_session: Session) -> None:
        instrument_id = _seeded_instrument_id(db_session)
        db_session.add(
            Order(
                account_id=uuid.uuid4(),
                instrument_id=instrument_id,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal(1),
                status=OrderStatus.DRAFT,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestDocumentedIndexesExist:
    """Spot-checks the named indexes each model docstring/comment promises."""

    @pytest.mark.parametrize(
        "index_name,table_name",
        [
            ("ix_cash_ledger_account", "cash_ledger"),
            ("ix_position_lots_open", "position_lots"),
            ("ix_executions_order", "executions"),
            ("ix_market_bars_lookup", "market_bars"),
            ("ix_agent_evidence_links_lookup", "agent_evidence_links"),
            ("ix_data_quality_events_subject", "data_quality_events"),
        ],
    )
    def test_index_exists(self, db_session: Session, index_name: str, table_name: str) -> None:
        row = db_session.execute(
            text("SELECT 1 FROM pg_indexes WHERE indexname = :idx AND tablename = :tbl"),
            {"idx": index_name, "tbl": table_name},
        ).first()
        assert row is not None, f"expected index {index_name} on {table_name} to exist"
