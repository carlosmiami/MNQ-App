from datetime import date, datetime, timezone


# ============================================================
# CME U.S. EQUITY INDEX ROLL DATES
# ============================================================

ROLL_DATES = [
    {
        "year": 2026,
        "quarter": "SEP",
        "roll_date": date(2026, 9, 14),
        "expiration_date": date(2026, 9, 18),
    },
    {
        "year": 2026,
        "quarter": "DEC",
        "roll_date": date(2026, 12, 14),
        "expiration_date": date(2026, 12, 18),
    },
    {
        "year": 2027,
        "quarter": "MAR",
        "roll_date": date(2027, 3, 15),
        "expiration_date": date(2027, 3, 19),
    },
    {
        "year": 2027,
        "quarter": "JUN",
        "roll_date": date(2027, 6, 14),
        "expiration_date": date(2027, 6, 18),
    },
    {
        "year": 2027,
        "quarter": "SEP",
        "roll_date": date(2027, 9, 13),
        "expiration_date": date(2027, 9, 17),
    },
    {
        "year": 2027,
        "quarter": "DEC",
        "roll_date": date(2027, 12, 13),
        "expiration_date": date(2027, 12, 17),
    },
]


# ============================================================
# NEXT ROLL
# ============================================================

def get_next_roll(
    current_date=None,
):

    if current_date is None:

        current_date = datetime.now(
            timezone.utc
        ).date()

    for item in ROLL_DATES:

        if item["expiration_date"] >= current_date:

            return item

    return None


# ============================================================
# ROLL STATUS
# ============================================================

def get_roll_status(
    current_date=None,
    warning_days=14,
    critical_days=5,
):

    if current_date is None:

        current_date = datetime.now(
            timezone.utc
        ).date()

    item = get_next_roll(
        current_date
    )

    if item is None:

        return {
            "state": "UNKNOWN",
            "year": None,
            "days_to_roll": None,
            "days_to_expiration": None,
            "roll_date": None,
            "expiration_date": None,
            "quarter": None,
        }

    roll_date = item[
        "roll_date"
    ]

    expiration_date = item[
        "expiration_date"
    ]

    days_to_roll = (
        roll_date
        - current_date
    ).days

    days_to_expiration = (
        expiration_date
        - current_date
    ).days

    if current_date > expiration_date:

        state = "EXPIRED"

    elif current_date >= roll_date:

        state = "ROLL NOW"

    elif days_to_roll <= critical_days:

        state = "ROLL CRITICAL"

    elif days_to_roll <= warning_days:

        state = "ROLL APPROACHING"

    else:

        state = "NORMAL"

    return {
        "state":
            state,

        "year":
            item[
                "year"
            ],

        "quarter":
            item[
                "quarter"
            ],

        "roll_date":
            roll_date,

        "expiration_date":
            expiration_date,

        "days_to_roll":
            days_to_roll,

        "days_to_expiration":
            days_to_expiration,
    }