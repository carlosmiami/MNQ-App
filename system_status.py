import json
from datetime import datetime, timezone, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from cme_calendar import (
    get_cme_holiday_window,
)

from mnq_market_schedule import (
    classify_mnq_market_time,
    expected_missing_bars_between,
    gap_touches_unknown_holiday_schedule,
)

from contract_history import (
    load_contract_history,
    get_contract_history_file,
)

from history_integrity import (
    analyze_history_integrity,
)

from rollover_calendar import (
    get_roll_status,
)


STATUS_FILE = Path(
    "state/forward_runner_status.json"
)

ET = ZoneInfo(
    "America/New_York"
)


# ============================================================
# LOAD RUNNER STATUS
# ============================================================

def load_runner_status():

    if not STATUS_FILE.exists():

        return {
            "status": "UNKNOWN",
            "collector": "UNKNOWN",
            "tracker": "UNKNOWN",
            "updated_at": None,
            "message":
                "Forward runner status file "
                "has not been created yet.",
        }

    try:

        data = json.loads(
            STATUS_FILE.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:

        return {
            "status": "ERROR",
            "collector": "UNKNOWN",
            "tracker": "UNKNOWN",
            "updated_at": None,
            "message":
                f"Could not read status file: {exc}",
        }

    updated_at = data.get(
        "updated_at"
    )

    if updated_at:

        updated_at = pd.Timestamp(
            updated_at
        )

        if updated_at.tzinfo is None:

            updated_at = (
                updated_at
                .tz_localize(
                    "UTC"
                )
            )

        else:

            updated_at = (
                updated_at
                .tz_convert(
                    "UTC"
                )
            )

    return {
        "status":
            data.get(
                "status",
                "UNKNOWN",
            ),

        "collector":
            data.get(
                "collector",
                "UNKNOWN",
            ),

        "tracker":
            data.get(
                "tracker",
                "UNKNOWN",
            ),

        "updated_at":
            updated_at,

        "message":
            data.get(
                "message",
                "",
            ),
    }


# ============================================================
# TIME HELPERS
# ============================================================

def now_utc():

    return pd.Timestamp(
        datetime.now(
            timezone.utc
        )
    )


def normalize_timestamp(
    value,
):

    if value is None:
        return None

    try:

        ts = pd.Timestamp(
            value
        )

    except Exception:

        return None

    if ts.tzinfo is None:

        ts = ts.tz_localize(
            "UTC"
        )

    else:

        ts = ts.tz_convert(
            "UTC"
        )

    return ts


def age_minutes(
    timestamp,
):

    timestamp = normalize_timestamp(
        timestamp
    )

    if timestamp is None:
        return None

    age = (
        now_utc()
        - timestamp
    ).total_seconds() / 60.0

    return max(
        0.0,
        age,
    )


# ============================================================
# CME MARKET STATE
#
# Single source of truth:
# mnq_market_schedule.py
#
# as_of_time exists for deterministic regression testing.
# Production callers omit it and current UTC time is used.
# ============================================================

def get_cme_market_state(
    as_of_time=None,
):

    if as_of_time is None:

        current_utc = (
            now_utc()
        )

    else:

        current_utc = (
            normalize_timestamp(
                as_of_time
            )
        )

    if current_utc is None:

        return {
            "state":
                "UNKNOWN",

            "label":
                "UNKNOWN",

            "holiday_name":
                None,

            "time_et":
                None,

            "schedule_reason":
                "Invalid market timestamp.",
        }

    classification = (
        classify_mnq_market_time(
            current_utc
        )
    )

    schedule_state = (
        classification.get(
            "state"
        )
    )

    reason = (
        classification.get(
            "reason",
            "",
        )
    )

    local_chicago = (
        classification.get(
            "chicago_time"
        )
    )

    time_et = (
        current_utc
        .tz_convert(
            ET
        )
        .to_pydatetime()
    )

    holiday_name = None

    if (
        schedule_state
        == "HOLIDAY UNKNOWN"
        and local_chicago is not None
    ):

        holiday = (
            get_cme_holiday_window(
                local_chicago.date()
            )
        )

        if holiday is not None:

            holiday_name = (
                holiday.get(
                    "name"
                )
            )

    if (
        schedule_state
        == "HOLIDAY UNKNOWN"
    ):

        return {
            "state":
                "SCHEDULE UNKNOWN",

            "label":
                "SCHEDULE UNKNOWN",

            "holiday_name":
                holiday_name,

            "time_et":
                time_et,

            "schedule_reason":
                reason,
        }

    if (
        schedule_state
        == "WEEKEND CLOSED"
    ):

        return {
            "state":
                "CLOSED",

            "label":
                "MARKET CLOSED",

            "holiday_name":
                None,

            "time_et":
                time_et,

            "schedule_reason":
                reason,
        }

    if (
        schedule_state
        == "MAINTENANCE"
    ):

        return {
            "state":
                "MAINTENANCE",

            "label":
                "MAINTENANCE",

            "holiday_name":
                None,

            "time_et":
                time_et,

            "schedule_reason":
                reason,
        }

    if (
        schedule_state
        == "DAILY HALT"
    ):

        return {
            "state":
                "DAILY HALT",

            "label":
                "DAILY HALT",

            "holiday_name":
                None,

            "time_et":
                time_et,

            "schedule_reason":
                reason,
        }

    if (
        schedule_state
        == "OPEN"
    ):

        return {
            "state":
                "OPEN",

            "label":
                "OPEN",

            "holiday_name":
                None,

            "time_et":
                time_et,

            "schedule_reason":
                reason,
        }

    return {
        "state":
            "UNKNOWN",

        "label":
            "UNKNOWN",

        "holiday_name":
            holiday_name,

        "time_et":
            time_et,

        "schedule_reason":
            reason
            or
            "MNQ market schedule could not be classified.",
    }


# ============================================================
# HEALTH
# ============================================================

def classify_runner_health(
    status,
    age,
):

    if status == "ERROR":

        return "ERROR"

    if status != "PASS":

        return "UNKNOWN"

    if age is None:

        return "UNKNOWN"

    if age <= 10:

        return "HEALTHY"

    if age <= 20:

        return "STALE"

    return "OFFLINE"


def classify_market_data(
    age,
    market_state,
):

    state = market_state[
        "state"
    ]

    # Holiday window with no finalized exact MNQ schedule.
    #
    # We deliberately do NOT call this fresh, stale, closed,
    # or holiday-closed. The schedule itself is unresolved.

    if (
        state
        == "SCHEDULE UNKNOWN"
    ):

        return (
            "SCHEDULE UNKNOWN"
        )

    if state == "CLOSED":

        return (
            "MARKET CLOSED"
        )

    if state == "MAINTENANCE":

        return (
            "MAINTENANCE"
        )

    if state == "DAILY HALT":

        return (
            "DAILY HALT"
        )

    if state == "UNKNOWN":

        return (
            "UNKNOWN"
        )

    if age is None:

        return (
            "UNKNOWN"
        )

    if age <= 10:

        return (
            "FRESH"
        )

    if age <= 30:

        return (
            "STALE"
        )

    return (
        "OLD"
    )


# ============================================================
# FORMAT
# ============================================================

def format_age(
    value,
):

    if value is None:

        return "-"

    if value < 1:

        return "<1 min"

    if value < 60:

        return (
            f"{value:.1f} min"
        )

    return (
        f"{value / 60.0:.1f} hr"
    )


def format_number(
    value,
    decimals=2,
):

    if value is None:

        return "-"

    try:

        return (
            f"{float(value):.{decimals}f}"
        )

    except Exception:

        return str(
            value
        )


def format_bar_time(
    value,
):

    ts = normalize_timestamp(
        value
    )

    if ts is None:

        return "-"

    return ts.strftime(
        "%Y-%m-%d %H:%M UTC"
    )


# ============================================================
# LOCAL CONTRACT HISTORY
# ============================================================

def load_local_history_status(
    contract_info,
):

    empty = {
        "bars": 0,
        "first_bar": None,
        "last_bar": None,
        "age_minutes": None,
        "file": None,
        "status": "NONE",
        "integrity_state": "NO DATA",
        "short_gaps": 0,
        "missing_bars": 0,
        "integrity_message":
            "No local history available.",
    }

    if not contract_info:

        return empty

    contract_id = (
        contract_info.get(
            "id"
        )
    )

    contract_name = (
        contract_info.get(
            "name"
        )
    )

    if (
        not contract_id
        or not contract_name
    ):

        return empty

    try:

        path = (
            get_contract_history_file(
                contract_name
            )
        )

        df = load_contract_history(
            contract_id=contract_id,
            contract_name=contract_name,
        )

    except Exception as exc:

        return {
            **empty,
            "status": "ERROR",
            "error": str(
                exc
            ),
        }

    if df.empty:

        return {
            **empty,
            "file": str(
                path
            ),
            "status": "EMPTY",
        }

    first_bar = (
        df.iloc[
            0
        ][
            "time"
        ]
    )

    last_bar = (
        df.iloc[
            -1
        ][
            "time"
        ]
    )

    local_age = age_minutes(
        last_bar
    )

    integrity = (
        analyze_history_integrity(
            df
        )
    )

    return {
        "bars":
            len(
                df
            ),

        "first_bar":
            first_bar,

        "last_bar":
            last_bar,

        "age_minutes":
            local_age,

        "file":
            str(
                path
            ),

        "status":
            "OK",

        "integrity_state":
            integrity[
                "state"
            ],

        "short_gaps":
            integrity[
                "short_gaps"
            ],

        "missing_bars":
            integrity[
                "missing_bars"
            ],

        "integrity_message":
            integrity[
                "message"
            ],
    }


# ============================================================
# LOCAL HISTORY SYNC
#
# Market-aware synchronization.
#
# Clock minutes alone are NOT enough because the interval may
# contain:
# - daily halt
# - daily maintenance
# - weekend closure
# - holiday schedule whose exact hours are unknown
#
# Policy preserves the old open-market tolerance:
#
# 0 expected missing bars -> SYNCED
# 1-2 expected bars       -> LAGGING
# 3+ expected bars        -> OUT OF SYNC
# holiday unknown         -> UNKNOWN
# ============================================================

def classify_local_history_sync(
    latest_market_bar,
    latest_local_bar,
):

    market_ts = normalize_timestamp(
        latest_market_bar
    )

    local_ts = normalize_timestamp(
        latest_local_bar
    )

    if (
        market_ts is None
        or local_ts is None
    ):

        return {
            "state":
                "UNKNOWN",

            "gap_minutes":
                None,

            "expected_missing_bars":
                None,

            "message":
                (
                    "Market/local history synchronization "
                    "cannot be determined."
                ),
        }

    gap_minutes = (
        market_ts
        - local_ts
    ).total_seconds() / 60.0

    # Local history equal to or ahead of the current
    # market dataframe is synchronized.

    if gap_minutes <= 0.0:

        return {
            "state":
                "SYNCED",

            "gap_minutes":
                0.0,

            "expected_missing_bars":
                0,

            "message":
                "Local contract history is synchronized.",
        }

    # Preserve existing 5-minute tolerance.
    #
    # If market has merely advanced to the immediately next
    # 5m bar, there is no INTERNAL expected missing candle.

    if gap_minutes <= 5.0:

        return {
            "state":
                "SYNCED",

            "gap_minutes":
                gap_minutes,

            "expected_missing_bars":
                0,

            "message":
                "Local contract history is synchronized.",
        }

    # If the interval intersects a holiday whose exact MNQ
    # schedule is not encoded, synchronization cannot safely
    # be inferred from clock time.

    if gap_touches_unknown_holiday_schedule(
        local_ts,
        market_ts,
    ):

        return {
            "state":
                "UNKNOWN",

            "gap_minutes":
                gap_minutes,

            "expected_missing_bars":
                None,

            "message":
                (
                    "Local history synchronization cannot "
                    "be verified because the interval "
                    "crosses a CME holiday window with "
                    "unknown exact MNQ trading hours."
                ),
        }

    expected_missing = (
        expected_missing_bars_between(
            local_ts,
            market_ts,
        )
    )

    missing_count = len(
        expected_missing
    )

    # No tradable 5m candles should have existed between the
    # two timestamps.
    #
    # Typical examples:
    # maintenance, daily halt, weekend closure.

    if missing_count == 0:

        return {
            "state":
                "SYNCED",

            "gap_minutes":
                gap_minutes,

            "expected_missing_bars":
                0,

            "message":
                (
                    "Local contract history is synchronized. "
                    "The clock-time difference contains no "
                    "expected MNQ 5-minute bars."
                ),
        }

    # Preserve old effective thresholds during continuous
    # open-market trading:
    #
    # 10 min -> 1 internal expected bar
    # 15 min -> 2 internal expected bars

    if missing_count <= 2:

        return {
            "state":
                "LAGGING",

            "gap_minutes":
                gap_minutes,

            "expected_missing_bars":
                missing_count,

            "message":
                (
                    "Local contract history is behind "
                    f"market data by {missing_count} "
                    "expected MNQ 5-minute bar(s) "
                    f"({gap_minutes:.1f} clock minutes)."
                ),
        }

    return {
        "state":
            "OUT OF SYNC",

        "gap_minutes":
            gap_minutes,

        "expected_missing_bars":
            missing_count,

        "message":
            (
                "Local contract history is out of sync by "
                f"{missing_count} expected MNQ 5-minute "
                f"bar(s) ({gap_minutes:.1f} clock minutes)."
            ),
    }


# ============================================================
# RENDER
# ============================================================

def render_system_status(
    latest_bar_time=None,
    contract_info=None,
):

    data = load_runner_status()

    runner_age = age_minutes(
        data[
            "updated_at"
        ]
    )

    runner_health = (
        classify_runner_health(
            data[
                "status"
            ],
            runner_age,
        )
    )

    market_state = (
        get_cme_market_state()
    )

    market_age = age_minutes(
        latest_bar_time
    )

    market_data_status = (
        classify_market_data(
            market_age,
            market_state,
        )
    )

    contract_name = "-"
    contract_id = "-"
    tick_size = "-"
    tick_value = "-"

    if contract_info:

        contract_name = (
            contract_info.get(
                "name"
            )
            or "-"
        )

        contract_id = (
            contract_info.get(
                "id"
            )
            or "-"
        )

        tick_size = format_number(
            contract_info.get(
                "tickSize"
            ),
            2,
        )

        tick_value = format_number(
            contract_info.get(
                "tickValue"
            ),
            2,
        )

    local_history = (
        load_local_history_status(
            contract_info
        )
    )

    local_sync = (
        classify_local_history_sync(
            latest_market_bar=
                latest_bar_time,

            latest_local_bar=
                local_history[
                    "last_bar"
                ],
        )
    )

    roll_status = (
        get_roll_status()
    )

    with st.expander(
        "System Status",
        expanded=False,
    ):

        # ====================================================
        # CORE SYSTEM STATUS
        # ====================================================

        c1, c2, c3, c4, c5, c6 = (
            st.columns(
                6
            )
        )

        c1.metric(
            "Forward Runner",
            runner_health,
        )

        c2.metric(
            "Collector",
            data[
                "collector"
            ],
        )

        c3.metric(
            "Tracker",
            data[
                "tracker"
            ],
        )

        c4.metric(
            "Runner Age",
            format_age(
                runner_age
            ),
        )

        c5.metric(
            "CME",
            market_state[
                "label"
            ],
        )

        c6.metric(
            "Market Data",
            market_data_status,
        )

        # ====================================================
        # CONTRACT
        # ====================================================

        st.markdown(
            "**Active MNQ Contract**"
        )

        k1, k2, k3 = (
            st.columns(
                [
                    1,
                    2.2,
                    1.2,
                ]
            )
        )

        k1.metric(
            "Contract",
            contract_name,
        )

        k2.metric(
            "Contract ID",
            contract_id,
        )

        k3.metric(
            "Tick",
            (
                f"{tick_size} / "
                f"${tick_value}"
            ),
        )

        # ====================================================
        # ROLLOVER
        # ====================================================

        st.markdown(
            "**MNQ Rollover**"
        )

        r1, r2, r3, r4 = (
            st.columns(
                [
                    1.2,
                    1.2,
                    1.2,
                    1.2,
                ]
            )
        )

        r1.metric(
            "Rollover Status",
            roll_status[
                "state"
            ],
        )

        r2.metric(
            "Next Roll",
            (
                roll_status[
                    "roll_date"
                ].isoformat()
                if roll_status[
                    "roll_date"
                ]
                is not None
                else "-"
            ),
        )

        r3.metric(
            "Days to Roll",
            (
                roll_status[
                    "days_to_roll"
                ]
                if roll_status[
                    "days_to_roll"
                ]
                is not None
                else "-"
            ),
        )

        r4.metric(
            "Expiration",
            (
                roll_status[
                    "expiration_date"
                ].isoformat()
                if roll_status[
                    "expiration_date"
                ]
                is not None
                else "-"
            ),
        )

        if (
            roll_status[
                "state"
            ]
            == "ROLL APPROACHING"
        ):

            st.warning(
                "MNQ rollover is approaching. "
                f"{roll_status['days_to_roll']} days "
                "remain until the CME roll date."
            )

        elif (
            roll_status[
                "state"
            ]
            == "ROLL CRITICAL"
        ):

            st.warning(
                "MNQ rollover is in the critical window. "
                f"Only {roll_status['days_to_roll']} days "
                "remain until the CME roll date."
            )

        elif (
            roll_status[
                "state"
            ]
            == "ROLL NOW"
        ):

            st.error(
                "MNQ is at or past the CME roll date. "
                "Verify that TopstepX has switched the "
                "active MNQ contract before relying on "
                "new C1-C5 setups."
            )

        # ====================================================
        # LOCAL HISTORY
        # ====================================================

        st.markdown(
            "**Local Contract History**"
        )

        h1, h2, h3, h4, h5, h6 = (
            st.columns(
                [
                    1,
                    1.6,
                    1.6,
                    1,
                    1.2,
                    1.2,
                ]
            )
        )

        h1.metric(
            "Local Bars",
            local_history[
                "bars"
            ],
        )

        h2.metric(
            "Local First",
            format_bar_time(
                local_history[
                    "first_bar"
                ]
            ),
        )

        h3.metric(
            "Local Last",
            format_bar_time(
                local_history[
                    "last_bar"
                ]
            ),
        )

        h4.metric(
            "Local Age",
            format_age(
                local_history[
                    "age_minutes"
                ]
            ),
        )

        h5.metric(
            "Local Sync",
            local_sync[
                "state"
            ],
        )

        h6.metric(
            "History Integrity",
            local_history[
                "integrity_state"
            ],
        )

        if local_history[
            "file"
        ]:

            st.caption(
                "Local file: "
                f"{local_history['file']}"
            )

        if (
            local_history[
                "status"
            ]
            == "ERROR"
        ):

            st.error(
                "Local history error: "
                f"{local_history.get('error')}"
            )

        elif (
            local_history[
                "status"
            ]
            == "EMPTY"
        ):

            st.warning(
                "Local contract history file "
                "has no bars yet."
            )

        if (
            local_history[
                "status"
            ]
            == "OK"
        ):

            if (
                local_sync[
                    "state"
                ]
                == "LAGGING"
            ):

                st.warning(
                    local_sync[
                        "message"
                    ]
                )

            elif (
                local_sync[
                    "state"
                ]
                == "OUT OF SYNC"
            ):

                st.error(
                    local_sync[
                        "message"
                    ]
                )

            if (
                local_history[
                    "integrity_state"
                ]
                == "GAPS FOUND"
            ):

                st.error(
                    "Local history integrity problem: "
                    f"{local_history['short_gaps']} "
                    "short gap(s), "
                    f"{local_history['missing_bars']} "
                    "missing 5m bar(s)."
                )

            elif (
                local_history[
                    "integrity_state"
                ]
                == "SCHEDULE UNKNOWN"
            ):

                st.warning(
                    "Local history integrity cannot be "
                    "fully verified because one or more "
                    "gaps intersect a CME holiday window "
                    "with unknown exact MNQ trading hours. "
                    + local_history[
                        "integrity_message"
                    ]
                )

            elif (
                local_history[
                    "integrity_state"
                ]
                == "CLEAN"
            ):

                st.caption(
                    "History integrity: "
                    + local_history[
                        "integrity_message"
                    ]
                )

        # ====================================================
        # TIMES
        # ====================================================

        st.caption(
            "CME time ET: "
            f"{market_state['time_et']}"
        )

        if (
            market_state[
                "state"
            ]
            == "SCHEDULE UNKNOWN"
        ):

            st.caption(
                "Holiday window: "
                f"{market_state['holiday_name']}"
            )

        if data[
            "updated_at"
        ] is not None:

            st.caption(
                "Runner updated UTC: "
                f"{data['updated_at']}"
            )

        if latest_bar_time is not None:

            normalized_market = (
                normalize_timestamp(
                    latest_bar_time
                )
            )

            st.caption(
                "Last market bar UTC: "
                f"{normalized_market}"
                " | Age: "
                f"{format_age(market_age)}"
            )

        # ====================================================
        # RUNNER
        # ====================================================

        if runner_health == "HEALTHY":

            st.success(
                data[
                    "message"
                ]
                or
                "Forward runner is healthy."
            )

        elif runner_health == "STALE":

            st.warning(
                "Forward runner has not reported "
                "in more than 10 minutes."
            )

        elif runner_health == "OFFLINE":

            st.error(
                "Forward runner has not reported "
                "in more than 20 minutes."
            )

        elif runner_health == "ERROR":

            st.error(
                data[
                    "message"
                ]
                or
                "Forward runner reported an error."
            )

        else:

            st.info(
                data[
                    "message"
                ]
                or
                "Forward runner status is unknown."
            )

        # ====================================================
        # MARKET
        # ====================================================

        if (
            market_state[
                "state"
            ]
            == "SCHEDULE UNKNOWN"
        ):

            st.warning(
                "CME holiday window detected: "
                f"{market_state['holiday_name'] or 'Unknown holiday'}. "
                "Exact MNQ holiday trading hours are not encoded. "
                "Market freshness cannot be used to infer whether "
                "MNQ should currently be open or closed. "
                "Operational analysis remains fail-safe blocked."
            )

        elif (
            market_state[
                "state"
            ]
            == "CLOSED"
        ):

            st.info(
                "CME equity-index futures "
                "market is currently closed."
            )

        elif (
            market_state[
                "state"
            ]
            == "MAINTENANCE"
        ):

            st.info(
                "CME daily maintenance window "
                "is currently active."
            )

        elif (
            market_state[
                "state"
            ]
            == "DAILY HALT"
        ):

            st.info(
                "CME daily equity-index futures "
                "trading halt is currently active."
            )

        elif (
            market_data_status
            == "STALE"
        ):

            st.warning(
                "CME should be open, but the "
                "last MNQ bar is more than "
                "10 minutes old."
            )

        elif (
            market_data_status
            == "OLD"
        ):

            st.error(
                "CME should be open, but the "
                "MNQ market data is more than "
                "30 minutes old."
            )