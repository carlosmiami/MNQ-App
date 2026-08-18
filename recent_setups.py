from pathlib import Path

import pandas as pd
import streamlit as st


HISTORY_FILE = Path(
    "state/setup_history.csv"
)


# ============================================================
# LOAD HISTORY
# ============================================================

def load_setup_history():

    if not HISTORY_FILE.exists():

        return pd.DataFrame()

    try:

        df = pd.read_csv(
            HISTORY_FILE
        )

    except Exception:

        return pd.DataFrame()

    if df.empty:

        return df

    datetime_columns = [
        "c1_time",
        "c2_time",
        "c3_time",
        "c4_time",
        "c5_time",
        "terminal_time",
        "created_at",
        "updated_at",
    ]

    for column in datetime_columns:

        if column in df.columns:

            df[column] = pd.to_datetime(
                df[column],
                utc=True,
                errors="coerce",
            )

    if "key_level" in df.columns:

        df["key_level"] = pd.to_numeric(
            df["key_level"],
            errors="coerce",
        )

    return df


# ============================================================
# DISPLAY CONTRACT
# ============================================================

def get_display_contract(
    row,
):

    contract_name = row.get(
        "contract_name"
    )

    if pd.isna(
        contract_name
    ):

        return "LEGACY / UNBOUND"

    text = str(
        contract_name
    ).strip()

    if (
        not text
        or text.lower() in [
            "none",
            "nan",
        ]
    ):

        return "LEGACY / UNBOUND"

    return text


# ============================================================
# LAST REACHED STAGE
# ============================================================

def get_last_reached_stage(
    row,
):

    if pd.notna(
        row.get(
            "c5_time"
        )
    ):

        return "C5"

    if pd.notna(
        row.get(
            "c4_time"
        )
    ):

        return "C4"

    if pd.notna(
        row.get(
            "c3_time"
        )
    ):

        return "C3"

    if pd.notna(
        row.get(
            "c2_time"
        )
    ):

        return "C2"

    if pd.notna(
        row.get(
            "c1_time"
        )
    ):

        return "C1"

    return "-"


# ============================================================
# SUMMARY
# ============================================================

def get_summary(
    df,
):

    if df.empty:

        return {
            "total": 0,
            "confirmed": 0,
            "invalidated": 0,
            "long": 0,
            "short": 0,
        }

    final_stage = (
        df["final_stage"]
        .fillna("")
        .astype(str)
    )

    side = (
        df["side"]
        .fillna("")
        .astype(str)
    )

    return {
        "total":
            len(df),

        "confirmed":
            int(
                (
                    final_stage
                    == "C5 CONFIRMED"
                ).sum()
            ),

        "invalidated":
            int(
                (
                    final_stage
                    == "INVALIDATED"
                ).sum()
            ),

        "long":
            int(
                (
                    side
                    == "LONG"
                ).sum()
            ),

        "short":
            int(
                (
                    side
                    == "SHORT"
                ).sum()
            ),
    }


# ============================================================
# CONTRACT SUMMARY
# ============================================================

def get_contract_summary(
    df,
):

    if df.empty:

        return []

    display = df.copy()

    display[
        "Display Contract"
    ] = display.apply(
        get_display_contract,
        axis=1,
    )

    counts = (
        display[
            "Display Contract"
        ]
        .value_counts()
    )

    result = []

    for contract_name, count in counts.items():

        result.append(
            {
                "contract":
                    contract_name,

                "count":
                    int(
                        count
                    ),
            }
        )

    return result


# ============================================================
# RENDER
# ============================================================

def render_recent_setups(
    limit=15,
):

    df = load_setup_history()

    with st.expander(
        "Recent Setups",
        expanded=False,
    ):

        if df.empty:

            st.info(
                "No completed setups have been archived yet."
            )

            st.caption(
                "The next INVALIDATED or C5 CONFIRMED "
                "setup will be stored automatically."
            )

            return

        summary = get_summary(
            df
        )

        c1, c2, c3, c4, c5 = (
            st.columns(5)
        )

        c1.metric(
            "Completed",
            summary[
                "total"
            ],
        )

        c2.metric(
            "C5 Confirmed",
            summary[
                "confirmed"
            ],
        )

        c3.metric(
            "Invalidated",
            summary[
                "invalidated"
            ],
        )

        c4.metric(
            "LONG",
            summary[
                "long"
            ],
        )

        c5.metric(
            "SHORT",
            summary[
                "short"
            ],
        )

        # ====================================================
        # CONTRACT SUMMARY
        # ====================================================

        contract_summary = (
            get_contract_summary(
                df
            )
        )

        if contract_summary:

            summary_text = " | ".join(
                [
                    (
                        f"{item['contract']}: "
                        f"{item['count']} setup"
                        f"{'' if item['count'] == 1 else 's'}"
                    )
                    for item
                    in contract_summary
                ]
            )

            st.caption(
                summary_text
            )

        # ====================================================
        # TABLE
        # ====================================================

        display = (
            df.copy()
        )

        display[
            "Contract"
        ] = display.apply(
            get_display_contract,
            axis=1,
        )

        display[
            "Last Stage"
        ] = display.apply(
            get_last_reached_stage,
            axis=1,
        )

        if "terminal_time" in display.columns:

            display = (
                display
                .sort_values(
                    "terminal_time",
                    ascending=False,
                )
            )

        display = display.head(
            limit
        )

        columns = [
            "terminal_time",
            "Contract",
            "side",
            "key_level",
            "Last Stage",
            "final_stage",
            "terminal_reason",
            "c1_time",
            "c2_time",
            "c3_time",
            "c4_time",
            "c5_time",
        ]

        available = [
            column
            for column in columns
            if column in display.columns
        ]

        display = display[
            available
        ].copy()

        rename = {
            "terminal_time":
                "Finished",

            "side":
                "Side",

            "key_level":
                "Level",

            "final_stage":
                "Result",

            "terminal_reason":
                "Reason",

            "c1_time":
                "C1",

            "c2_time":
                "C2",

            "c3_time":
                "C3",

            "c4_time":
                "C4",

            "c5_time":
                "C5",
        }

        display = display.rename(
            columns=rename
        )

        st.dataframe(
            display,
            width="stretch",
            hide_index=True,
            height=330,
        )