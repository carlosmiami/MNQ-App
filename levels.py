import pandas as pd


def find_pivots(df, left=3, right=3):
    """
    Detecta swing highs y swing lows simples.
    """

    data = df.copy()

    data["pivot_high"] = False
    data["pivot_low"] = False

    highs = data["high"].to_numpy()
    lows = data["low"].to_numpy()

    for i in range(left, len(data) - right):

        current_high = highs[i]
        current_low = lows[i]

        left_highs = highs[i - left:i]
        right_highs = highs[i + 1:i + right + 1]

        left_lows = lows[i - left:i]
        right_lows = lows[i + 1:i + right + 1]

        if (
            current_high > max(left_highs)
            and current_high >= max(right_highs)
        ):
            data.loc[data.index[i], "pivot_high"] = True

        if (
            current_low < min(left_lows)
            and current_low <= min(right_lows)
        ):
            data.loc[data.index[i], "pivot_low"] = True

    return data


def cluster_prices(prices, tolerance):
    """
    Agrupa precios cercanos en un mismo nivel.
    """

    prices = sorted(prices)

    if not prices:
        return []

    clusters = [[prices[0]]]

    for price in prices[1:]:

        current_cluster = clusters[-1]
        cluster_mean = sum(current_cluster) / len(current_cluster)

        if abs(price - cluster_mean) <= tolerance:
            current_cluster.append(price)
        else:
            clusters.append([price])

    result = []

    for cluster in clusters:

        level = sum(cluster) / len(cluster)

        result.append(
            {
                "level": level,
                "touches": len(cluster),
            }
        )

    return result


def detect_key_levels(
    df,
    lookback=500,
    pivot_left=3,
    pivot_right=3,
    tolerance_points=8.0,
    max_levels=8,
):
    """
    Detecta niveles clave recientes de MNQ.

    Devuelve:
        {
            "resistance": [...],
            "support": [...]
        }
    """

    if df.empty:
        return {
            "resistance": [],
            "support": [],
        }

    data = df.tail(lookback).copy()

    data = find_pivots(
        data,
        left=pivot_left,
        right=pivot_right,
    )

    pivot_high_prices = (
        data.loc[
            data["pivot_high"],
            "high",
        ]
        .dropna()
        .tolist()
    )

    pivot_low_prices = (
        data.loc[
            data["pivot_low"],
            "low",
        ]
        .dropna()
        .tolist()
    )

    resistance_clusters = cluster_prices(
        pivot_high_prices,
        tolerance=tolerance_points,
    )

    support_clusters = cluster_prices(
        pivot_low_prices,
        tolerance=tolerance_points,
    )

    current_price = float(
        data.iloc[-1]["close"]
    )

    resistances = []

    for item in resistance_clusters:

        if item["level"] > current_price:

            resistances.append(
                {
                    "level": item["level"],
                    "touches": item["touches"],
                    "distance": item["level"] - current_price,
                }
            )

    supports = []

    for item in support_clusters:

        if item["level"] < current_price:

            supports.append(
                {
                    "level": item["level"],
                    "touches": item["touches"],
                    "distance": current_price - item["level"],
                }
            )

    resistances = sorted(
        resistances,
        key=lambda x: (
            -x["touches"],
            x["distance"],
        ),
    )

    supports = sorted(
        supports,
        key=lambda x: (
            -x["touches"],
            x["distance"],
        ),
    )

    resistances = resistances[:max_levels]
    supports = supports[:max_levels]

    return {
        "resistance": resistances,
        "support": supports,
    }