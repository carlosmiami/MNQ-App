import pandas as pd

from levels import detect_key_levels

from setup_state import (
    load_setup_state,
    start_setup,
    confirm_c2,
    confirm_c3,
    confirm_c4,
    confirm_c5,
    invalidate_setup,
)

from setup_history import (
    archive_terminal_setup,
)

from session_utils import (
    get_session_label,
)

from closed_bar_utils import (
    filter_closed_bars,
)

from ohlcv_integrity import (
    validate_ohlcv_frame,
)


C3_ATR_FRACTION = 0.20
C3_MAX_WAIT_BARS = 12
C4_MAX_WAIT_BARS = 3


def _to_timestamp(value):

    if value is None:
        return None

    return pd.to_datetime(
        value,
        utc=True,
    )


def _public_result(state):

    return {
        "side":
            state.get(
                "side"
            ),

        "stage":
            state.get(
                "stage",
                "NO SETUP",
            ),

        "level":
            state.get(
                "key_level"
            ),

        "contract_id":
            state.get(
                "contract_id"
            ),

        "contract_name":
            state.get(
                "contract_name"
            ),

        "c1_time":
            _to_timestamp(
                state.get(
                    "c1_time"
                )
            ),

        "c2_time":
            _to_timestamp(
                state.get(
                    "c2_time"
                )
            ),

        "c3_time":
            _to_timestamp(
                state.get(
                    "c3_time"
                )
            ),

        "c4_time":
            _to_timestamp(
                state.get(
                    "c4_time"
                )
            ),

        "c5_time":
            _to_timestamp(
                state.get(
                    "c5_time"
                )
            ),

        "message":
            state.get(
                "message",
                "Waiting for setup.",
            ),
    }


def _empty_result(
    message="Waiting for breakout.",
):

    return {
        "side": None,
        "stage": "NO SETUP",
        "level": None,

        "contract_id": None,
        "contract_name": None,

        "c1_time": None,
        "c2_time": None,
        "c3_time": None,
        "c4_time": None,
        "c5_time": None,

        "message": message,
    }


def _add_atr14(df):

    data = df.copy()

    previous_close = (
        data["close"]
        .shift(1)
    )

    tr1 = (
        data["high"]
        - data["low"]
    )

    tr2 = (
        data["high"]
        - previous_close
    ).abs()

    tr3 = (
        data["low"]
        - previous_close
    ).abs()

    true_range = pd.concat(
        [
            tr1,
            tr2,
            tr3,
        ],
        axis=1,
    ).max(
        axis=1
    )

    data["atr14"] = (
        true_range
        .rolling(14)
        .mean()
    )

    return data


def _get_levels_from_history(
    history,
):

    if (
        history is None
        or len(history) < 50
    ):

        return [], []

    levels = detect_key_levels(
        history,
        lookback=min(
            500,
            len(history),
        ),
        pivot_left=3,
        pivot_right=3,
        tolerance_points=8.0,
        max_levels=8,
    )

    resistances = sorted(
        levels[
            "resistance"
        ],
        key=lambda x:
            x["distance"],
    )

    supports = sorted(
        levels[
            "support"
        ],
        key=lambda x:
            x["distance"],
    )

    return (
        resistances,
        supports,
    )


# ============================================================
# CONTRACT BINDING
# ============================================================

def _validate_contract(
    contract_id,
    contract_name,
):

    if not contract_id:
        return False

    if not contract_name:
        return False

    return True


def _state_contract_matches(
    state,
    contract_id,
    contract_name,
):

    state_contract_id = (
        state.get(
            "contract_id"
        )
    )

    state_contract_name = (
        state.get(
            "contract_name"
        )
    )

    if not state_contract_id:
        return False

    if not state_contract_name:
        return False

    return (
        str(
            state_contract_id
        )
        == str(
            contract_id
        )
        and
        str(
            state_contract_name
        )
        == str(
            contract_name
        )
    )


# ============================================================
# C1
# ============================================================

def _find_new_c1(
    data,
):

    latest_index = (
        len(data)
        - 1
    )

    latest = data.iloc[
        latest_index
    ]

    history = (
        data
        .iloc[
            :latest_index
        ]
        .copy()
    )

    resistances, supports = (
        _get_levels_from_history(
            history
        )
    )

    # LONG C1
    if resistances:

        level = float(
            resistances[
                0
            ][
                "level"
            ]
        )

        previous = data.iloc[
            latest_index - 1
        ]

        valid = (
            float(
                previous[
                    "close"
                ]
            )
            <= level

            and

            float(
                latest[
                    "close"
                ]
            )
            > level
        )

        if valid:

            return {
                "side":
                    "LONG",

                "level":
                    level,

                "time":
                    latest[
                        "time"
                    ],
            }

    # SHORT C1
    if supports:

        level = float(
            supports[
                0
            ][
                "level"
            ]
        )

        previous = data.iloc[
            latest_index - 1
        ]

        valid = (
            float(
                previous[
                    "close"
                ]
            )
            >= level

            and

            float(
                latest[
                    "close"
                ]
            )
            < level
        )

        if valid:

            return {
                "side":
                    "SHORT",

                "level":
                    level,

                "time":
                    latest[
                        "time"
                    ],
            }

    return None


# ============================================================
# C2
# ============================================================

def _manage_c1(
    data,
    state,
):

    side = state[
        "side"
    ]

    level = float(
        state[
            "key_level"
        ]
    )

    c1_time = _to_timestamp(
        state[
            "c1_time"
        ]
    )

    later = data[
        data[
            "time"
        ]
        > c1_time
    ]

    if later.empty:
        return state

    c2 = later.iloc[
        0
    ]

    if pd.isna(
        c2[
            "atr14"
        ]
    ):

        return state

    if side == "LONG":

        valid = (
            float(
                c2[
                    "close"
                ]
            )
            > level
        )

    else:

        valid = (
            float(
                c2[
                    "close"
                ]
            )
            < level
        )

    if valid:

        return confirm_c2(
            state,
            c2[
                "time"
            ],
            c2[
                "atr14"
            ],
        )

    return invalidate_setup(
        state,
        (
            f"{side} setup invalidated: "
            f"C2 failed."
        ),
        terminal_time=
            c2[
                "time"
            ],
    )


# ============================================================
# C3
# ============================================================

def _manage_c2(
    data,
    state,
):

    side = state[
        "side"
    ]

    level = float(
        state[
            "key_level"
        ]
    )

    c2_time = _to_timestamp(
        state[
            "c2_time"
        ]
    )

    atr14 = float(
        state[
            "c2_atr14"
        ]
    )

    tolerance = (
        atr14
        * C3_ATR_FRACTION
    )

    zone_low = (
        level
        - tolerance
    )

    zone_high = (
        level
        + tolerance
    )

    all_later = data[
        data[
            "time"
        ]
        > c2_time
    ]

    later = (
        all_later
        .head(
            C3_MAX_WAIT_BARS
        )
    )

    # --------------------------------------------------------
    # Find the C2 close.
    #
    # C2 itself already establishes direction:
    #
    # LONG  -> C2 close > level
    # SHORT -> C2 close < level
    #
    # Every C3 candidate must therefore approach the retest
    # zone from the correct breakout side.
    # --------------------------------------------------------

    c2_rows = data[
        data[
            "time"
        ]
        == c2_time
    ]

    if c2_rows.empty:

        return state

    previous_close = float(
        c2_rows.iloc[-1][
            "close"
        ]
    )

    for _, candle in later.iterrows():

        candle_low = float(
            candle[
                "low"
            ]
        )

        candle_high = float(
            candle[
                "high"
            ]
        )

        intersects_zone = (
            candle_low
            <= zone_high

            and

            candle_high
            >= zone_low
        )

        if side == "LONG":

            correct_approach = (
                previous_close
                > level
            )

        else:

            correct_approach = (
                previous_close
                < level
            )

        touched = (
            correct_approach
            and intersects_zone
        )

        if touched:

            return confirm_c3(
                state,
                candle,
            )

        previous_close = float(
            candle[
                "close"
            ]
        )

    if (
        len(
            all_later
        )
        >= C3_MAX_WAIT_BARS
    ):

        terminal_candle = (
            later.iloc[
                -1
            ]
        )

        return invalidate_setup(
            state,
            (
                f"{side} setup invalidated: "
                f"no C3 retest within "
                f"{C3_MAX_WAIT_BARS} bars."
            ),
            terminal_time=
                terminal_candle[
                    "time"
                ],
        )

    return state


# ============================================================
# C4
# ============================================================

def _manage_c3(
    data,
    state,
):

    side = state[
        "side"
    ]

    level = float(
        state[
            "key_level"
        ]
    )

    c3_time = _to_timestamp(
        state[
            "c3_time"
        ]
    )

    c3_high = float(
        state[
            "c3_high"
        ]
    )

    c3_low = float(
        state[
            "c3_low"
        ]
    )

    all_later = data[
        data[
            "time"
        ]
        > c3_time
    ]

    later = (
        all_later
        .head(
            C4_MAX_WAIT_BARS
        )
    )

    for _, candle in later.iterrows():

        close = float(
            candle[
                "close"
            ]
        )

        if side == "LONG":

            valid = (
                close
                > level

                and

                close
                > c3_high
            )

        else:

            valid = (
                close
                < level

                and

                close
                < c3_low
            )

        if valid:

            return confirm_c4(
                state,
                candle,
            )

    if (
        len(
            all_later
        )
        >= C4_MAX_WAIT_BARS
    ):

        terminal_candle = (
            later.iloc[
                -1
            ]
        )

        return invalidate_setup(
            state,
            (
                f"{side} setup invalidated: "
                f"C4 defense failed."
            ),
            terminal_time=
                terminal_candle[
                    "time"
                ],
        )

    return state


# ============================================================
# C5
# ============================================================

def _manage_c4(
    data,
    state,
):

    side = state[
        "side"
    ]

    c4_time = _to_timestamp(
        state[
            "c4_time"
        ]
    )

    c4_close = float(
        state[
            "c4_close"
        ]
    )

    later = data[
        data[
            "time"
        ]
        > c4_time
    ]

    if later.empty:
        return state

    c5 = later.iloc[
        0
    ]

    c5_close = float(
        c5[
            "close"
        ]
    )

    if side == "LONG":

        valid = (
            c5_close
            > c4_close
        )

    else:

        valid = (
            c5_close
            < c4_close
        )

    if valid:

        return confirm_c5(
            state,
            c5,
        )

    return invalidate_setup(
        state,
        (
            f"{side} setup invalidated: "
            f"C5 failed."
        ),
        terminal_time=
            c5[
                "time"
            ],
    )


# ============================================================
# MAIN ENGINE
# ============================================================

def evaluate_setup(
    df,
    contract_id=None,
    contract_name=None,
    as_of_time=None,
):

    # ========================================================
    # FAIL SAFE: CONTRACT REQUIRED
    # ========================================================

    if not _validate_contract(
        contract_id,
        contract_name,
    ):

        return _empty_result(
            "C1-C5 blocked: current contract "
            "identity is unavailable."
        )

    if df is None:

        return _empty_result(
            "No market data."
        )

    if len(df) < 60:

        return _empty_result(
            "Not enough historical data."
        )

    data = df.copy()

    data["time"] = pd.to_datetime(
        data[
            "time"
        ],
        utc=True,
    )

    data = (
        data
        .sort_values(
            "time"
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # CLOSED-BAR FAIL-SAFE
    #
    # TopstepX already requests includePartialBar=False.
    # This is an independent engine-level defense.
    #
    # When as_of_time is supplied, bars whose 5-minute
    # interval has not completed are removed before any
    # C1-C5 processing.
    # ========================================================

    if as_of_time is not None:

        data = filter_closed_bars(
            data,
            as_of_time=
                as_of_time,
        )

        if len(data) < 60:

            return _empty_result(
                "C1-C5 blocked: not enough CLOSED "
                "5-minute bars after filtering."
            )

    # ========================================================
    # OHLCV INTEGRITY FAIL-SAFE
    #
    # No malformed closed 5-minute bar may reach ATR,
    # key levels, setup state, or C1-C5 inference.
    #
    # Policy is fail-safe:
    #   - do not silently remove corrupt bars
    #   - do not continue analysis
    #   - return NO SETUP explicitly
    # ========================================================

    ohlcv_integrity = validate_ohlcv_frame(
        data
    )


    if (
        ohlcv_integrity[
            "status"
        ]
        != "OK"
    ):

        invalid_count = (
            ohlcv_integrity.get(
                "invalid_count",
                0,
            )
        )

        invalid_indices = (
            ohlcv_integrity.get(
                "invalid_indices",
                [],
            )
        )

        reason = (
            ohlcv_integrity.get(
                "reason",
                "UNKNOWN",
            )
        )


        return _empty_result(
            "C1-C5 blocked: INVALID OHLCV "
            "market data detected. "
            f"Reason={reason}; "
            f"invalid_bars={invalid_count}; "
            f"indices={invalid_indices}."
        )


    if "atr14" not in data.columns:

        data = _add_atr14(
            data
        )

    state = load_setup_state()

    # ========================================================
    # EXISTING ACTIVE SETUP:
    # CONTRACT MUST MATCH EXACTLY
    # ========================================================

    if state.get(
        "active"
    ):

        if not _state_contract_matches(
            state,
            contract_id,
            contract_name,
        ):

            old_contract = (
                state.get(
                    "contract_name"
                )
                or "UNBOUND"
            )

            latest_time = (
                data.iloc[
                    -1
                ][
                    "time"
                ]
            )

            state = invalidate_setup(
                state,
                (
                    "Setup invalidated: contract "
                    f"changed from {old_contract} "
                    f"to {contract_name}. "
                    "Cross-contract continuation "
                    "is prohibited."
                ),
                terminal_time=
                    latest_time,
            )

            # Archive the OLD contract setup before returning.
            # Its original contract_id / contract_name remain
            # preserved in state.
            archive_terminal_setup(
                state
            )

            return _public_result(
                state
            )

        # ====================================================
        # ACTIVE SETUP SESSION BINDING
        #
        # C1-C5 is one intraday lifecycle.
        # It may NEVER continue through the 17:00 CT
        # CME session boundary.
        # ====================================================

        latest_time = (
            data.iloc[
                -1
            ][
                "time"
            ]
        )

        setup_session = (
            get_session_label(
                state.get(
                    "c1_time"
                )
            )
        )

        current_session = (
            get_session_label(
                latest_time
            )
        )

        # ----------------------------------------------------
        # Session identity must be available.
        # ----------------------------------------------------

        if (
            setup_session is None
            or current_session is None
        ):

            state = invalidate_setup(
                state,
                (
                    "Setup invalidated: trading session "
                    "identity is unavailable. "
                    "Cross-session continuation "
                    "is prohibited."
                ),
                terminal_time=
                    latest_time,
            )

            archive_terminal_setup(
                state
            )

            return _public_result(
                state
            )

        # ----------------------------------------------------
        # Hard boundary:
        #
        # Example August CDT:
        #
        # 16:55 CT -> session 2026-08-17
        # 17:00 CT -> session 2026-08-18
        #
        # C1/C2/C3/C4 from the prior session may not use
        # bars from the newly opened session.
        # ----------------------------------------------------

        if (
            setup_session
            != current_session
        ):

            state = invalidate_setup(
                state,
                (
                    "Setup invalidated: trading session "
                    f"changed from {setup_session} "
                    f"to {current_session}. "
                    "Cross-session continuation "
                    "is prohibited."
                ),
                terminal_time=
                    latest_time,
            )

            archive_terminal_setup(
                state
            )

            return _public_result(
                state
            )

        stage = state.get(
            "stage"
        )

        if stage == "C1 BREAKOUT":

            state = _manage_c1(
                data,
                state,
            )

        elif stage == "C2 CONFIRMED":

            state = _manage_c2(
                data,
                state,
            )

        elif stage == "C3 RETEST":

            state = _manage_c3(
                data,
                state,
            )

        elif stage == "C4 DEFENSE":

            state = _manage_c4(
                data,
                state,
            )

        elif stage == "C5 CONFIRMED":

            return _public_result(
                state
            )

        if not state.get(
            "active"
        ):

            archive_terminal_setup(
                state
            )

        return _public_result(
            state
        )

    # ========================================================
    # SEARCH FOR NEW C1
    # ========================================================

    candidate = _find_new_c1(
        data
    )

    if candidate is None:

        return _empty_result()

    state = start_setup(
        side=
            candidate[
                "side"
            ],

        key_level=
            candidate[
                "level"
            ],

        c1_time=
            candidate[
                "time"
            ],

        contract_id=
            contract_id,

        contract_name=
            contract_name,
    )

    return _public_result(
        state
    )


def evaluate_c1_c2(
    df,
    contract_id=None,
    contract_name=None,
    as_of_time=None,
):

    return evaluate_setup(
        df,
        contract_id=
            contract_id,
        contract_name=
            contract_name,
        as_of_time=
            as_of_time,
    )