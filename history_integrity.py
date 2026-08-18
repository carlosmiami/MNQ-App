import pandas as pd

from mnq_market_schedule import (
    expected_missing_bars_between,
    gap_touches_unknown_holiday_schedule,
)


EXPECTED_BAR_MINUTES = 5

# ============================================================
# COMPATIBILITY
#
# Older MNQ-App modules/tests import this name and the function
# find_short_5m_gaps().
#
# The detector is no longer limited to <=30 minute gaps.
# The constant remains only for compatibility.
# ============================================================

MAX_SHORT_GAP_MINUTES = 30


# ============================================================
# NORMALIZE
# ============================================================

def normalize_times(
    df,
):

    if (
        df is None
        or df.empty
        or "time" not in df.columns
    ):

        return pd.Series(
            dtype="datetime64[ns, UTC]"
        )

    times = pd.to_datetime(
        df["time"],
        utc=True,
        errors="coerce",
    )

    return (
        times
        .dropna()
        .drop_duplicates()
        .sort_values()
        .reset_index(
            drop=True
        )
    )


# ============================================================
# BUILD ONE GAP RECORD
# ============================================================

def _build_gap_record(
    previous,
    current,
    expected_missing,
):

    difference_minutes = (
        current
        - previous
    ).total_seconds() / 60.0

    return {
        "previous_bar":
            previous,

        "next_bar":
            current,

        "gap_minutes":
            difference_minutes,

        "missing_bars":
            len(
                expected_missing
            ),

        "first_missing":
            (
                expected_missing[
                    0
                ]
                if expected_missing
                else None
            ),

        "last_missing":
            (
                expected_missing[
                    -1
                ]
                if expected_missing
                else None
            ),

        "expected_missing_times":
            list(
                expected_missing
            ),

        "market_aware":
            True,
    }


# ============================================================
# BUILD UNKNOWN HOLIDAY GAP RECORD
# ============================================================

def _build_unknown_gap_record(
    previous,
    current,
):

    difference_minutes = (
        current
        - previous
    ).total_seconds() / 60.0

    return {
        "previous_bar":
            previous,

        "next_bar":
            current,

        "gap_minutes":
            difference_minutes,

        "reason":
            (
                "Gap intersects a CME holiday window "
                "whose exact MNQ trading hours are not "
                "encoded."
            ),
    }


# ============================================================
# FIND MARKET-AWARE INTERNAL GAPS
#
# IMPORTANT:
#
# A time discontinuity is NOT automatically considered data
# loss.
#
# We ask the MNQ schedule whether each missing 5-minute slot
# should actually have contained a tradable bar.
#
# Therefore:
#
# - Daily maintenance is ignored.
# - Daily halt is ignored.
# - Weekend closure is ignored.
# - Missing bars during standard OPEN market are flagged.
# - Unknown holiday schedule is tracked separately.
# ============================================================

def find_market_aware_5m_gaps(
    df,
):

    times = normalize_times(
        df
    )

    if len(
        times
    ) < 2:

        return []

    gaps = []

    previous = times.iloc[
        0
    ]

    for current in times.iloc[
        1:
    ]:

        difference_minutes = (
            current
            - previous
        ).total_seconds() / 60.0

        if (
            difference_minutes
            <= EXPECTED_BAR_MINUTES
        ):

            previous = current

            continue

        if gap_touches_unknown_holiday_schedule(
            previous,
            current,
            bar_minutes=
                EXPECTED_BAR_MINUTES,
        ):

            previous = current

            continue

        expected_missing = (
            expected_missing_bars_between(
                previous,
                current,
                bar_minutes=
                    EXPECTED_BAR_MINUTES,
            )
        )

        if not expected_missing:

            previous = current

            continue

        gaps.append(
            _build_gap_record(
                previous,
                current,
                expected_missing,
            )
        )

        previous = current

    return gaps


# ============================================================
# FIND UNKNOWN HOLIDAY-SCHEDULE GAPS
# ============================================================

def find_unknown_schedule_gaps(
    df,
):

    times = normalize_times(
        df
    )

    if len(
        times
    ) < 2:

        return []

    unknown = []

    previous = times.iloc[
        0
    ]

    for current in times.iloc[
        1:
    ]:

        difference_minutes = (
            current
            - previous
        ).total_seconds() / 60.0

        if (
            difference_minutes
            <= EXPECTED_BAR_MINUTES
        ):

            previous = current

            continue

        if gap_touches_unknown_holiday_schedule(
            previous,
            current,
            bar_minutes=
                EXPECTED_BAR_MINUTES,
        ):

            unknown.append(
                _build_unknown_gap_record(
                    previous,
                    current,
                )
            )

        previous = current

    return unknown


# ============================================================
# LEGACY FUNCTION NAME
# ============================================================

def find_short_5m_gaps(
    df,
    max_gap_minutes=MAX_SHORT_GAP_MINUTES,
):

    _ = max_gap_minutes

    return find_market_aware_5m_gaps(
        df
    )


# ============================================================
# SUMMARY
# ============================================================

def analyze_history_integrity(
    df,
):

    times = normalize_times(
        df
    )

    gaps = (
        find_market_aware_5m_gaps(
            df
        )
    )

    unknown_schedule_gaps = (
        find_unknown_schedule_gaps(
            df
        )
    )

    missing_bars = sum(
        gap[
            "missing_bars"
        ]
        for gap in gaps
    )

    if len(
        times
    ) == 0:

        return {
            "state":
                "NO DATA",

            "bars":
                0,

            "short_gaps":
                0,

            "market_gaps":
                0,

            "unknown_schedule_gaps":
                0,

            "missing_bars":
                0,

            "first_gap":
                None,

            "last_gap":
                None,

            "first_unknown_gap":
                None,

            "last_unknown_gap":
                None,

            "message":
                "No local history available.",
        }

    # ========================================================
    # KNOWN MARKET GAPS TAKE PRIORITY
    #
    # If we positively know bars are missing during OPEN
    # market, that is a definite integrity failure.
    # ========================================================

    if gaps:

        return {
            "state":
                "GAPS FOUND",

            "bars":
                len(
                    times
                ),

            "short_gaps":
                len(
                    gaps
                ),

            "market_gaps":
                len(
                    gaps
                ),

            "unknown_schedule_gaps":
                len(
                    unknown_schedule_gaps
                ),

            "missing_bars":
                missing_bars,

            "first_gap":
                gaps[
                    0
                ],

            "last_gap":
                gaps[
                    -1
                ],

            "first_unknown_gap":
                (
                    unknown_schedule_gaps[
                        0
                    ]
                    if unknown_schedule_gaps
                    else None
                ),

            "last_unknown_gap":
                (
                    unknown_schedule_gaps[
                        -1
                    ]
                    if unknown_schedule_gaps
                    else None
                ),

            "message":
                (
                    f"{len(gaps)} market-time gap(s) "
                    f"detected containing "
                    f"{missing_bars} expected MNQ "
                    f"5-minute bar(s)."
                ),
        }

    # ========================================================
    # HOLIDAY SCHEDULE UNKNOWN
    #
    # No definite open-market gap was found, but at least one
    # discontinuity intersects a holiday window whose exact
    # product schedule is unknown.
    #
    # We MUST NOT call the history CLEAN.
    # ========================================================

    if unknown_schedule_gaps:

        return {
            "state":
                "SCHEDULE UNKNOWN",

            "bars":
                len(
                    times
                ),

            "short_gaps":
                0,

            "market_gaps":
                0,

            "unknown_schedule_gaps":
                len(
                    unknown_schedule_gaps
                ),

            "missing_bars":
                0,

            "first_gap":
                None,

            "last_gap":
                None,

            "first_unknown_gap":
                unknown_schedule_gaps[
                    0
                ],

            "last_unknown_gap":
                unknown_schedule_gaps[
                    -1
                ],

            "message":
                (
                    f"{len(unknown_schedule_gaps)} gap(s) "
                    "intersect CME holiday windows with "
                    "unknown exact MNQ trading hours. "
                    "History cannot be declared CLEAN."
                ),
        }

    # ========================================================
    # CLEAN
    # ========================================================

    return {
        "state":
            "CLEAN",

        "bars":
            len(
                times
            ),

        "short_gaps":
            0,

        "market_gaps":
            0,

        "unknown_schedule_gaps":
            0,

        "missing_bars":
            0,

        "first_gap":
            None,

        "last_gap":
            None,

        "first_unknown_gap":
            None,

        "last_unknown_gap":
            None,

        "message":
            (
                "No missing 5m bars were detected "
                "during expected MNQ trading time."
            ),
    }