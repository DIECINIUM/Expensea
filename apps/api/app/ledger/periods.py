"""User-calendar periods converted to precise UTC query boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.ledger.errors import LedgerValidationError


@dataclass(frozen=True, slots=True)
class YearMonth:
    """A validated calendar month."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if self.year < 2000 or self.year > 2100:
            raise LedgerValidationError(
                code="INVALID_YEAR",
                message="year must be between 2000 and 2100.",
                field="year",
            )
        if self.month < 1 or self.month > 12:
            raise LedgerValidationError(
                code="INVALID_MONTH",
                message="month must be between 1 and 12.",
                field="month",
            )

    @classmethod
    def containing(cls, instant: datetime, timezone_name: str) -> YearMonth:
        """Return the user's local month containing one aware instant."""
        timezone = parse_timezone(timezone_name)
        if instant.tzinfo is None or instant.utcoffset() is None:
            msg = "Month lookup requires a timezone-aware instant"
            raise ValueError(msg)
        local = instant.astimezone(timezone)
        return cls(year=local.year, month=local.month)

    def next(self) -> YearMonth:
        """Return the following calendar month."""
        if self.month == 12:
            return YearMonth(year=self.year + 1, month=1)
        return YearMonth(year=self.year, month=self.month + 1)

    def previous(self) -> YearMonth:
        """Return the preceding calendar month."""
        if self.month == 1:
            return YearMonth(year=self.year - 1, month=12)
        return YearMonth(year=self.year, month=self.month - 1)


@dataclass(frozen=True, slots=True)
class MonthPeriod:
    """Half-open UTC instants and local dates for a user-calendar month."""

    month: YearMonth
    start_date: date
    end_date: date
    start_utc: datetime
    end_utc: datetime


def parse_timezone(timezone_name: str) -> ZoneInfo:
    """Resolve an IANA timezone into a client-safe validation failure."""
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        raise LedgerValidationError(
            code="INVALID_TIMEZONE",
            message="The configured user timezone is not recognized.",
            field="timezone",
        ) from None


def month_period(month: YearMonth, timezone_name: str) -> MonthPeriod:
    """Convert local month midnights to a DST-safe half-open UTC interval."""
    timezone = parse_timezone(timezone_name)
    following = month.next()
    start_date = date(month.year, month.month, 1)
    end_date = date(following.year, following.month, 1)
    start_local = datetime.combine(start_date, datetime.min.time(), timezone)
    end_local = datetime.combine(end_date, datetime.min.time(), timezone)
    return MonthPeriod(
        month=month,
        start_date=start_date,
        end_date=end_date,
        start_utc=start_local.astimezone(UTC),
        end_utc=end_local.astimezone(UTC),
    )


def previous_months(ending: YearMonth, count: int) -> list[YearMonth]:
    """Return ascending months ending with ``ending``."""
    if count < 1 or count > 24:
        raise LedgerValidationError(
            code="INVALID_MONTH_COUNT",
            message="months must be between 1 and 24.",
            field="months",
        )

    months = [ending]
    while len(months) < count:
        months.append(months[-1].previous())
    months.reverse()
    return months
