"""Unit checks for ledger periods and opaque pagination."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.ledger.errors import InvalidCursorError, LedgerValidationError
from app.ledger.pagination import (
    TransactionCursor,
    decode_transaction_cursor,
    encode_transaction_cursor,
    validate_page_size,
)
from app.ledger.periods import YearMonth, month_period, previous_months


def test_transaction_cursor_round_trips_utc_sort_keys() -> None:
    cursor = TransactionCursor(
        occurred_at=datetime(2026, 7, 23, 12, 30, 45, 123456, tzinfo=UTC),
        transaction_id=UUID("29ad141a-1ec0-4514-b3f1-b40f31e79a2e"),
    )

    encoded = encode_transaction_cursor(cursor)

    assert decode_transaction_cursor(encoded) == cursor
    assert "2026" not in encoded


@pytest.mark.parametrize(
    "raw_cursor",
    [
        "",
        "not base64!",
        "eyJ2IjoyfQ",
        "eyJhdCI6IjIwMjYtMDctMjNUMTI6MDA6MDBaIiwiaWQiOiJiYWQtaWQiLCJ2IjoxfQ",
    ],
)
def test_invalid_transaction_cursor_is_a_stable_client_failure(raw_cursor: str) -> None:
    with pytest.raises(InvalidCursorError) as exc_info:
        decode_transaction_cursor(raw_cursor)

    assert exc_info.value.code == "INVALID_CURSOR"
    assert exc_info.value.field == "after"


@pytest.mark.parametrize("first", [1, 20, 100])
def test_page_size_accepts_bounded_values(first: int) -> None:
    assert validate_page_size(first) == first


@pytest.mark.parametrize("first", [0, 101])
def test_page_size_rejects_unbounded_values(first: int) -> None:
    with pytest.raises(LedgerValidationError, match="between 1 and 100"):
        validate_page_size(first)


def test_kolkata_month_boundaries_are_converted_to_utc() -> None:
    period = month_period(YearMonth(2026, 7), "Asia/Kolkata")

    assert period.start_utc == datetime(2026, 6, 30, 18, 30, tzinfo=UTC)
    assert period.end_utc == datetime(2026, 7, 31, 18, 30, tzinfo=UTC)


def test_new_york_dst_month_uses_local_midnights_not_fixed_utc_days() -> None:
    period = month_period(YearMonth(2026, 3), "America/New_York")

    assert period.start_utc == datetime(2026, 3, 1, 5, 0, tzinfo=UTC)
    assert period.end_utc == datetime(2026, 4, 1, 4, 0, tzinfo=UTC)


def test_previous_months_crosses_year_boundary_in_ascending_order() -> None:
    assert previous_months(YearMonth(2026, 2), 4) == [
        YearMonth(2025, 11),
        YearMonth(2025, 12),
        YearMonth(2026, 1),
        YearMonth(2026, 2),
    ]
