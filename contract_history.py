from pathlib import Path
import os
import re
import tempfile

import pandas as pd

from state_lock import FileLock

from ohlcv_integrity import (
    validate_ohlcv_frame,
)


DATA_DIR = Path(
    "data/contracts"
)

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


REQUIRED_COLUMNS = [
    "time",
    "open",
    "high",
    "low",
    "close",
    "volume",
]


# ============================================================
# HELPERS
# ============================================================

def safe_name(
    value,
):

    value = str(
        value
        or ""
    ).strip()

    value = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        value,
    )

    return (
        value
        or "UNKNOWN"
    )


def get_contract_history_file(
    contract_name,
):

    return (
        DATA_DIR
        / f"{safe_name(contract_name)}_5m.csv"
    )


def get_contract_history_lock_file(
    contract_name,
):
    """
    One transaction lock per contract history.

    The lock protects the complete:
        read -> merge -> validate -> atomic write

    sequence so concurrent Streamlit/process writers cannot
    overwrite each other's newly received bars.
    """

    return (
        DATA_DIR
        / f"{safe_name(contract_name)}_5m.lock"
    )


def normalize_history_frame(
    df,
):

    if df is None:

        return pd.DataFrame(
            columns=REQUIRED_COLUMNS
        )

    data = df.copy()

    for column in REQUIRED_COLUMNS:

        if column not in data.columns:

            data[column] = None

    data["time"] = pd.to_datetime(
        data["time"],
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

        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    data = (
        data
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

    return data[
        REQUIRED_COLUMNS
    ]


# ============================================================
# LOAD
# ============================================================

def load_contract_history(
    contract_id,
    contract_name,
):

    path = (
        get_contract_history_file(
            contract_name
        )
    )

    if not path.exists():

        return pd.DataFrame(
            columns=REQUIRED_COLUMNS
        )

    stored = pd.read_csv(
        path
    )

    # --------------------------------------------------------
    # Integrity check.
    # A file belonging to another contract must never
    # be silently reused.
    # --------------------------------------------------------

    if (
        "contract_id"
        in stored.columns
    ):

        ids = (
            stored[
                "contract_id"
            ]
            .dropna()
            .astype(str)
            .str.strip()
        )

        ids = ids[
            ids != ""
        ]

        unique_ids = set(
            ids.unique()
        )

        if (
            unique_ids
            and unique_ids
            != {
                str(
                    contract_id
                )
            }
        ):

            raise RuntimeError(
                "CONTRACT HISTORY INTEGRITY ERROR: "
                f"{path} contains contract IDs "
                f"{sorted(unique_ids)}, but caller requested "
                f"{contract_id}."
            )

    normalized = normalize_history_frame(
        stored
    )

    # ========================================================
    # STORED OHLCV INTEGRITY FAIL-SAFE
    #
    # Legacy/existing CSV files may predate the persistence
    # gate. Never allow malformed stored bars to enter the
    # application, indicators, levels, or C1-C5.
    #
    # Fail explicitly. Do not silently drop or repair bars.
    # ========================================================

    stored_integrity = validate_ohlcv_frame(
        normalized
    )


    if (
        stored_integrity[
            "status"
        ]
        != "OK"
    ):

        raise RuntimeError(
            "OHLCV STORED HISTORY BLOCKED: "
            f"{path} contains invalid market data. "
            f"reason={stored_integrity.get('reason')}; "
            f"invalid_bars={stored_integrity.get('invalid_count')}; "
            f"indices={stored_integrity.get('invalid_indices')}."
        )


    return normalized


# ============================================================
# ATOMIC SAVE
# ============================================================

def save_contract_history(
    contract_id,
    contract_name,
    df,
):

    data = normalize_history_frame(
        df
    )

    path = (
        get_contract_history_file(
            contract_name
        )
    )

    output = data.copy()

    output[
        "contract_id"
    ] = str(
        contract_id
    )

    output[
        "contract_name"
    ] = str(
        contract_name
    )

    # Write temporary file in the same directory and replace.
    # This prevents leaving a half-written CSV if interrupted.

    fd, temp_name = tempfile.mkstemp(
        prefix=(
            path.stem
            + "_"
        ),
        suffix=".tmp",
        dir=str(
            DATA_DIR
        ),
    )

    os.close(
        fd
    )

    temp_path = Path(
        temp_name
    )

    try:

        output.to_csv(
            temp_path,
            index=False,
        )

        os.replace(
            temp_path,
            path,
        )

    finally:

        if temp_path.exists():

            temp_path.unlink(
                missing_ok=True
            )

    return path


# ============================================================
# MERGE API + LOCAL
# ============================================================

def persist_contract_history(
    contract,
    fresh_df,
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

    fresh = normalize_history_frame(
        fresh_df
    )

    # ========================================================
    # OHLCV PERSISTENCE FAIL-SAFE
    #
    # No malformed fresh bar may enter local contract history.
    # Corrupt data is rejected before loading, merging,
    # or writing any persistent file.
    # ========================================================

    fresh_integrity = validate_ohlcv_frame(
        fresh
    )


    if (
        fresh_integrity[
            "status"
        ]
        != "OK"
    ):

        raise RuntimeError(
            "OHLCV PERSISTENCE BLOCKED: "
            "invalid fresh market data. "
            f"reason={fresh_integrity.get('reason')}; "
            f"invalid_bars={fresh_integrity.get('invalid_count')}; "
            f"indices={fresh_integrity.get('invalid_indices')}."
        )


    history_lock_file = (
        get_contract_history_lock_file(
            contract_name
        )
    )

    # ========================================================
    # TRANSACTION LOCK
    #
    # Protect the ENTIRE read -> merge -> validate -> write
    # sequence. Atomic os.replace() protects the file itself,
    # but without this transaction lock two concurrent writers
    # could both read the same old history and one could later
    # overwrite bars added by the other.
    # ========================================================

    with FileLock(
        history_lock_file
    ):

        existing = load_contract_history(
            contract_id=contract_id,
            contract_name=contract_name,
        )

        merged = pd.concat(
            [
                existing,
                fresh,
            ],
            ignore_index=True,
        )

        merged = normalize_history_frame(
            merged
        )

        merged_integrity = validate_ohlcv_frame(
            merged
        )

        if (
            merged_integrity[
                "status"
            ]
            != "OK"
        ):

            raise RuntimeError(
                "OHLCV PERSISTENCE BLOCKED: "
                "merged contract history is invalid. "
                f"reason={merged_integrity.get('reason')}; "
                f"invalid_bars={merged_integrity.get('invalid_count')}; "
                f"indices={merged_integrity.get('invalid_indices')}."
            )

        path = save_contract_history(
            contract_id=contract_id,
            contract_name=contract_name,
            df=merged,
        )

    return (
        merged,
        path,
    )


# ============================================================
# STATUS
# ============================================================

def get_contract_history_info(
    contract,
    df,
):

    contract_id = contract.get(
        "id"
    )

    contract_name = contract.get(
        "name"
    )

    data = normalize_history_frame(
        df
    )

    path = get_contract_history_file(
        contract_name
    )

    return {
        "contract_id":
            contract_id,

        "contract_name":
            contract_name,

        "bars":
            len(
                data
            ),

        "first_bar":
            (
                data.iloc[0][
                    "time"
                ]
                if not data.empty
                else None
            ),

        "last_bar":
            (
                data.iloc[-1][
                    "time"
                ]
                if not data.empty
                else None
            ),

        "file":
            str(
                path
            ),
    }