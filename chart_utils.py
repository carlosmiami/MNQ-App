import pandas as pd


BAR_MINUTES = 5


def get_missing_bar_times(
    df,
):

    if df is None or df.empty:

        return []

    if "time" not in df.columns:

        return []

    times = pd.to_datetime(
        df["time"],
        utc=True,
        errors="coerce",
    )

    times = (
        times
        .dropna()
        .drop_duplicates()
        .sort_values()
    )

    if len(times) < 2:

        return []

    expected = pd.date_range(
        start=times.iloc[0],
        end=times.iloc[-1],
        freq=f"{BAR_MINUTES}min",
        tz="UTC",
    )

    actual = pd.DatetimeIndex(
        times
    )

    missing = expected.difference(
        actual
    )

    return list(
        missing.to_pydatetime()
    )


def apply_market_rangebreaks(
    fig,
    df,
):

    missing_times = (
        get_missing_bar_times(
            df
        )
    )

    if not missing_times:

        return fig

    fig.update_xaxes(
        rangebreaks=[
            dict(
                values=missing_times,
                dvalue=(
                    BAR_MINUTES
                    * 60
                    * 1000
                ),
            )
        ]
    )

    return fig