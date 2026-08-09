"""CSV import idempotency tests (Revision Prompt 8) — re-uploading the
exact same file is a no-op at the batch level; a logical fill repeated
across two different files is caught at the row level."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import ImportRowStatus
from tradingos_api.models.execution import Account
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.csv_import import import_execution_csv
from tradingos_api.services.portfolio_accounting import get_open_lots


def _account(db_session: Session) -> Account:
    account = db_session.scalar(select(Account).limit(1))
    assert account is not None
    return account


def _instrument(db_session: Session) -> Instrument:
    inst = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
    assert inst is not None
    return inst


_CSV_TEMPLATE = (
    b"executed_at,side,ticker,quantity,price,lane\n"
    b"2026-01-15T14:30:00Z,BUY,AMD,100,75.00,TACTICAL\n"
)


class TestCsvImportIdempotency:
    def test_reimporting_the_identical_file_is_a_no_op(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)

        first = import_execution_csv(
            db_session,
            account_id=account.id,
            filename="fills.csv",
            file_bytes=_CSV_TEMPLATE,
            imported_at=datetime.now(UTC),
        )
        assert first.was_duplicate_batch is False
        assert first.rows[0].status == ImportRowStatus.IMPORTED

        second = import_execution_csv(
            db_session,
            account_id=account.id,
            filename="fills.csv",
            file_bytes=_CSV_TEMPLATE,
            imported_at=datetime.now(UTC),
        )
        assert second.was_duplicate_batch is True
        assert second.batch.id == first.batch.id

        lots = get_open_lots(db_session, account_id=account.id, instrument_id=instrument.id)
        assert sum(lot.quantity_remaining for lot in lots) == Decimal(100)  # not 200

    def test_overlapping_row_across_two_different_files_is_row_level_deduped(
        self, db_session: Session
    ) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)

        file_a = _CSV_TEMPLATE
        file_b = (
            b"executed_at,side,ticker,quantity,price,lane\n"
            b"2026-01-15T14:30:00Z,BUY,AMD,100,75.00,TACTICAL\n"
            b"2026-01-16T14:30:00Z,BUY,AMD,25,80.00,TACTICAL\n"
        )

        import_execution_csv(
            db_session,
            account_id=account.id,
            filename="a.csv",
            file_bytes=file_a,
            imported_at=datetime.now(UTC),
        )
        outcome_b = import_execution_csv(
            db_session,
            account_id=account.id,
            filename="b.csv",
            file_bytes=file_b,
            imported_at=datetime.now(UTC),
        )

        statuses = [row.status for row in outcome_b.rows]
        assert statuses == [ImportRowStatus.DUPLICATE_SKIPPED, ImportRowStatus.IMPORTED]

        lots = get_open_lots(db_session, account_id=account.id, instrument_id=instrument.id)
        assert sum(lot.quantity_remaining for lot in lots) == Decimal(125)  # 100 + 25, not 225

    def test_unknown_ticker_produces_an_error_row_without_aborting_the_batch(
        self, db_session: Session
    ) -> None:
        account = _account(db_session)
        csv_bytes = (
            b"executed_at,side,ticker,quantity,price,lane\n"
            b"2026-01-15T14:30:00Z,BUY,NOTAREALTICKER,100,75.00,TACTICAL\n"
            b"2026-01-16T14:30:00Z,BUY,AMD,10,80.00,TACTICAL\n"
        )
        outcome = import_execution_csv(
            db_session,
            account_id=account.id,
            filename="mixed.csv",
            file_bytes=csv_bytes,
            imported_at=datetime.now(UTC),
        )
        assert outcome.rows[0].status == ImportRowStatus.ERROR
        assert outcome.rows[0].error_detail is not None
        assert outcome.rows[1].status == ImportRowStatus.IMPORTED
