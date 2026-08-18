from __future__ import annotations

import math

import pandas as pd


REQUIRED_OHLCV_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
]


PRICE_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
]


def _invalid_result(
    reason,
    normalized=None,
):
    return {
        "status":
            "INVALID_OHLCV",

        "reason":
            reason,

        "normalized":
            normalized,
    }


def validate_ohlcv_bar(
    bar,
):
    """
    Validate one OHLCV bar.

    Policy:
    - open/high/low/close/volume required
    - all values numeric and finite
    - prices strictly > 0
    - volume >= 0
    - high >= low
    - open inside [low, high]
    - close inside [low, high]

    Zero volume is allowed.
    """

    if bar is None:

        return _invalid_result(
            "BAR_MISSING"
        )


    normalized = {}


    for column in REQUIRED_OHLCV_COLUMNS:

        try:
            value = bar[column]

        except Exception:

            return _invalid_result(
                f"MISSING_{column.upper()}"
            )


        try:
            value = float(value)

        except Exception:

            return _invalid_result(
                f"NON_NUMERIC_{column.upper()}"
            )


        if not math.isfinite(
            value
        ):

            return _invalid_result(
                f"NON_FINITE_{column.upper()}"
            )


        normalized[
            column
        ] = value


    for column in PRICE_COLUMNS:

        if (
            normalized[column]
            <= 0.0
        ):

            return _invalid_result(
                f"NON_POSITIVE_{column.upper()}",
                normalized=normalized,
            )


    if (
        normalized["volume"]
        < 0.0
    ):

        return _invalid_result(
            "NEGATIVE_VOLUME",
            normalized=normalized,
        )


    high = normalized[
        "high"
    ]

    low = normalized[
        "low"
    ]

    open_price = normalized[
        "open"
    ]

    close = normalized[
        "close"
    ]


    if high < low:

        return _invalid_result(
            "HIGH_BELOW_LOW",
            normalized=normalized,
        )


    if not (
        low
        <= open_price
        <= high
    ):

        return _invalid_result(
            "OPEN_OUTSIDE_RANGE",
            normalized=normalized,
        )


    if not (
        low
        <= close
        <= high
    ):

        return _invalid_result(
            "CLOSE_OUTSIDE_RANGE",
            normalized=normalized,
        )


    return {
        "status":
            "OK",

        "reason":
            None,

        "normalized":
            normalized,
    }


def validate_ohlcv_frame(
    df,
):
    """
    Validate an OHLCV DataFrame without mutating it.

    Any invalid bar invalidates the whole frame.

    Returns all invalid row indices so the caller can
    fail safely and report exactly where corruption exists.
    """

    if df is None:

        return {
            "status":
                "INVALID_OHLCV",

            "reason":
                "FRAME_MISSING",

            "invalid_count":
                0,

            "invalid_indices":
                [],
        }


    if not isinstance(
        df,
        pd.DataFrame,
    ):

        return {
            "status":
                "INVALID_OHLCV",

            "reason":
                "NOT_DATAFRAME",

            "invalid_count":
                0,

            "invalid_indices":
                [],
        }


    missing_columns = [
        column
        for column
        in REQUIRED_OHLCV_COLUMNS
        if column
        not in df.columns
    ]


    if missing_columns:

        return {
            "status":
                "INVALID_OHLCV",

            "reason":
                (
                    "MISSING_COLUMNS:"
                    + ",".join(
                        missing_columns
                    )
                ),

            "invalid_count":
                len(df),

            "invalid_indices":
                list(
                    df.index
                ),
        }


    invalid_indices = []

    invalid_reasons = {}


    for index, row in df.iterrows():

        result = validate_ohlcv_bar(
            row
        )


        if (
            result["status"]
            != "OK"
        ):

            invalid_indices.append(
                index
            )

            invalid_reasons[
                index
            ] = result[
                "reason"
            ]


    if invalid_indices:

        return {
            "status":
                "INVALID_OHLCV",

            "reason":
                "INVALID_BARS",

            "invalid_count":
                len(
                    invalid_indices
                ),

            "invalid_indices":
                invalid_indices,

            "invalid_reasons":
                invalid_reasons,
        }


    return {
        "status":
            "OK",

        "reason":
            None,

        "invalid_count":
            0,

        "invalid_indices":
            [],

        "invalid_reasons":
            {},
    }
