import re


QUARTER_TO_MONTH_CODE = {
    "MAR": "H",
    "JUN": "M",
    "SEP": "U",
    "DEC": "Z",
}


# ============================================================
# CONTRACT PARSING
# ============================================================

def parse_mnq_contract(
    contract_name,
):

    text = str(
        contract_name
        or ""
    ).strip().upper()

    # TopstepX examples:
    # MNQU6 -> SEP 2026
    # MNQZ6 -> DEC 2026
    # MNQH7 -> MAR 2027
    #
    # The final digit is compared against
    # rollover year % 10.

    match = re.fullmatch(
        r"MNQ([HMUZ])(\d)",
        text,
    )

    if not match:

        return None

    return {
        "month_code":
            match.group(
                1
            ),

        "year_digit":
            int(
                match.group(
                    2
                )
            ),
    }


def get_contract_month_code(
    contract_name,
):

    parsed = parse_mnq_contract(
        contract_name
    )

    if parsed is None:

        return None

    return parsed[
        "month_code"
    ]


def get_roll_year(
    roll_status,
):

    if not roll_status:

        return None

    explicit_year = roll_status.get(
        "year"
    )

    if explicit_year is not None:

        try:

            return int(
                explicit_year
            )

        except (
            TypeError,
            ValueError,
        ):

            return None

    # Backward-compatible fallback for older test/status
    # dictionaries that may not yet contain "year".

    for field in [
        "roll_date",
        "expiration_date",
    ]:

        value = roll_status.get(
            field
        )

        if value is None:

            continue

        year = getattr(
            value,
            "year",
            None,
        )

        if year is not None:

            return int(
                year
            )

    return None


def contract_is_roll_contract(
    contract_name,
    roll_status,
):

    if not roll_status:

        return False

    parsed = parse_mnq_contract(
        contract_name
    )

    if parsed is None:

        return False

    quarter = roll_status.get(
        "quarter"
    )

    expected_code = (
        QUARTER_TO_MONTH_CODE.get(
            quarter
        )
    )

    if expected_code is None:

        return False

    if (
        parsed[
            "month_code"
        ]
        != expected_code
    ):

        return False

    expected_year = get_roll_year(
        roll_status
    )

    # Backward compatibility:
    #
    # Old callers without any usable year information
    # retain the prior month-code behavior.
    #
    # Production rollover_calendar now always supplies year.

    if expected_year is None:

        return True

    expected_year_digit = (
        expected_year
        % 10
    )

    return (
        parsed[
            "year_digit"
        ]
        == expected_year_digit
    )


# ============================================================
# OPERATIONAL GATE
# ============================================================

def evaluate_operational_gate(
    contract_name,
    history_status,
    local_sync_state,
    integrity_state,
    roll_status,
    market_state=None,
):

    reasons = []
    warnings = []

    # ========================================================
    # CURRENT MARKET SCHEDULE FAIL-SAFE
    # ========================================================
    #
    # Production callers supply the current shared market
    # schedule state.
    #
    # SCHEDULE UNKNOWN means we are inside a CME holiday
    # window but exact MNQ trading hours are not encoded.
    # C1-C5 must therefore remain fail-safe blocked.
    #
    # UNKNOWN is also blocked when explicitly supplied.
    #
    # market_state=None preserves backward compatibility for
    # older callers/tests that predate this input.

    if market_state == "SCHEDULE UNKNOWN":

        reasons.append(
            "Current MNQ market schedule is UNKNOWN."
        )

    elif market_state == "UNKNOWN":

        reasons.append(
            "Current MNQ market state is UNKNOWN."
        )

    elif market_state == "CLOSED":

        reasons.append(
            "MNQ market is CLOSED."
        )

    elif market_state == "MAINTENANCE":

        reasons.append(
            "MNQ is inside the daily maintenance window."
        )

    elif market_state == "DAILY HALT":

        reasons.append(
            "MNQ is inside the daily trading halt."
        )

    # ========================================================
    # HISTORY
    # ========================================================

    history_ready = bool(
        history_status
        and history_status.get(
            "ready"
        )
    )

    if not history_ready:

        reasons.append(
            "Contract history is not READY."
        )

    # ========================================================
    # LOCAL SYNC
    # ========================================================

    if (
        local_sync_state
        != "SYNCED"
    ):

        reasons.append(
            "Local contract history is not SYNCED."
        )

    # ========================================================
    # HISTORY INTEGRITY
    # ========================================================

    if (
        integrity_state
        != "CLEAN"
    ):

        reasons.append(
            "Local contract history integrity is not CLEAN."
        )

    # ========================================================
    # ROLLOVER
    # ========================================================

    roll_state = (
        roll_status.get(
            "state"
        )
        if roll_status
        else "UNKNOWN"
    )

    if roll_state == "ROLL APPROACHING":

        warnings.append(
            "MNQ rollover is approaching."
        )

    elif roll_state == "ROLL CRITICAL":

        warnings.append(
            "MNQ is inside the critical rollover window."
        )

    elif roll_state == "ROLL NOW":

        still_roll_contract = (
            contract_is_roll_contract(
                contract_name,
                roll_status,
            )
        )

        if still_roll_contract:

            reasons.append(
                (
                    f"{contract_name} is still the active "
                    "contract at the CME roll date."
                )
            )

        else:

            warnings.append(
                (
                    "TopstepX appears to have switched "
                    "away from the rollover contract."
                )
            )

    elif roll_state == "UNKNOWN":

        reasons.append(
            "Rollover status is UNKNOWN."
        )

    allowed = (
        len(
            reasons
        )
        == 0
    )

    if allowed:

        message = (
            "C1-C5 operational gate is ENABLED."
        )

    else:

        message = (
            "C1-C5 operational gate is BLOCKED: "
            + " ".join(
                reasons
            )
        )

    return {
        "allowed":
            allowed,

        "state":
            (
                "ENABLED"
                if allowed
                else "BLOCKED"
            ),

        "reasons":
            reasons,

        "warnings":
            warnings,

        "message":
            message,

        "roll_state":
            roll_state,
    }