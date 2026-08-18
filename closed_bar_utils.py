import pandas as pd


BAR_MINUTES = 5


def to_utc_timestamp(
    value,
):

    if value is None:
        return None

    timestamp = pd.to_datetime(
        value,
        utc=True,
        errors="coerce",
    )

    if pd.isna(
        timestamp
    ):
        return None

    return timestamp


def get_last_closed_bar_start(
    as_of_time,
    bar_minutes=BAR_MINUTES,
):

    now = to_utc_timestamp(
        as_of_time
    )

    if now is None:
        return None

    # Example:
    #
    # 22:02:30 -> current candle starts 22:00
    #             last CLOSED candle starts 21:55
    #
    # 22:05:00 -> 22:00 candle is now closed.

    current_bar_start = now.floor(
        f"{bar_minutes}min"
    )

    return (
        current_bar_start
        - pd.Timedelta(
            minutes=bar_minutes
        )
    )


def filter_closed_bars(
    df,
    as_of_time,
    time_column="time",
    bar_minutes=BAR_MINUTES,
):

    if df is None:
        return None

    data = df.copy()

    if data.empty:
        return data

    if time_column not in data.columns:

        raise RuntimeError(
            f"Missing bar time column: "
            f"{time_column}"
        )

    now = to_utc_timestamp(
        as_of_time
    )

    if now is None:

        raise RuntimeError(
            "Closed-bar filter requires "
            "a valid as_of_time."
        )

    data[
        time_column
    ] = pd.to_datetime(
        data[
            time_column
        ],
        utc=True,
        errors="coerce",
    )

    data = data.dropna(
        subset=[
            time_column
        ]
    )

    # A 5m bar timestamp represents its START.
    #
    # Therefore it is closed only when:
    #
    # bar_start + 5 minutes <= as_of_time

    close_times = (
        data[
            time_column
        ]
        + pd.Timedelta(
            minutes=bar_minutes
        )
    )

    data = data[
        close_times
        <= now
    ]

    return (
        data
        .sort_values(
            time_column
        )
        .reset_index(
            drop=True
        )
    )


def bar_is_closed(
    bar_time,
    as_of_time,
    bar_minutes=BAR_MINUTES,
):

    bar_start = to_utc_timestamp(
        bar_time
    )

    now = to_utc_timestamp(
        as_of_time
    )

    if (
        bar_start is None
        or now is None
    ):
        return False

    return (
        bar_start
        + pd.Timedelta(
            minutes=bar_minutes
        )
        <= now
    )