"""Injectable clock. Business dates are in America/Phoenix (NFR-6)."""

from datetime import UTC, date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

PHOENIX = ZoneInfo("America/Phoenix")


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """For tests: always returns the same instant, can be moved forward."""

    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("FixedClock needs an aware datetime")
        self.at = at

    def now(self) -> datetime:
        return self.at


def today(clock: Clock) -> date:
    """The business date in Phoenix for the clock's current instant."""
    return clock.now().astimezone(PHOENIX).date()


_clock: Clock = SystemClock()


def get_clock() -> Clock:
    return _clock


def set_clock(clock: Clock) -> None:
    global _clock
    _clock = clock
