from datetime import datetime, timedelta, timezone

import requests


API_BASE_URL = "https://api.topstepx.com"


# ============================================================
# LEGACY / COMPATIBILITY
# ============================================================

MNQ_CONTRACT_ID = "CON.F.US.MNQ.U26"

MNQ_SYMBOL_ID = "F.US.MNQ"


# ============================================================
# HISTORY / WARM-UP POLICY
# ============================================================

# EMA200 needs 200 bars, but MNQ-App key-level analysis
# can use a 500-bar lookback.
#
# Therefore a contract is not considered fully READY
# until at least 500 CLOSED 5-minute bars are available.
MNQ_MIN_READY_5M_BARS = 500

# Informational intermediate threshold.
MNQ_MIN_EMA_5M_BARS = 200


# ============================================================
# TIME
# ============================================================

def _to_utc(
    value,
):

    if value is None:

        return datetime.now(
            timezone.utc
        )

    if value.tzinfo is None:

        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


# ============================================================
# HEADERS
# ============================================================

def _headers(
    token,
):

    if not token:

        raise RuntimeError(
            "No authentication token provided."
        )

    return {
        "Authorization":
            f"Bearer {token}",

        "Content-Type":
            "application/json",

        "Accept":
            "text/plain",
    }


# ============================================================
# CONTRACT SEARCH
# ============================================================

def search_mnq_contracts(
    token,
):

    payload = {
        "searchText": "MNQ",
        "live": False,
    }

    response = requests.post(
        f"{API_BASE_URL}/api/Contract/search",
        headers=_headers(token),
        json=payload,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    if not data.get(
        "success"
    ):

        raise RuntimeError(
            "TopstepX contract search failed: "
            f"{data.get('errorMessage')}"
        )

    contracts = data.get(
        "contracts",
        [],
    )

    mnq_contracts = []

    for contract in contracts:

        contract_id = str(
            contract.get(
                "id",
                "",
            )
        )

        name = str(
            contract.get(
                "name",
                "",
            )
        ).upper()

        symbol_id = str(
            contract.get(
                "symbolId",
                "",
            )
        ).upper()

        is_mnq = (
            symbol_id
            == MNQ_SYMBOL_ID.upper()
            or
            ".MNQ."
            in contract_id.upper()
            or
            name.startswith(
                "MNQ"
            )
        )

        if is_mnq:

            mnq_contracts.append(
                contract
            )

    return mnq_contracts


# ============================================================
# ACTIVE CONTRACT
# ============================================================

def get_active_mnq_contract(
    token,
):

    contracts = search_mnq_contracts(
        token
    )

    if not contracts:

        raise RuntimeError(
            "No MNQ contracts were returned "
            "by TopstepX."
        )

    active = []

    for contract in contracts:

        active_flag = contract.get(
            "activeContract"
        )

        if active_flag is None:

            active_flag = contract.get(
                "active"
            )

        if active_flag is True:

            active.append(
                contract
            )

    if len(active) == 0:

        available = ", ".join(
            str(
                contract.get(
                    "name",
                    contract.get(
                        "id",
                        "?",
                    ),
                )
            )
            for contract in contracts
        )

        raise RuntimeError(
            "TopstepX returned MNQ contracts, "
            "but none is marked active. "
            f"Returned: {available}"
        )

    if len(active) > 1:

        active_names = ", ".join(
            str(
                contract.get(
                    "name",
                    contract.get(
                        "id",
                        "?",
                    ),
                )
            )
            for contract in active
        )

        raise RuntimeError(
            "More than one MNQ contract is marked active. "
            "Automatic rollover stopped for safety. "
            f"Active contracts: {active_names}"
        )

    contract = active[
        0
    ]

    contract_id = contract.get(
        "id"
    )

    if not contract_id:

        raise RuntimeError(
            "Active MNQ contract has no contract ID."
        )

    return {
        "id":
            contract_id,

        "name":
            contract.get(
                "name"
            ),

        "description":
            contract.get(
                "description"
            ),

        "tickSize":
            contract.get(
                "tickSize"
            ),

        "tickValue":
            contract.get(
                "tickValue"
            ),

        "activeContract":
            True,

        "symbolId":
            contract.get(
                "symbolId"
            ),
    }


def get_active_mnq_contract_id(
    token,
):

    contract = (
        get_active_mnq_contract(
            token
        )
    )

    return contract[
        "id"
    ]


# ============================================================
# GENERIC BAR RETRIEVAL
# ============================================================

def get_bars(
    token,
    contract_id,
    days=2,
    limit=500,
    end_time=None,
    unit=2,
    unit_number=5,
):

    if not contract_id:

        raise RuntimeError(
            "No contract ID provided."
        )

    end_time = _to_utc(
        end_time
    )

    start_time = (
        end_time
        - timedelta(
            days=days
        )
    )

    payload = {
        "contractId":
            contract_id,

        "live":
            False,

        "startTime":
            start_time.isoformat(),

        "endTime":
            end_time.isoformat(),

        "unit":
            unit,

        "unitNumber":
            unit_number,

        "limit":
            limit,

        "includePartialBar":
            False,
    }

    response = requests.post(
        f"{API_BASE_URL}/api/History/retrieveBars",
        headers=_headers(token),
        json=payload,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    if not data.get(
        "success"
    ):

        raise RuntimeError(
            "TopstepX bars request failed: "
            f"{data.get('errorMessage')}"
        )

    bars = data.get(
        "bars",
        [],
    )

    bars.sort(
        key=lambda bar:
            bar["t"]
    )

    return bars


# ============================================================
# MNQ 5-MINUTE BARS
# ============================================================

def get_mnq_5m_bars(
    token,
    contract_id=None,
    days=2,
    limit=500,
    end_time=None,
):

    if contract_id is None:

        contract_id = (
            get_active_mnq_contract_id(
                token
            )
        )

    return get_bars(
        token=token,
        contract_id=contract_id,
        days=days,
        limit=limit,
        end_time=end_time,
        unit=2,
        unit_number=5,
    )


# ============================================================
# HISTORY / WARM-UP STATUS
# ============================================================

def classify_mnq_history(
    bar_count,
    min_ready_bars=MNQ_MIN_READY_5M_BARS,
):

    bar_count = int(
        bar_count
        or 0
    )

    if bar_count >= min_ready_bars:

        return {
            "state":
                "READY",

            "ready":
                True,

            "message":
                (
                    f"{bar_count} closed 5m bars available. "
                    "Full MNQ-App analysis is allowed."
                ),
        }

    if bar_count >= MNQ_MIN_EMA_5M_BARS:

        missing = (
            min_ready_bars
            - bar_count
        )

        return {
            "state":
                "LIMITED",

            "ready":
                False,

            "message":
                (
                    f"{bar_count} closed 5m bars available. "
                    f"EMA200 has context, but {missing} more "
                    "bars are required for full level warm-up."
                ),
        }

    missing_ema = (
        MNQ_MIN_EMA_5M_BARS
        - bar_count
    )

    return {
        "state":
            "WARMING UP",

        "ready":
            False,

        "message":
            (
                f"Only {bar_count} closed 5m bars available. "
                f"At least {missing_ema} more bars are needed "
                "before EMA200 itself has 200-bar context."
            ),
    }


def get_mnq_5m_history_status(
    token,
    contract_id=None,
    contract_name=None,
    days=30,
    limit=5000,
    min_ready_bars=MNQ_MIN_READY_5M_BARS,
):

    # Resolve the active contract only when caller
    # did not explicitly provide one.
    if contract_id is None:

        contract = (
            get_active_mnq_contract(
                token
            )
        )

        contract_id = (
            contract[
                "id"
            ]
        )

        contract_name = (
            contract.get(
                "name"
            )
        )

    bars = get_mnq_5m_bars(
        token=token,
        contract_id=contract_id,
        days=days,
        limit=limit,
    )

    status = classify_mnq_history(
        bar_count=len(
            bars
        ),
        min_ready_bars=min_ready_bars,
    )

    first_bar = None
    last_bar = None

    if bars:

        first_bar = bars[
            0
        ].get(
            "t"
        )

        last_bar = bars[
            -1
        ].get(
            "t"
        )

    return {
        "contract_id":
            contract_id,

        "contract_name":
            contract_name,

        "bar_count":
            len(
                bars
            ),

        "minimum_ready_bars":
            min_ready_bars,

        "first_bar":
            first_bar,

        "last_bar":
            last_bar,

        "state":
            status[
                "state"
            ],

        "ready":
            status[
                "ready"
            ],

        "message":
            status[
                "message"
            ],
    }

# ============================================================
# INCREMENTAL MNQ 5-MINUTE HISTORY
# ============================================================

def get_bars_between(
    token,
    contract_id,
    start_time,
    end_time,
    unit=2,
    unit_number=5,
    limit=5000,
):

    if not contract_id:

        raise RuntimeError(
            "No contract ID provided."
        )

    start_time = _to_utc(
        start_time
    )

    end_time = _to_utc(
        end_time
    )

    if start_time >= end_time:

        return []

    payload = {
        "contractId":
            contract_id,

        "live":
            False,

        "startTime":
            start_time.isoformat(),

        "endTime":
            end_time.isoformat(),

        "unit":
            unit,

        "unitNumber":
            unit_number,

        "limit":
            limit,

        "includePartialBar":
            False,
    }

    response = requests.post(
        f"{API_BASE_URL}/api/History/retrieveBars",
        headers=_headers(token),
        json=payload,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    if not data.get(
        "success"
    ):

        raise RuntimeError(
            "TopstepX incremental bars request failed: "
            f"{data.get('errorMessage')}"
        )

    bars = data.get(
        "bars",
        [],
    )

    bars.sort(
        key=lambda bar:
            bar["t"]
    )

    return bars


def get_mnq_5m_bars_since(
    token,
    contract_id,
    start_time,
    end_time=None,
    chunk_days=7,
):

    if not contract_id:

        raise RuntimeError(
            "No contract ID provided."
        )

    start_time = _to_utc(
        start_time
    )

    end_time = _to_utc(
        end_time
    )

    if start_time >= end_time:

        return []

    all_bars = []

    # "Since" means strictly AFTER the last stored
    # closed 5-minute candle.
    cursor = (
        start_time
        + timedelta(minutes=5)
    )

    while cursor < end_time:

        chunk_end = min(
            cursor
            + timedelta(
                days=chunk_days
            ),
            end_time,
        )

        bars = get_bars_between(
            token=token,
            contract_id=contract_id,
            start_time=cursor,
            end_time=chunk_end,
            unit=2,
            unit_number=5,
            limit=5000,
        )

        all_bars.extend(
            bars
        )

        cursor = chunk_end

    # Deduplicate because adjacent range boundaries
    # may return the same candle.

    unique = {}

    for bar in all_bars:

        timestamp = bar.get(
            "t"
        )

        if timestamp is None:

            continue

        unique[
            timestamp
        ] = bar

    result = list(
        unique.values()
    )

    result.sort(
        key=lambda bar:
            bar["t"]
    )

    return result

