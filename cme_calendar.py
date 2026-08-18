from datetime import date


# ============================================================
# CME 2026 OFFICIAL HOLIDAY WINDOWS
#
# Source:
# CME Group 2026 CME Globex Trading Schedule.
#
# IMPORTANT:
# These are holiday WINDOWS published by CME.
# Exact product trading hours may be finalized or changed
# closer to each holiday.
# ============================================================

CME_HOLIDAY_WINDOWS_2026 = [
    {
        "name": "New Year's",
        "start": date(2025, 12, 31),
        "end": date(2026, 1, 2),
    },
    {
        "name": "Martin Luther King Jr. Day",
        "start": date(2026, 1, 18),
        "end": date(2026, 1, 20),
    },
    {
        "name": "Presidents Day",
        "start": date(2026, 2, 15),
        "end": date(2026, 2, 17),
    },
    {
        "name": "Good Friday",
        "start": date(2026, 4, 2),
        "end": date(2026, 4, 4),
    },
    {
        "name": "Memorial Day",
        "start": date(2026, 5, 24),
        "end": date(2026, 5, 26),
    },
    {
        "name": "Juneteenth",
        "start": date(2026, 6, 18),
        "end": date(2026, 6, 19),
    },
    {
        "name": "Independence Day",
        "start": date(2026, 7, 3),
        "end": date(2026, 7, 5),
    },
    {
        "name": "Labor Day",
        "start": date(2026, 9, 6),
        "end": date(2026, 9, 8),
    },
    {
        "name": "Thanksgiving",
        "start": date(2026, 11, 26),
        "end": date(2026, 11, 28),
    },
    {
        "name": "Christmas",
        "start": date(2026, 12, 24),
        "end": date(2026, 12, 26),
    },
    {
        "name": "New Year's",
        "start": date(2026, 12, 31),
        "end": date(2027, 1, 1),
    },
]


def get_cme_holiday_window(
    current_date,
):

    for item in CME_HOLIDAY_WINDOWS_2026:

        if (
            item["start"]
            <= current_date
            <= item["end"]
        ):

            return item

    return None


def is_cme_holiday_window(
    current_date,
):

    return (
        get_cme_holiday_window(
            current_date
        )
        is not None
    )