import pandas as pd


CHICAGO_TIMEZONE = "America/Chicago"
SESSION_ROLLOVER_HOUR = 17


def get_session_label(
    value,
):

    if value is None:

        return None

    try:

        timestamp = pd.to_datetime(
            value,
            utc=True,
            errors="coerce",
        )

    except Exception:

        return None

    if pd.isna(
        timestamp
    ):

        return None

    chicago_time = timestamp.tz_convert(
        CHICAGO_TIMEZONE
    )

    if (
        chicago_time.hour
        >= SESSION_ROLLOVER_HOUR
    ):

        session_date = (
            chicago_time
            + pd.Timedelta(
                days=1
            )
        ).date()

    else:

        session_date = (
            chicago_time.date()
        )

    return session_date.isoformat()


def add_session_column(
    df,
    time_column="time",
    session_column="session",
):

    data = df.copy()

    if (
        data is None
        or data.empty
    ):

        if session_column not in data.columns:

            data[
                session_column
            ] = pd.Series(
                dtype="object"
            )

        return data

    data[
        time_column
    ] = pd.to_datetime(
        data[
            time_column
        ],
        utc=True,
        errors="coerce",
    )

    chicago_time = (
        data[
            time_column
        ]
        .dt.tz_convert(
            CHICAGO_TIMEZONE
        )
    )

    normal_date = (
        chicago_time
        .dt.date
        .astype(
            str
        )
    )

    next_date = (
        chicago_time
        + pd.Timedelta(
            days=1
        )
    ).dt.date.astype(
        str
    )

    after_rollover = (
        chicago_time.dt.hour
        >= SESSION_ROLLOVER_HOUR
    )

    data[
        session_column
    ] = normal_date

    data.loc[
        after_rollover,
        session_column,
    ] = next_date[
        after_rollover
    ]

    return data


def add_session_vwap(
    df,
):

    data = add_session_column(
        df
    )

    if data.empty:

        data[
            "tp_volume"
        ] = pd.Series(
            dtype="float64"
        )

        data[
            "cum_tp_volume"
        ] = pd.Series(
            dtype="float64"
        )

        data[
            "cum_volume"
        ] = pd.Series(
            dtype="float64"
        )

        data[
            "vwap"
        ] = pd.Series(
            dtype="float64"
        )

        data[
            "vwap_plot"
        ] = pd.Series(
            dtype="float64"
        )

        return data

    typical_price = (
        data[
            "high"
        ]
        + data[
            "low"
        ]
        + data[
            "close"
        ]
    ) / 3.0

    data[
        "tp_volume"
    ] = (
        typical_price
        * data[
            "volume"
        ]
    )

    data[
        "cum_tp_volume"
    ] = (
        data.groupby(
            "session"
        )[
            "tp_volume"
        ]
        .cumsum()
    )

    data[
        "cum_volume"
    ] = (
        data.groupby(
            "session"
        )[
            "volume"
        ]
        .cumsum()
    )

    data[
        "vwap"
    ] = (
        data[
            "cum_tp_volume"
        ]
        / data[
            "cum_volume"
        ]
    )

    data[
        "vwap_plot"
    ] = data[
        "vwap"
    ]

    new_session = (
        data[
            "session"
        ]
        != data[
            "session"
        ].shift(
            1
        )
    )

    data.loc[
        new_session,
        "vwap_plot",
    ] = float(
        "nan"
    )

    return data