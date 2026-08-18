from pathlib import Path

import pandas as pd
import streamlit as st


def _ui(en, es):
    """Display-only translation. Internal strategy values are unchanged."""
    language = st.session_state.get("language", "English")
    return es if language == "Español" else en


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
        _ui("Recent Setups", "Setups recientes"),
        expanded=False,
    ):

        if df.empty:

            st.info(
                _ui(
                    "No completed setups have been archived yet.",
                    "Todavía no se han archivado setups completados.",
                )
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
            _ui("Completed", "Completados"),
            summary[
                "total"
            ],
        )

        c2.metric(
            _ui("C5 Confirmed", "C5 confirmados"),
            summary[
                "confirmed"
            ],
        )

        c3.metric(
            _ui("Invalidated", "Invalidados"),
            summary[
                "invalidated"
            ],
        )

        c4.metric(
            _ui("LONG", "LARGO"),
            summary[
                "long"
            ],
        )

        c5.metric(
            _ui("SHORT", "CORTO"),
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

            if st.session_state.get("language", "English") == "Español":
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
            else:
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
            "Contract":
                _ui("Contract", "Contrato"),

            "Last Stage":
                _ui("Last Stage", "Última etapa"),

            "terminal_time":
                _ui("Finished", "Finalizado"),

            "side":
                _ui("Side", "Dirección"),

            "key_level":
                _ui("Level", "Nivel"),

            "final_stage":
                _ui("Result", "Resultado"),

            "terminal_reason":
                _ui("Reason", "Motivo"),

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

        # ====================================================
        # DISPLAY-ONLY VALUE TRANSLATION
        # Internal archived values remain unchanged.
        # ====================================================

        if st.session_state.get("language", "English") == "Español":

            if "side" in display.columns:
                display["side"] = display["side"].replace(
                    {
                        "LONG": "LARGO",
                        "SHORT": "CORTO",
                    }
                )

            if "final_stage" in display.columns:
                display["final_stage"] = display["final_stage"].replace(
                    {
                        "INVALIDATED": "INVALIDADO",
                        "C5 CONFIRMED": "C5 CONFIRMADO",
                    }
                )

            if "terminal_reason" in display.columns:
                display["terminal_reason"] = (
                    display["terminal_reason"]
                    .fillna("")
                    .astype(str)
                    .replace(
                        {
                            "C5 CONFIRMED":
                                "C5 CONFIRMADO",
                        }
                    )
                )

                reason_replacements = {
                    "LONG setup invalidated: no C3 retest within 12 bars.":
                        "Setup LARGO invalidado: no hubo retesteo C3 dentro de 12 velas.",

                    "SHORT setup invalidated: no C3 retest within 12 bars.":
                        "Setup CORTO invalidado: no hubo retesteo C3 dentro de 12 velas.",

                    "LONG setup invalidated: C5 failed.":
                        "Setup LARGO invalidado: C5 falló.",

                    "SHORT setup invalidated: C5 failed.":
                        "Setup CORTO invalidado: C5 falló.",

                    "LONG setup invalidated: C2 failed.":
                        "Setup LARGO invalidado: C2 falló.",

                    "SHORT setup invalidated: C2 failed.":
                        "Setup CORTO invalidado: C2 falló.",
                }

                display["terminal_reason"] = (
                    display["terminal_reason"]
                    .replace(reason_replacements)
                )

                # Generic prefixes for reasons containing dynamic values.
                display["terminal_reason"] = (
                    display["terminal_reason"]
                    .str.replace(
                        "LONG setup invalidated:",
                        "Setup LARGO invalidado:",
                        regex=False,
                    )
                    .str.replace(
                        "SHORT setup invalidated:",
                        "Setup CORTO invalidado:",
                        regex=False,
                    )
                    .str.replace(
                        "Setup invalidated:",
                        "Setup invalidado:",
                        regex=False,
                    )
                    .str.replace(
                        "trading session changed from",
                        "la sesión de trading cambió de",
                        regex=False,
                    )
                    .str.replace(
                        "contract changed from",
                        "el contrato cambió de",
                        regex=False,
                    )
                    .str.replace(
                        "Cross-session continuation",
                        "Continuación entre sesiones",
                        regex=False,
                    )
                    .str.replace(
                        "Cross-contract continuation",
                        "Continuación entre contratos",
                        regex=False,
                    )
                    .str.replace(
                        "no C3 retest within 12 bars",
                        "no hubo retesteo C3 dentro de 12 velas",
                        regex=False,
                    )
                    .str.replace(
                        "C5 failed",
                        "C5 falló",
                        regex=False,
                    )
                    .str.replace(
                        "C2 failed",
                        "C2 falló",
                        regex=False,
                    )
                )

            # Replace missing display values only.
            display = display.fillna("-")

        display = display.rename(
            columns=rename
        )

        st.dataframe(
            display,
            width="stretch",
            hide_index=True,
            height=330,
        )