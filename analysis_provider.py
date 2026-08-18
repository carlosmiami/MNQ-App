import tempfile
import threading
from pathlib import Path

import pandas as pd

import setup_engine
import setup_history
import setup_state

from session_utils import get_session_label


_RECOVERY_LOCK = threading.Lock()

MAX_RECOVERY_CONTEXT = 500


def _configure_state_paths(root):
    root = Path(root)

    setup_state.STATE_DIR = root
    setup_state.STATE_FILE = root / "active_setup.json"
    setup_state.STATE_LOCK_FILE = root / "active_setup.lock"

    setup_history.STATE_DIR = root
    setup_history.HISTORY_FILE = root / "setup_history.csv"
    setup_history.HISTORY_LOCK_FILE = root / "setup_history.lock"


def _recover_current_session(
    df,
    contract_id,
    contract_name,
):
    """
    Rebuild the current C1-C5 lifecycle deterministically
    when the persisted active state is missing.

    Recovery runs against temporary state/history so replay
    cannot duplicate or contaminate the real setup history.
    """

    data = df.copy()

    data["time"] = pd.to_datetime(
        data["time"],
        utc=True,
    )

    data = (
        data
        .sort_values("time")
        .reset_index(drop=True)
    )

    if data.empty:
        return setup_engine._empty_result(
            "No market data."
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
        return setup_engine.evaluate_setup(
            data,
            contract_id=contract_id,
            contract_name=contract_name,
            as_of_time=
                latest_time
                + pd.Timedelta(minutes=5),
        )

    original_state_paths = (
        setup_state.STATE_DIR,
        setup_state.STATE_FILE,
        setup_state.STATE_LOCK_FILE,
    )

    original_history_paths = (
        setup_history.STATE_DIR,
        setup_history.HISTORY_FILE,
        setup_history.HISTORY_LOCK_FILE,
    )

    recovered_result = None
    recovered_state = None

    try:

        with tempfile.TemporaryDirectory(
            prefix="mnq_session_recovery_"
        ) as tmp:

            _configure_state_paths(
                tmp
            )

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
                            + pd.Timedelta(minutes=5),
                    )
                )

            recovered_state = (
                setup_state.load_setup_state()
            )

    finally:

        (
            setup_state.STATE_DIR,
            setup_state.STATE_FILE,
            setup_state.STATE_LOCK_FILE,
        ) = original_state_paths

        (
            setup_history.STATE_DIR,
            setup_history.HISTORY_FILE,
            setup_history.HISTORY_LOCK_FILE,
        ) = original_history_paths

    if recovered_state is not None:

        setup_state.save_setup_state(
            recovered_state
        )

    if recovered_result is None:

        return setup_engine._empty_result()

    return recovered_result


def evaluate_setup_public(
    df,
    contract_id=None,
    contract_name=None,
    as_of_time=None,
):
    """
    Public-facing analysis provider.

    Normal operation:
        delegates to the local strategy engine.

    Restart recovery:
        if persisted setup state is missing, rebuild the
        current session before continuing live processing.

    Future:
        this boundary can call the private backend API.
    """

    if setup_state.STATE_FILE.exists():

        return setup_engine.evaluate_setup(
            df,
            contract_id=contract_id,
            contract_name=contract_name,
            as_of_time=as_of_time,
        )

    with _RECOVERY_LOCK:

        # Another Streamlit session may have recovered state
        # while this session waited for the lock.
        if setup_state.STATE_FILE.exists():

            return setup_engine.evaluate_setup(
                df,
                contract_id=contract_id,
                contract_name=contract_name,
                as_of_time=as_of_time,
            )

        return _recover_current_session(
            df=df,
            contract_id=contract_id,
            contract_name=contract_name,
        )
