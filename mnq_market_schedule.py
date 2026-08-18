from datetime import (
    time,
)

import pandas as pd

from cme_calendar import (
    is_cme_holiday_window,
)


CHICAGO_TZ = "America/Chicago"

BAR_MINUTES = 5


# ============================================================
# STANDARD MICRO E-MINI EQUITY INDEX HOURS
#
# CME:
# Sunday-Friday:
#   17:00 CT open
#   16:00 CT close
#
# Daily maintenance:
#   16:00-17:00 CT
#
# Daily trading halt:
#   15:15-15:30 CT
#
# Holiday schedules are NOT inferred here because CME states
# that holiday hours are subject to change.
# ============================================================

SESSION_OPEN = time(
    17,
    0,
)

SESSION_CLOSE = time(
    16,
    0,
)

DAILY_HALT_START = time(
    15,
    15,
)

DAILY_HALT_END = time(
    15,
    30,
)


def _to_chicago(
    value,
):

    timestamp = pd.to_datetime(
        value,
        utc=True,
        errors="coerce",
    )

    if pd.isna(
        timestamp
    ):

        return None

    return timestamp.tz_convert(
        CHICAGO_TZ
    )


def is_weekend_closed(
    value,
):

    local = _to_chicago(
        value
    )

    if local is None:

        return False

    weekday = local.weekday()
    clock = local.time()

    # Saturday:
    # completely closed.

    if weekday == 5:

        return True

    # Friday:
    # closes at 16:00 CT and does not reopen that evening.

    if (
        weekday == 4
        and clock >= SESSION_CLOSE
    ):

        return True

    # Sunday:
    # closed until 17:00 CT.

    if (
        weekday == 6
        and clock < SESSION_OPEN
    ):

        return True

    return False


def is_daily_maintenance(
    value,
):

    local = _to_chicago(
        value
    )

    if local is None:

        return False

    clock = local.time()

    # Friday after 16:00 and the weekend are handled
    # separately by is_weekend_closed().

    if is_weekend_closed(
        value
    ):

        return False

    return (
        SESSION_CLOSE
        <= clock
        < SESSION_OPEN
    )


def is_daily_trading_halt(
    value,
):

    local = _to_chicago(
        value
    )

    if local is None:

        return False

    if is_weekend_closed(
        value
    ):

        return False

    clock = local.time()

    return (
        DAILY_HALT_START
        <= clock
        < DAILY_HALT_END
    )


def is_holiday_schedule_unknown(
    value,
):

    local = _to_chicago(
        value
    )

    if local is None:

        return False

    return bool(
        is_cme_holiday_window(
            local.date()
        )
    )


def classify_mnq_market_time(
    value,
):

    local = _to_chicago(
        value
    )

    if local is None:

        return {
            "state":
                "INVALID",

            "expected_open":
                False,

            "reason":
                "Invalid timestamp.",

            "chicago_time":
                None,
        }

    if is_holiday_schedule_unknown(
        value
    ):

        return {
            "state":
                "HOLIDAY UNKNOWN",

            "expected_open":
                None,

            "reason":
                (
                    "Timestamp falls inside a CME holiday "
                    "window. Exact holiday hours are not "
                    "assumed."
                ),

            "chicago_time":
                local,
        }

    if is_weekend_closed(
        value
    ):

        return {
            "state":
                "WEEKEND CLOSED",

            "expected_open":
                False,

            "reason":
                "Standard CME weekend closure.",

            "chicago_time":
                local,
        }

    if is_daily_maintenance(
        value
    ):

        return {
            "state":
                "MAINTENANCE",

            "expected_open":
                False,

            "reason":
                "Standard 16:00-17:00 CT maintenance.",

            "chicago_time":
                local,
        }

    if is_daily_trading_halt(
        value
    ):

        return {
            "state":
                "DAILY HALT",

            "expected_open":
                False,

            "reason":
                "Standard 15:15-15:30 CT trading halt.",

            "chicago_time":
                local,
        }

    return {
        "state":
            "OPEN",

        "expected_open":
            True,

        "reason":
            "Standard MNQ trading time.",

        "chicago_time":
            local,
    }


def expected_bar_start(
    value,
):

    classification = (
        classify_mnq_market_time(
            value
        )
    )

    return (
        classification[
            "expected_open"
        ]
        is True
    )


def expected_missing_bars_between(
    previous_time,
    next_time,
    bar_minutes=BAR_MINUTES,
):

    previous = pd.to_datetime(
        previous_time,
        utc=True,
        errors="coerce",
    )

    following = pd.to_datetime(
        next_time,
        utc=True,
        errors="coerce",
    )

    if (
        pd.isna(
            previous
        )
        or pd.isna(
            following
        )
        or following <= previous
    ):

        return []

    cursor = (
        previous
        + pd.Timedelta(
            minutes=bar_minutes
        )
    )

    missing = []

    while cursor < following:

        classification = (
            classify_mnq_market_time(
                cursor
            )
        )

        if (
            classification[
                "expected_open"
            ]
            is True
        ):

            missing.append(
                cursor
            )

        cursor = (
            cursor
            + pd.Timedelta(
                minutes=bar_minutes
            )
        )

    return missing


def gap_touches_unknown_holiday_schedule(
    previous_time,
    next_time,
    bar_minutes=BAR_MINUTES,
):

    previous = pd.to_datetime(
        previous_time,
        utc=True,
        errors="coerce",
    )

    following = pd.to_datetime(
        next_time,
        utc=True,
        errors="coerce",
    )

    if (
        pd.isna(
            previous
        )
        or pd.isna(
            following
        )
        or following <= previous
    ):

        return False

    cursor = (
        previous
        + pd.Timedelta(
            minutes=bar_minutes
        )
    )

    while cursor < following:

        classification = (
            classify_mnq_market_time(
                cursor
            )
        )

        if (
            classification[
                "state"
            ]
            == "HOLIDAY UNKNOWN"
        ):

            return True

        cursor = (
            cursor
            + pd.Timedelta(
                minutes=bar_minutes
            )
        )

    return False