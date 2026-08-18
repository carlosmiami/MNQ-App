import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from market_data import (
    get_bars_between,
)

from contract_history import (
    load_contract_history,
    persist_contract_history,
)

from history_integrity import (
    analyze_history_integrity,
    find_short_5m_gaps,
)


STATE_DIR = Path(
    "state"
)

STATE_DIR.mkdir(
    exist_ok=True
)

REPAIR_STATE_FILE = (
    STATE_DIR
    / "history_repair_status.json"
)

DEFAULT_COOLDOWN_MINUTES = 15

EXPECTED_BAR_MINUTES = 5

# Keep each repair request comfortably below the
# TopstepX get_bars_between() maximum.
REPAIR_REQUEST_MAX_BARS = 1000


# ============================================================
# API BARS -> DATAFRAME
# ============================================================

def bars_to_dataframe(
    bars,
):

    if not bars:

        return pd.DataFrame(
            columns=[
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

    df = (
        pd.DataFrame(
            bars
        )
        .rename(
            columns={
                "t": "time",
                "o": "open",
                "h": "high",
                "l": "low",
                "c": "close",
                "v": "volume",
            }
        )
    )

    df["time"] = pd.to_datetime(
        df["time"],
        utc=True,
        errors="coerce",
    )

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    return (
        df
        .dropna(
            subset=[
                "time",
                "open",
                "high",
                "low",
                "close",
            ]
        )
        .drop_duplicates(
            subset=[
                "time"
            ],
            keep="last",
        )
        .sort_values(
            "time"
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# REPAIR STATE
# ============================================================

def load_repair_state():

    if not REPAIR_STATE_FILE.exists():

        return {}

    try:

        return json.loads(
            REPAIR_STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return {}


def save_repair_state(
    state,
):

    temp = REPAIR_STATE_FILE.with_suffix(
        ".tmp"
    )

    temp.write_text(
        json.dumps(
            state,
            indent=2,
        ),
        encoding="utf-8",
    )

    temp.replace(
        REPAIR_STATE_FILE
    )


def utc_now():

    return pd.Timestamp(
        datetime.now(
            timezone.utc
        )
    )


def get_contract_repair_state(
    contract_id,
):

    state = load_repair_state()

    return state.get(
        str(
            contract_id
        ),
        {},
    )


def update_contract_repair_state(
    contract_id,
    **values,
):

    state = load_repair_state()

    key = str(
        contract_id
    )

    current = state.get(
        key,
        {},
    )

    current.update(
        values
    )

    state[
        key
    ] = current

    save_repair_state(
        state
    )


# ============================================================
# COOLDOWN
# ============================================================

def repair_cooldown_active(
    contract_id,
    cooldown_minutes=
        DEFAULT_COOLDOWN_MINUTES,
):

    status = (
        get_contract_repair_state(
            contract_id
        )
    )

    last_failed = status.get(
        "last_failed_at"
    )

    if not last_failed:

        return False

    try:

        last_failed = pd.Timestamp(
            last_failed
        )

        if last_failed.tzinfo is None:

            last_failed = (
                last_failed
                .tz_localize(
                    "UTC"
                )
            )

        else:

            last_failed = (
                last_failed
                .tz_convert(
                    "UTC"
                )
            )

    except Exception:

        return False

    elapsed = (
        utc_now()
        - last_failed
    ).total_seconds() / 60.0

    return (
        elapsed
        < cooldown_minutes
    )


# ============================================================
# NORMALIZE EXPECTED MISSING TIMES
# ============================================================

def get_expected_missing_times(
    gap,
):

    values = gap.get(
        "expected_missing_times"
    )

    if values:

        times = pd.to_datetime(
            list(
                values
            ),
            utc=True,
            errors="coerce",
        )

        return sorted(
            {
                pd.Timestamp(
                    value
                )
                for value in times
                if not pd.isna(
                    value
                )
            }
        )

    first_missing = gap.get(
        "first_missing"
    )

    last_missing = gap.get(
        "last_missing"
    )

    if (
        first_missing is None
        or last_missing is None
    ):

        return []

    first_missing = pd.Timestamp(
        first_missing
    )

    last_missing = pd.Timestamp(
        last_missing
    )

    if first_missing.tzinfo is None:

        first_missing = (
            first_missing
            .tz_localize(
                "UTC"
            )
        )

    else:

        first_missing = (
            first_missing
            .tz_convert(
                "UTC"
            )
        )

    if last_missing.tzinfo is None:

        last_missing = (
            last_missing
            .tz_localize(
                "UTC"
            )
        )

    else:

        last_missing = (
            last_missing
            .tz_convert(
                "UTC"
            )
        )

    if (
        last_missing
        < first_missing
    ):

        return []

    return list(
        pd.date_range(
            start=first_missing,
            end=last_missing,
            freq=(
                f"{EXPECTED_BAR_MINUTES}min"
            ),
            tz="UTC",
        )
    )


# ============================================================
# SPLIT EXPECTED TIMES INTO CONTIGUOUS OPEN-MARKET RANGES
#
# Example:
#
# 15:55 CT
# maintenance
# 17:00 CT
# 17:05 CT
#
# becomes TWO independent repair ranges instead of requesting
# one giant range through the maintenance closure.
# ============================================================

def split_contiguous_missing_ranges(
    expected_times,
):

    if not expected_times:

        return []

    normalized = sorted(
        {
            pd.Timestamp(
                value
            )
            for value in expected_times
        }
    )

    ranges = []

    current = [
        normalized[
            0
        ]
    ]

    step = pd.Timedelta(
        minutes=
            EXPECTED_BAR_MINUTES
    )

    for timestamp in normalized[
        1:
    ]:

        if (
            timestamp
            - current[
                -1
            ]
            == step
        ):

            current.append(
                timestamp
            )

        else:

            ranges.append(
                current
            )

            current = [
                timestamp
            ]

    ranges.append(
        current
    )

    return ranges


# ============================================================
# SPLIT LARGE CONTIGUOUS RANGE INTO SAFE API CHUNKS
# ============================================================

def split_repair_chunks(
    timestamps,
    max_bars=
        REPAIR_REQUEST_MAX_BARS,
):

    if not timestamps:

        return []

    max_bars = max(
        1,
        int(
            max_bars
        ),
    )

    return [
        timestamps[
            index:
            index + max_bars
        ]
        for index in range(
            0,
            len(
                timestamps
            ),
            max_bars,
        )
    ]


# ============================================================
# FETCH ONE GAP
#
# Only bars whose timestamps are explicitly expected are
# accepted.
#
# No synthetic bars are generated.
# ============================================================

def fetch_gap_bars(
    token,
    contract_id,
    gap,
):

    expected_times = (
        get_expected_missing_times(
            gap
        )
    )

    if not expected_times:

        return bars_to_dataframe(
            []
        )

    expected_set = set(
        expected_times
    )

    contiguous_ranges = (
        split_contiguous_missing_ranges(
            expected_times
        )
    )

    recovered_frames = []

    step = pd.Timedelta(
        minutes=
            EXPECTED_BAR_MINUTES
    )

    for contiguous in contiguous_ranges:

        chunks = split_repair_chunks(
            contiguous
        )

        for chunk in chunks:

            if not chunk:

                continue

            first_expected = (
                chunk[
                    0
                ]
            )

            last_expected = (
                chunk[
                    -1
                ]
            )

            # Expand by one 5m bar on each side.
            #
            # We later filter strictly to expected_set,
            # therefore adjacent already-existing bars cannot
            # contaminate the repair.

            request_start = (
                first_expected
                - step
            )

            request_end = (
                last_expected
                + step
            )

            bars = get_bars_between(
                token=token,
                contract_id=contract_id,
                start_time=request_start,
                end_time=request_end,
                unit=2,
                unit_number=5,
                limit=(
                    len(
                        chunk
                    )
                    + 10
                ),
            )

            df = bars_to_dataframe(
                bars
            )

            if df.empty:

                continue

            exact = (
                df[
                    df[
                        "time"
                    ].isin(
                        expected_set
                    )
                ]
                .copy()
            )

            if exact.empty:

                continue

            recovered_frames.append(
                exact
            )

    if not recovered_frames:

        return bars_to_dataframe(
            []
        )

    return (
        pd.concat(
            recovered_frames,
            ignore_index=True,
        )
        .drop_duplicates(
            subset=[
                "time"
            ],
            keep="last",
        )
        .sort_values(
            "time"
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# REPAIR CONTRACT HISTORY
# ============================================================

def repair_contract_history(
    token,
    contract,
    respect_cooldown=False,
    cooldown_minutes=
        DEFAULT_COOLDOWN_MINUTES,
):

    if not contract:

        raise RuntimeError(
            "No contract information provided."
        )

    contract_id = contract.get(
        "id"
    )

    contract_name = contract.get(
        "name"
    )

    if not contract_id:

        raise RuntimeError(
            "Contract has no contract ID."
        )

    if not contract_name:

        raise RuntimeError(
            "Contract has no contract name."
        )

    history = load_contract_history(
        contract_id=contract_id,
        contract_name=contract_name,
    )

    before = analyze_history_integrity(
        history
    )

    result = {
        "contract_id":
            contract_id,

        "contract_name":
            contract_name,

        "before_state":
            before[
                "state"
            ],

        "before_gaps":
            before[
                "short_gaps"
            ],

        "before_missing_bars":
            before[
                "missing_bars"
            ],

        "requested_gaps":
            0,

        "api_bars_recovered":
            0,

        "after_state":
            before[
                "state"
            ],

        "after_gaps":
            before[
                "short_gaps"
            ],

        "after_missing_bars":
            before[
                "missing_bars"
            ],

        "repaired":
            False,

        "cooldown":
            False,

        "message":
            "",
    }

    # ========================================================
    # CLEAN HISTORY
    # ========================================================

    if before[
        "state"
    ] != "GAPS FOUND":

        result[
            "message"
        ] = (
            "No missing market-time 5m bars "
            "require repair."
        )

        return result

    # ========================================================
    # FAILED / PARTIAL REPAIR COOLDOWN
    # ========================================================

    if (
        respect_cooldown
        and repair_cooldown_active(
            contract_id,
            cooldown_minutes,
        )
    ):

        result[
            "cooldown"
        ] = True

        result[
            "message"
        ] = (
            "History repair cooldown is active. "
            "No API repair request was sent."
        )

        return result

    # ========================================================
    # REQUEST MISSING RANGES
    # ========================================================

    gaps = find_short_5m_gaps(
        history
    )

    recovered_frames = []

    for gap in gaps:

        result[
            "requested_gaps"
        ] += 1

        recovered = fetch_gap_bars(
            token=token,
            contract_id=contract_id,
            gap=gap,
        )

        if recovered.empty:

            continue

        recovered_frames.append(
            recovered
        )

        result[
            "api_bars_recovered"
        ] += len(
            recovered
        )

    # ========================================================
    # NOTHING RECOVERED
    # ========================================================

    if not recovered_frames:

        now_text = (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )

        update_contract_repair_state(
            contract_id,
            last_failed_at=
                now_text,
            last_result=
                "NOT_FOUND",
            unresolved_missing_bars=
                before[
                    "missing_bars"
                ],
        )

        result[
            "message"
        ] = (
            "TopstepX did not return any of the "
            "expected missing 5m bars. "
            "History was NOT modified."
        )

        return result

    # ========================================================
    # PERSIST REAL API BARS ONLY
    # ========================================================

    recovered_all = (
        pd.concat(
            recovered_frames,
            ignore_index=True,
        )
        .drop_duplicates(
            subset=[
                "time"
            ],
            keep="last",
        )
        .sort_values(
            "time"
        )
        .reset_index(
            drop=True
        )
    )

    persist_contract_history(
        contract=contract,
        fresh_df=recovered_all,
    )

    # ========================================================
    # VERIFY AFTER PERSIST
    # ========================================================

    repaired_history = (
        load_contract_history(
            contract_id=contract_id,
            contract_name=contract_name,
        )
    )

    after = analyze_history_integrity(
        repaired_history
    )

    result[
        "after_state"
    ] = after[
        "state"
    ]

    result[
        "after_gaps"
    ] = after[
        "short_gaps"
    ]

    result[
        "after_missing_bars"
    ] = after[
        "missing_bars"
    ]

    result[
        "repaired"
    ] = (
        before[
            "missing_bars"
        ]
        > after[
            "missing_bars"
        ]
    )

    now_text = (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )

    # ========================================================
    # FULL SUCCESS
    # ========================================================

    if after[
        "state"
    ] == "CLEAN":

        update_contract_repair_state(
            contract_id,
            last_success_at=
                now_text,
            last_result=
                "CLEAN",
            last_failed_at=
                None,
            unresolved_missing_bars=
                0,
        )

        result[
            "message"
        ] = (
            "History repair completed. "
            "Integrity is now CLEAN."
        )

    # ========================================================
    # PARTIAL SUCCESS
    #
    # Some bars came back but unresolved expected bars remain.
    #
    # Treat this as cooldown-worthy so Streamlit refreshes do
    # not repeatedly hammer the API.
    # ========================================================

    elif result[
        "repaired"
    ]:

        update_contract_repair_state(
            contract_id,
            last_success_at=
                now_text,
            last_failed_at=
                now_text,
            last_result=
                "PARTIAL",
            unresolved_missing_bars=
                after[
                    "missing_bars"
                ],
        )

        result[
            "message"
        ] = (
            "Some missing bars were recovered, "
            "but unresolved gaps remain. "
            "Repair cooldown is now active."
        )

    # ========================================================
    # NO IMPROVEMENT
    # ========================================================

    else:

        update_contract_repair_state(
            contract_id,
            last_failed_at=
                now_text,
            last_result=
                "NO_IMPROVEMENT",
            unresolved_missing_bars=
                after[
                    "missing_bars"
                ],
        )

        result[
            "message"
        ] = (
            "API bars were returned, but history "
            "integrity did not improve."
        )

    return result