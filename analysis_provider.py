import json
import tempfile
import threading

import pandas as pd

import setup_engine
import setup_history
import setup_state

from session_utils import get_session_label


_ENGINE_LOCK = threading.Lock()

MAX_RECOVERY_CONTEXT = 500

# A newly started Python process reconstructs the current session once
# before continuing with normal incremental state processing.
_PROCESS_RECOVERY_DONE = False

# Last normalized market snapshot seen by this process.
# Used to detect changes to already-seen bars inside the same
# contract/session so C1-C5 can be deterministically rebuilt.
_PROCESS_MARKET_SNAPSHOT = None


def _state_file_is_usable(
    contract_id=None,
    contract_name=None,
    current_session=None,
):
    """
    Validate the REAL persisted active_setup.json.

    Existence alone is not sufficient. Corrupt, truncated,
    structurally invalid, or contract-mismatched state forces
    deterministic session recovery.
    """

    path = setup_state.STATE_FILE

    if not path.exists():
        return False

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            state = json.load(file)

    except Exception:
        return False

    if not isinstance(state, dict):
        return False

    if not isinstance(
        state.get("active"),
        bool,
    ):
        return False

    stage = state.get("stage")

    valid_stages = {
        "NO SETUP",
        "C1 BREAKOUT",
        "C2 CONFIRMED",
        "C3 RETEST",
        "C4 DEFENSE",
        "C5 CONFIRMED",
        "INVALIDATED",
    }

    if stage not in valid_stages:
        return False

    active = state["active"]

    # ------------------------------------------------------------
    # ACTIVE LIFECYCLE
    # ------------------------------------------------------------

    if active:

        if stage not in {
            "C1 BREAKOUT",
            "C2 CONFIRMED",
            "C3 RETEST",
            "C4 DEFENSE",
        }:
            return False

        if state.get("side") not in {
            "LONG",
            "SHORT",
        }:
            return False

        if not state.get("setup_id"):
            return False

        if not state.get("contract_id"):
            return False

        if not state.get("contract_name"):
            return False

        if state.get("key_level") is None:
            return False

        if not state.get("c1_time"):
            return False

        # An active C1-C4 lifecycle may never survive into
        # another CME trading session.  Treat it as unusable
        # here so the provider performs deterministic recovery
        # before the engine is allowed to continue.
        if current_session is not None:

            setup_session = get_session_label(
                state.get("c1_time")
            )

            if (
                setup_session is None
                or setup_session != current_session
            ):
                return False

        if (
            contract_id is not None
            and str(state.get("contract_id"))
            != str(contract_id)
        ):
            return False

        if (
            contract_name is not None
            and str(state.get("contract_name"))
            != str(contract_name)
        ):
            return False

        if (
            stage in {
                "C2 CONFIRMED",
                "C3 RETEST",
                "C4 DEFENSE",
            }
            and not state.get("c2_time")
        ):
            return False

        if (
            stage in {
                "C3 RETEST",
                "C4 DEFENSE",
            }
            and not state.get("c3_time")
        ):
            return False

        if (
            stage == "C4 DEFENSE"
            and not state.get("c4_time")
        ):
            return False

    # ------------------------------------------------------------
    # INACTIVE STATE
    # ------------------------------------------------------------

    else:

        if stage not in {
            "NO SETUP",
            "C5 CONFIRMED",
            "INVALIDATED",
        }:
            return False

        if stage in {
            "C5 CONFIRMED",
            "INVALIDATED",
        }:

            if not state.get("setup_id"):
                return False

            if state.get("side") not in {
                "LONG",
                "SHORT",
            }:
                return False

            if not state.get("contract_id"):
                return False

            if not state.get("contract_name"):
                return False

            if state.get("key_level") is None:
                return False

            if not state.get("c1_time"):
                return False

            if not state.get("terminal_time"):
                return False

    return True


def _recover_current_session(
    df,
    contract_id,
    contract_name,
):
    """
    Deterministically reconstruct the current C1-C5 lifecycle.

    Replay state AND replay history live inside context-isolated
    temporary directories.

    Nothing generated during replay can modify:
        state/active_setup.json
        state/setup_history.csv

    Only the final reconstructed active state is written back
    after the isolated replay has completely finished.
    """

    if df is None:
        return setup_engine._empty_result(
            "No market data."
        )

    data = df.copy()

    if data.empty:
        return setup_engine._empty_result(
            "No market data."
        )

    data["time"] = pd.to_datetime(
        data["time"],
        utc=True,
    )

    data = (
        data
        .sort_values("time")
        .reset_index(drop=True)
    )

    latest_time = data.iloc[-1]["time"]

    current_session = get_session_label(
        latest_time
    )

    if current_session is None:

        return setup_engine.evaluate_setup(
            data,
            contract_id=contract_id,
            contract_name=contract_name,
            as_of_time=
                latest_time
                + pd.Timedelta(minutes=5),
        )

    session_indices = [
        index
        for index, timestamp
        in enumerate(data["time"])
        if get_session_label(timestamp)
        == current_session
    ]

    if not session_indices:

        return setup_engine._empty_result(
            "No bars available in current trading session."
        )

    recovered_result = None
    recovered_state = None

    with tempfile.TemporaryDirectory(
        prefix="mnq_session_recovery_"
    ) as tmp:

        with setup_state.isolated_state_dir(
            tmp
        ):

            with setup_history.isolated_history_dir(
                tmp
            ):

                for index in session_indices:

                    start = max(
                        0,
                        index
                        - MAX_RECOVERY_CONTEXT
                        + 1,
                    )

                    window = (
                        data
                        .iloc[
                            start:index + 1
                        ]
                        .copy()
                        .reset_index(
                            drop=True
                        )
                    )

                    recovered_result = (
                        setup_engine.evaluate_setup(
                            window,
                            contract_id=contract_id,
                            contract_name=contract_name,
                            as_of_time=
                                data.iloc[index]["time"]
                                + pd.Timedelta(
                                    minutes=5
                                ),
                        )
                    )

                recovered_state = (
                    setup_state.load_setup_state()
                )

    # We are now OUTSIDE the isolated ContextVars.
    # This writes only the final deterministic state to the
    # real persistent location.
    if recovered_state is not None:

        setup_state.save_setup_state(
            recovered_state
        )

    if recovered_result is None:

        return setup_engine._empty_result()

    return recovered_result



def _build_market_snapshot(
    df,
    contract_id=None,
    contract_name=None,
):
    if (
        df is None
        or df.empty
        or "time" not in df.columns
    ):
        return None

    required = [
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    if any(
        column not in df.columns
        for column in required
    ):
        return None

    data = df[
        required
    ].copy()

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
            subset=["time"],
            keep="last",
        )
        .sort_values("time")
        .reset_index(drop=True)
    )

    if data.empty:
        return None

    latest_time = data.iloc[-1]["time"]

    return {
        "contract_id":
            None
            if contract_id is None
            else str(contract_id),

        "contract_name":
            None
            if contract_name is None
            else str(contract_name),

        "session":
            get_session_label(
                latest_time
            ),

        "data":
            data,
    }


def _historical_market_mutated(
    previous_snapshot,
    current_snapshot,
):
    if (
        previous_snapshot is None
        or current_snapshot is None
    ):
        return False

    if (
        previous_snapshot.get("contract_id")
        != current_snapshot.get("contract_id")
    ):
        return False

    if (
        previous_snapshot.get("contract_name")
        != current_snapshot.get("contract_name")
    ):
        return False

    if (
        previous_snapshot.get("session")
        != current_snapshot.get("session")
    ):
        return False

    previous = previous_snapshot.get("data")
    current = current_snapshot.get("data")

    if (
        previous is None
        or current is None
        or previous.empty
        or current.empty
    ):
        return False

    previous_latest = previous.iloc[-1]["time"]

    previous_seen = (
        previous[
            previous["time"]
            <= previous_latest
        ]
        .copy()
    )

    current_seen = (
        current[
            current["time"]
            <= previous_latest
        ]
        .copy()
    )

    merged = previous_seen.merge(
        current_seen,
        on="time",
        how="outer",
        suffixes=("_old", "_new"),
        indicator=True,
    )

    # A previously seen timestamp disappeared.
    if (
        merged["_merge"]
        != "both"
    ).any():
        return True

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]:

        old_col = f"{column}_old"
        new_col = f"{column}_new"

        different = (
            merged[old_col]
            .ne(
                merged[new_col]
            )
        )

        if different.any():
            return True

    return False


def evaluate_setup_public(
    df,
    contract_id=None,
    contract_name=None,
    as_of_time=None,
):
    """
    Single frontend boundary for C1-C5.

    Guarantees:
      - one engine operation at a time in this process
      - deterministic reconstruction after process restart
      - deterministic reconstruction after missing/corrupt state
      - replay state/history isolation
      - no mutation of module-global state/history paths
    """

    global _PROCESS_RECOVERY_DONE
    global _PROCESS_MARKET_SNAPSHOT

    with _ENGINE_LOCK:

        current_snapshot = _build_market_snapshot(
            df,
            contract_id=contract_id,
            contract_name=contract_name,
        )

        historical_mutation = (
            _historical_market_mutated(
                _PROCESS_MARKET_SNAPSHOT,
                current_snapshot,
            )
        )

        current_session = None

        if (
            df is not None
            and not df.empty
            and "time" in df.columns
        ):

            try:

                times = pd.to_datetime(
                    df["time"],
                    utc=True,
                    errors="coerce",
                ).dropna()

                if not times.empty:

                    current_session = (
                        get_session_label(
                            times.max()
                        )
                    )

            except Exception:

                current_session = None

        state_usable = (
            _state_file_is_usable(
                contract_id=contract_id,
                contract_name=contract_name,
                current_session=current_session,
            )
        )

        needs_recovery = (
            not _PROCESS_RECOVERY_DONE
            or not state_usable
            or historical_mutation
        )

        if needs_recovery:

            result = _recover_current_session(
                df=df,
                contract_id=contract_id,
                contract_name=contract_name,
            )

            _PROCESS_RECOVERY_DONE = True
            _PROCESS_MARKET_SNAPSHOT = current_snapshot

            return result

        result = setup_engine.evaluate_setup(
            df,
            contract_id=contract_id,
            contract_name=contract_name,
            as_of_time=as_of_time,
        )

        _PROCESS_MARKET_SNAPSHOT = current_snapshot

        return result
