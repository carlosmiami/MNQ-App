import json
import os
import tempfile

from pathlib import Path
from datetime import datetime, timezone

from state_lock import (
    FileLock,
    replace_with_retry,
)


STATE_DIR = Path("state")
STATE_FILE = STATE_DIR / "active_setup.json"
STATE_LOCK_FILE = STATE_DIR / "active_setup.lock"


def _now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def _ensure_state_dir():

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def _default_state():

    return {
        "active": False,
        "setup_id": None,

        # ====================================================
        # CONTRACT BINDING
        # ====================================================

        "contract_id": None,
        "contract_name": None,

        "side": None,
        "stage": "NO SETUP",

        "key_level": None,

        "c1_time": None,
        "c2_time": None,
        "c3_time": None,
        "c4_time": None,
        "c5_time": None,

        "c2_atr14": None,

        "c3_high": None,
        "c3_low": None,
        "c3_close": None,

        "c4_close": None,

        "terminal_time": None,
        "terminal_reason": None,

        "created_at": None,
        "updated_at": None,

        "message": "Waiting for setup.",
    }


def load_setup_state():

    _ensure_state_dir()

    if not STATE_FILE.exists():

        return _default_state()

    try:

        with STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(
                f
            )

    except Exception:

        return _default_state()

    default = _default_state()

    for key, value in default.items():

        if key not in data:

            data[key] = value

    return data


def save_setup_state(
    state,
):

    _ensure_state_dir()

    state = dict(
        state
    )

    state["updated_at"] = (
        _now()
    )

    temp_path = None

    with FileLock(
        STATE_LOCK_FILE
    ):

        try:

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=STATE_DIR,
                prefix="active_setup_",
                suffix=".tmp",
                delete=False,
            ) as file:

                temp_path = Path(
                    file.name
                )

                json.dump(
                    state,
                    file,
                    indent=2,
                    default=str,
                )

                file.flush()

                os.fsync(
                    file.fileno()
                )

            replace_with_retry(
                temp_path,
                STATE_FILE,
            )

            temp_path = None

        finally:

            if (
                temp_path is not None
                and temp_path.exists()
            ):

                try:

                    temp_path.unlink()

                except OSError:

                    pass


def clear_setup_state():

    state = _default_state()

    save_setup_state(
        state
    )

    return state


def start_setup(
    side,
    key_level,
    c1_time,
    contract_id,
    contract_name,
):

    if not contract_id:

        raise RuntimeError(
            "Cannot start setup without contract_id."
        )

    if not contract_name:

        raise RuntimeError(
            "Cannot start setup without contract_name."
        )

    now = _now()

    setup_id = (
        f"{contract_name}_"
        f"{side}_"
        f"{str(c1_time)}_"
        f"{float(key_level):.2f}"
    )

    state = _default_state()

    state.update(
        {
            "active": True,

            "setup_id":
                setup_id,

            "contract_id":
                str(
                    contract_id
                ),

            "contract_name":
                str(
                    contract_name
                ),

            "side":
                side,

            "stage":
                "C1 BREAKOUT",

            "key_level":
                float(
                    key_level
                ),

            "c1_time":
                str(
                    c1_time
                ),

            "created_at":
                now,

            "updated_at":
                now,

            "message":
                (
                    f"{side} C1 on "
                    f"{contract_name} at "
                    f"{float(key_level):.2f}. "
                    f"Waiting for C2."
                ),
        }
    )

    save_setup_state(
        state
    )

    return state


def confirm_c2(
    state,
    c2_time,
    atr14,
):

    state = dict(
        state
    )

    state["stage"] = (
        "C2 CONFIRMED"
    )

    state["c2_time"] = str(
        c2_time
    )

    state["c2_atr14"] = float(
        atr14
    )

    state["message"] = (
        f"{state['side']} C2 confirmed. "
        f"Waiting for C3 retest."
    )

    save_setup_state(
        state
    )

    return state


def confirm_c3(
    state,
    candle,
):

    state = dict(
        state
    )

    state["stage"] = (
        "C3 RETEST"
    )

    state["c3_time"] = str(
        candle["time"]
    )

    state["c3_high"] = float(
        candle["high"]
    )

    state["c3_low"] = float(
        candle["low"]
    )

    state["c3_close"] = float(
        candle["close"]
    )

    state["message"] = (
        f"{state['side']} C3 retest detected. "
        f"Waiting for C4 defense."
    )

    save_setup_state(
        state
    )

    return state


def confirm_c4(
    state,
    candle,
):

    state = dict(
        state
    )

    state["stage"] = (
        "C4 DEFENSE"
    )

    state["c4_time"] = str(
        candle["time"]
    )

    state["c4_close"] = float(
        candle["close"]
    )

    state["message"] = (
        f"{state['side']} C4 defense confirmed. "
        f"Waiting for C5."
    )

    save_setup_state(
        state
    )

    return state


def confirm_c5(
    state,
    candle,
):

    state = dict(
        state
    )

    state["active"] = False

    state["stage"] = (
        "C5 CONFIRMED"
    )

    state["c5_time"] = str(
        candle["time"]
    )

    state["terminal_time"] = str(
        candle["time"]
    )

    state["terminal_reason"] = (
        "C5 CONFIRMED"
    )

    state["message"] = (
        f"{state['side']} C5 CONFIRMED "
        f"on {state.get('contract_name')} "
        f"at {state['key_level']:.2f}."
    )

    save_setup_state(
        state
    )

    return state


def invalidate_setup(
    state,
    reason,
    terminal_time=None,
):

    state = dict(
        state
    )

    state["active"] = False

    state["stage"] = (
        "INVALIDATED"
    )

    if terminal_time is not None:

        state["terminal_time"] = str(
            terminal_time
        )

    state["terminal_reason"] = (
        reason
    )

    state["message"] = (
        reason
    )

    save_setup_state(
        state
    )

    return state