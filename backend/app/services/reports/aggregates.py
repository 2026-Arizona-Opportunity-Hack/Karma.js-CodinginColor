"""Date-range rules shared by the public API and the app's reports."""

from datetime import date, timedelta

from app.clock import Clock, today
from app.errors import Invalid


def resolve_range(clock: Clock, start: date | None, end: date | None) -> tuple[date, date]:
    """Default: the last 12 months ending today (Phoenix). `from` must not be after `to`."""
    end = end or today(clock)
    start = start or end - timedelta(days=364)
    if start > end:
        raise Invalid("`from` must not be after `to`.")
    if (end - start).days > 3660:
        raise Invalid("Date range is limited to 10 years.")
    return start, end
