from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from auth import get_token
from market_data import (
    get_mnq_5m_bars,
    get_mnq_5m_bars_since,
    get_active_mnq_contract,
    classify_mnq_history,
)
from levels import detect_key_levels
from analysis_provider import evaluate_setup_public
from recent_setups import render_recent_setups
from chart_utils import apply_market_rangebreaks
from rollover_calendar import get_roll_status
from operational_gate import evaluate_operational_gate
from history_repair import repair_contract_history
from system_status import (
    render_system_status,
    load_local_history_status,
    classify_local_history_sync,
    get_cme_market_state,
)
from contract_history import (
    persist_contract_history,
    load_contract_history,
)


# ============================================================================
# UI TRANSLATIONS
# ============================================================================

TRANSLATIONS = {
    "English": {
        "language": "Language",
        "in_progress": "IN PROGRESS",
        "waiting": "WAITING",
        "wait": "WAIT",
        "no_setup": "NO SETUP",
        "none": "NONE",
        "direction": "Direction",
        "stage": "Stage",
        "key_level": "Key Level",
        "breakout": "Breakout",
        "acceptance": "Acceptance",
        "retest": "Retest",
        "defense": "Defense",
        "confirmation": "Confirmation",
        "last": "Last",
        "setup_lifecycle": "C1 → C5 SETUP LIFECYCLE",
        "market_details": "Market Details | Levels / Indicators",
        "how_to_use": "How to Use the System",
        "how_to_use_body": (
            "**1. Direction**\n\n"
            "Shows whether the current setup is LONG, SHORT, or NONE. "
            "It is not a trade order.\n\n"
            "**2. Stage**\n\n"
            "Shows how far the current setup has progressed through the "
            "C1 → C5 sequence.\n\n"
            "**3. Key Level**\n\n"
            "The price level around which the current setup is being evaluated.\n\n"
            "**4. C1 — Breakout**\n\n"
            "Price breaks through the relevant level.\n\n"
            "**5. C2 — Acceptance**\n\n"
            "Price closes and shows acceptance beyond the breakout level.\n\n"
            "**6. C3 — Retest**\n\n"
            "Price returns to test the breakout area.\n\n"
            "**7. C4 — Defense**\n\n"
            "The retest area holds and price shows rejection or defense.\n\n"
            "**8. C5 — Confirmation**\n\n"
            "The setup receives its final confirmation. A setup should not be "
            "considered fully confirmed before C5.\n\n"
            "**WAIT / IN PROGRESS**\n\n"
            "WAIT means that stage has not started yet. IN PROGRESS means the "
            "current stage is developing but is not yet completed.\n\n"
            "**Important**\n\n"
            "Use the system as an analytical aid only. Review market context, "
            "risk, system status, data freshness, and your own trading plan "
            "before making any decision."
        ),
        "how_to_use": "How to Use the System",
        "how_to_use_body": (
            "**1. Direction**\n\n"
            "Shows whether the current setup is LONG, SHORT, or NONE. "
            "It is not a trade order.\n\n"
            "**2. Stage**\n\n"
            "Shows how far the current setup has progressed through the "
            "C1 → C5 sequence.\n\n"
            "**3. Key Level**\n\n"
            "The price level around which the current setup is being evaluated.\n\n"
            "**4. C1 — Breakout**\n\n"
            "Price breaks through the relevant level.\n\n"
            "**5. C2 — Acceptance**\n\n"
            "Price closes and shows acceptance beyond the breakout level.\n\n"
            "**6. C3 — Retest**\n\n"
            "Price returns to test the breakout area.\n\n"
            "**7. C4 — Defense**\n\n"
            "The retest area holds and price shows rejection or defense.\n\n"
            "**8. C5 — Confirmation**\n\n"
            "The setup receives its final confirmation. A setup should not be "
            "considered fully confirmed before C5.\n\n"
            "**WAIT / IN PROGRESS**\n\n"
            "WAIT means that stage has not started yet. IN PROGRESS means the "
            "current stage is developing but is not yet completed.\n\n"
            "**Important**\n\n"
            "Use the system as an analytical aid only. Review market context, "
            "risk, system status, data freshness, and your own trading plan "
            "before making any decision."
        ),
        "forward_validation": "Forward Validation | H1 / H2 / H3",
        "frozen_from": "Frozen from",
        "logged_c5": "Logged C5",
        "completed": "Completed",
        "open_display": "Open",
        "no_fill": "No Fill",
        "risk_gt_30": "Risk > 30",
        "overlap": "Overlap",
        "hypothesis": "Hypothesis",
        "setups": "Setups",
        "wins": "W",
        "losses": "L",
        "win_pct": "Win %",
        "total_r": "Total R",
        "avg_r": "Avg R",
        "recent_forward_setups": "Recent Forward Setups",
        "h1_label": "H1 SHORT + OVERNIGHT",
        "h2_label": "H2 VWAP NOT ALIGNED",
        "h3_label": "H3 DISTANCE > 2 ATR",
        "canonical_parity": "Canonical v1 | NQ-Bot / Atlas parity",
        "canonical_caption": "Research parity reference only | Stop buffer = 1 point | Max risk = 25 points | TP = 1.5R | Pending = 30 minutes | Quantity = 1 MNQ",
        "waiting_breakout": "Waiting for breakout.",
        "beta": "BETA • Educational / Testing Use Only",
        "app_subtitle": "Real-Time MNQ Setup Analysis",
        "disclaimer_title": "⚠️ Risk & Use Disclaimer",
        "disclaimer_body": (
            "This application is provided for educational, research, "
            "and testing purposes only. It does not provide financial, "
            "investment, trading, legal, or tax advice, and nothing "
            "displayed by the application should be interpreted as a "
            "recommendation or solicitation to buy, sell, or hold any "
            "financial instrument. Futures trading involves substantial "
            "risk of loss and may not be appropriate for every person. "
            "You are solely responsible for your own trading decisions "
            "and should independently verify all information before "
            "acting. Historical results, backtests, simulated results, "
            "indicators, setups, signals, projections, and displayed "
            "market information do not guarantee future performance. "
            "Data may be delayed, incomplete, unavailable, or inaccurate. "
            "The application is provided as-is and without any warranty "
            "of accuracy, availability, profitability, or fitness for a "
            "particular purpose. Use of this application is entirely at "
            "your own risk."
        ),
    },

    "Español": {
        "language": "Idioma",
        "in_progress": "EN CURSO",
        "waiting": "ESPERANDO",
        "wait": "ESPERA",
        "no_setup": "SIN SETUP",
        "none": "NINGUNA",
        "direction": "Dirección",
        "stage": "Etapa",
        "key_level": "Nivel clave",
        "breakout": "Ruptura",
        "acceptance": "Aceptación",
        "retest": "Retesteo",
        "defense": "Defensa",
        "confirmation": "Confirmación",
        "last": "Último",
        "setup_lifecycle": "CICLO DEL SETUP C1 → C5",
        "market_details": "Detalles del mercado | Niveles / Indicadores",
        "how_to_use": "Cómo usar el sistema",
        "how_to_use_body": (
            "**1. Dirección**\n\n"
            "Muestra si el setup actual es LARGO, CORTO o NINGUNO. "
            "No es una orden de trading.\n\n"
            "**2. Etapa**\n\n"
            "Muestra cuánto ha avanzado el setup actual dentro de la "
            "secuencia C1 → C5.\n\n"
            "**3. Nivel clave**\n\n"
            "Es el nivel de precio alrededor del cual se está evaluando "
            "el setup actual.\n\n"
            "**4. C1 — Ruptura**\n\n"
            "El precio rompe el nivel relevante.\n\n"
            "**5. C2 — Aceptación**\n\n"
            "El precio cierra y muestra aceptación más allá del nivel de ruptura.\n\n"
            "**6. C3 — Retesteo**\n\n"
            "El precio regresa a probar el área de la ruptura.\n\n"
            "**7. C4 — Defensa**\n\n"
            "El área del retesteo aguanta y el precio muestra rechazo o defensa.\n\n"
            "**8. C5 — Confirmación**\n\n"
            "El setup recibe su confirmación final. Un setup no debe considerarse "
            "completamente confirmado antes de C5.\n\n"
            "**ESPERA / EN CURSO**\n\n"
            "ESPERA significa que esa etapa todavía no ha comenzado. EN CURSO "
            "significa que la etapa actual se está desarrollando, pero todavía "
            "no ha terminado.\n\n"
            "**Importante**\n\n"
            "Usa el sistema solamente como herramienta de análisis. Revisa el "
            "contexto del mercado, el riesgo, el estado del sistema, la frescura "
            "de los datos y tu propio plan de trading antes de tomar una decisión."
        ),
        "how_to_use": "Cómo usar el sistema",
        "how_to_use_body": (
            "**1. Dirección**\n\n"
            "Muestra si el setup actual es LARGO, CORTO o NINGUNO. "
            "No es una orden de trading.\n\n"
            "**2. Etapa**\n\n"
            "Muestra cuánto ha avanzado el setup actual dentro de la "
            "secuencia C1 → C5.\n\n"
            "**3. Nivel clave**\n\n"
            "Es el nivel de precio alrededor del cual se está evaluando "
            "el setup actual.\n\n"
            "**4. C1 — Ruptura**\n\n"
            "El precio rompe el nivel relevante.\n\n"
            "**5. C2 — Aceptación**\n\n"
            "El precio cierra y muestra aceptación más allá del nivel de ruptura.\n\n"
            "**6. C3 — Retesteo**\n\n"
            "El precio regresa a probar el área de la ruptura.\n\n"
            "**7. C4 — Defensa**\n\n"
            "El área del retesteo aguanta y el precio muestra rechazo o defensa.\n\n"
            "**8. C5 — Confirmación**\n\n"
            "El setup recibe su confirmación final. Un setup no debe considerarse "
            "completamente confirmado antes de C5.\n\n"
            "**ESPERA / EN CURSO**\n\n"
            "ESPERA significa que esa etapa todavía no ha comenzado. EN CURSO "
            "significa que la etapa actual se está desarrollando, pero todavía "
            "no ha terminado.\n\n"
            "**Importante**\n\n"
            "Usa el sistema solamente como herramienta de análisis. Revisa el "
            "contexto del mercado, el riesgo, el estado del sistema, la frescura "
            "de los datos y tu propio plan de trading antes de tomar una decisión."
        ),
        "forward_validation": "Validación Forward | H1 / H2 / H3",
        "frozen_from": "Congelado desde",
        "logged_c5": "C5 registrados",
        "completed": "Completados",
        "open_display": "Abiertos",
        "no_fill": "Sin ejecución",
        "risk_gt_30": "Riesgo > 30",
        "overlap": "Solapamiento",
        "hypothesis": "Hipótesis",
        "setups": "Setups",
        "wins": "G",
        "losses": "P",
        "win_pct": "% ganadas",
        "total_r": "R total",
        "avg_r": "R promedio",
        "recent_forward_setups": "Setups Forward recientes",
        "h1_label": "H1 CORTO + NOCTURNA",
        "h2_label": "H2 VWAP NO ALINEADO",
        "h3_label": "H3 DISTANCIA > 2 ATR",
        "canonical_parity": "Canonical v1 | Paridad NQ-Bot / Atlas",
        "canonical_caption": "Referencia de paridad para investigación solamente | Buffer del stop = 1 punto | Riesgo máximo = 25 puntos | TP = 1.5R | Pendiente = 30 minutos | Cantidad = 1 MNQ",
        "waiting_breakout": "Esperando ruptura.",
        "beta": "BETA • Solo para uso educativo y de pruebas",
        "app_subtitle": "Análisis de setups MNQ en tiempo real",
        "disclaimer_title": "⚠️ Aviso de riesgo y uso",
        "disclaimer_body": (
            "Esta aplicación se proporciona únicamente con fines "
            "educativos, de investigación y de prueba. No proporciona "
            "asesoramiento financiero, de inversión, de trading, legal "
            "ni fiscal, y nada de lo mostrado por la aplicación debe "
            "interpretarse como una recomendación o solicitud para "
            "comprar, vender o mantener ningún instrumento financiero. "
            "El trading de futuros implica un riesgo sustancial de "
            "pérdida y puede no ser apropiado para todas las personas. "
            "Cada usuario es el único responsable de sus propias "
            "decisiones de trading y debe verificar independientemente "
            "toda la información antes de actuar. Los resultados "
            "históricos, backtests, resultados simulados, indicadores, "
            "setups, señales, proyecciones y datos de mercado mostrados "
            "no garantizan resultados futuros. Los datos pueden estar "
            "retrasados, incompletos, no disponibles o ser inexactos. "
            "La aplicación se proporciona tal cual, sin garantía de "
            "exactitud, disponibilidad, rentabilidad o idoneidad para "
            "un propósito particular. El uso de esta aplicación es "
            "completamente bajo la responsabilidad del usuario."
        ),
    },
}



# ============================================================
# FILES
# ============================================================

FORWARD_FILE = Path(
    "state/forward_validation.csv"
)

FREEZE_FILE = Path(
    "state/forward_validation_freeze.txt"
)


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="MNQ Edge",
    layout="wide",
)

# ============================================================================
# LANGUAGE SELECTOR
# ============================================================================

if "language" not in st.session_state:
    st.session_state.language = "English"

language = st.session_state.language
T = TRANSLATIONS[language]



# ============================================================
# COMPACT CSS
# ============================================================

# TOPSTEP-LIKE DARK UI
# TRUE RED VISUAL FIX

st.markdown(
    """
    <style>

    :root {
        --mnq-bg: #0b1016;
        --mnq-panel: #111820;
        --mnq-panel-2: #151d26;
        --mnq-border: #28323d;
        --mnq-text: #f2f5f7;
        --mnq-muted: #9ba6b2;
        --mnq-green: #22c98b;
        --mnq-red: #ff2020;
        --mnq-yellow: #e7cf54;
        --mnq-blue: #72bfff;
        --mnq-vwap: #2eb5a7;
    }

    html,
    body,
    [data-testid="stAppViewContainer"],
    [data-testid="stApp"] {
        background: #0b1016 !important;
        color: #f2f5f7 !important;
    }

    /*
       Keep Streamlit's native top bar.
       Reserve its fixed overlay height so the MNQ header always starts below it.
       This is presentation-only and avoids relying on Streamlit's changing toolbar selectors.
    */
    [data-testid="stHeader"] {
        background: #0b1016 !important;
    }

    .block-container {
        padding-top: 0.20rem !important;
        padding-bottom: 0.20rem;
        padding-left: 0.65rem;
        padding-right: 0.65rem;
        max-width: 100%;
    }

    h1, h2, h3, p, span, label {
        color: #f2f5f7;
    }

    h1 {
        font-size: 1.55rem !important;
        margin-top: 0 !important;
        margin-bottom: 0.1rem !important;
    }

    h2, h3 {
        margin-top: 0.25rem !important;
        margin-bottom: 0.25rem !important;
    }

    div[data-testid="stMetric"] {
        padding: 0.05rem 0.15rem;
        background: transparent;
    }

    div[data-testid="stMetricLabel"] {
        font-size: 0.72rem;
        color: #9ba6b2 !important;
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.25rem;
        color: #f2f5f7 !important;
    }

    div[data-testid="stAlert"] {
        padding-top: 0.4rem;
        padding-bottom: 0.4rem;
        margin-top: 0.15rem;
        margin-bottom: 0.35rem;
        border-radius: 8px;
    }

    div[data-testid="stHorizontalBlock"] {
        gap: 0.45rem;
    }

    [data-testid="stExpander"] {
        background: #111820;
        border: 1px solid #28323d;
        border-radius: 8px;
    }

    [data-testid="stDataFrame"] {
        border: 1px solid #28323d;
        border-radius: 8px;
        overflow: hidden;
    }

    .mnq-metric-card {
        min-height: 58px;
        padding: 4px 5px;
        box-sizing: border-box;
    }

    .mnq-metric-label {
        color: #9ba6b2;
        font-size: 14px;
        line-height: 1.25;
        margin-bottom: 6px;
    }

    .mnq-metric-value {
        font-size: 23px;
        line-height: 1.15;
        font-weight: 400;
        white-space: nowrap;
        letter-spacing: -0.3px;
    }

    .mnq-neutral { color: #d7dde3; }
    .mnq-green { color: #22c98b; }
    .mnq-red { color: #ff2020; }
    .mnq-yellow { color: #e7cf54; }


    .mnq-top-safe-space {
        height: 10px;
        min-height: 10px;
        width: 100%;
        display: block;
        pointer-events: none;
    }

    .mnq-app-title {
        font-size: 20px;
        font-weight: 700;
        line-height: 1.15;
        padding-top: 5px;
        white-space: nowrap;
        color: #f2f5f7 !important;
    }

    .mnq-app-title span {
        display: block;
        margin-top: 4px;
        font-size: 11px;
        font-weight: 500;
        color: #9ba6b2 !important;
    }

    .mnq-status-strip {
        min-height: 30px;
        display: flex;
        align-items: center;
        gap: 18px;
        padding: 5px 10px;
        margin: 0 0 6px 0;
        border: 1px solid #28323d;
        border-radius: 7px;
        background: #111820;
        color: #cfd6dd;
        font-size: 11px;
        overflow: hidden;
    }

    .mnq-status-strip i {
        font-style: normal;
        font-weight: 700;
    }

    .mnq-status-message {
        margin-left: auto;
        color: #9ba6b2;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .mnq-rail-title {
        height: 24px;
        display: flex;
        align-items: center;
        padding: 0 4px;
        margin: 0 0 4px 0;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: .7px;
        color: #9ba6b2;
    }

    [data-testid="stPlotlyChart"] {
        border: 1px solid #28323d;
        border-radius: 8px;
        overflow: hidden;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


def render_colored_metric(
    label,
    value,
    color_class="mnq-neutral",
):
    st.markdown(
        (
            "<div class='mnq-metric-card'>"
            "<div class='mnq-metric-label'>"
            f"{label}"
            "</div>"
            "<div class='mnq-metric-value "
            f"{color_class}'>"
            f"{value}"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


# ============================================================
# INDICATORS
# ============================================================

def add_indicators(df):

    data = df.copy()

    data["ema9"] = (
        data["close"]
        .ewm(
            span=9,
            adjust=False,
        )
        .mean()
    )

    data["ema21"] = (
        data["close"]
        .ewm(
            span=21,
            adjust=False,
        )
        .mean()
    )

    data["ema200"] = (
        data["close"]
        .ewm(
            span=200,
            adjust=False,
        )
        .mean()
    )

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

    # MNQ-App ATR14 = simple rolling mean.
    data["atr14"] = (
        true_range
        .rolling(14)
        .mean()
    )

    chicago_time = (
        data["time"]
        .dt.tz_convert(
            "America/Chicago"
        )
    )

    normal_date = (
        chicago_time
        .dt.date
        .astype(str)
    )

    next_date = (
        chicago_time
        + pd.Timedelta(
            days=1
        )
    ).dt.date.astype(str)

    after_1700 = (
        chicago_time.dt.hour
        >= 17
    )

    data["session"] = np.where(
        after_1700,
        next_date,
        normal_date,
    )

    typical_price = (
        data["high"]
        + data["low"]
        + data["close"]
    ) / 3.0

    data["tp_volume"] = (
        typical_price
        * data["volume"]
    )

    data["cum_tp_volume"] = (
        data.groupby(
            "session"
        )["tp_volume"]
        .cumsum()
    )

    data["cum_volume"] = (
        data.groupby(
            "session"
        )["volume"]
        .cumsum()
    )

    data["vwap"] = (
        data["cum_tp_volume"]
        / data["cum_volume"]
    )

    data["vwap_plot"] = (
        data["vwap"]
    )

    new_session = (
        data["session"]
        != data["session"].shift(1)
    )

    data.loc[
        new_session,
        "vwap_plot",
    ] = np.nan

    return data


# ============================================================
# MARKET DATA
# ============================================================

@st.cache_data(ttl=20)
def load_market_data():

    token = get_token()

    contract = get_active_mnq_contract(
        token
    )

    contract_id = contract[
        "id"
    ]

    contract_name = contract[
        "name"
    ]

    # ========================================================
    # EXISTING LOCAL HISTORY FOR THIS EXACT CONTRACT
    # ========================================================

    existing = load_contract_history(
        contract_id=contract_id,
        contract_name=contract_name,
    )

    # ========================================================
    # BOOTSTRAP
    #
    # No local file/history yet:
    # obtain an initial 1500-bar window.
    # ========================================================

    if existing.empty:

        bars = get_mnq_5m_bars(
            token,
            contract_id=contract_id,
            days=10,
            limit=1500,
        )

    # ========================================================
    # INCREMENTAL
    #
    # Local history exists:
    # request ONLY bars strictly after the latest saved bar.
    # ========================================================

    else:

        last_saved = pd.Timestamp(
            existing.iloc[-1][
                "time"
            ]
        )

        bars = get_mnq_5m_bars_since(
            token=token,
            contract_id=contract_id,
            start_time=last_saved,
        )

    # ========================================================
    # API BARS -> DATAFRAME
    # ========================================================

    if bars:

        fresh = (
            pd.DataFrame(
                bars
            )
            .rename(
                columns={
                    "t": "time",
                    "o": "open",
                    "h": "high",
                    "l": "low",
                    "c": "close",
                    "v": "volume",
                }
            )
        )

        fresh["time"] = pd.to_datetime(
            fresh["time"],
            utc=True,
        )

        for column in [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]:

            fresh[column] = pd.to_numeric(
                fresh[column],
                errors="coerce",
            )

        fresh = (
            fresh
            .dropna(
                subset=[
                    "time",
                    "open",
                    "high",
                    "low",
                    "close",
                ]
            )
            .sort_values(
                "time"
            )
            .reset_index(
                drop=True
            )
        )

    else:

        fresh = pd.DataFrame(
            columns=[
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

    # ========================================================
    # SAME-CONTRACT PERSISTENCE
    # ========================================================

    data, history_file = persist_contract_history(
        contract=contract,
        fresh_df=fresh,
    )

    # ========================================================
    # AUTOMATIC SHORT-GAP REPAIR
    #
    # CLEAN:
    #   no repair API request is made.
    #
    # GAPS FOUND:
    #   request only the missing real 5m bars.
    #
    # Failed attempts respect a 15-minute cooldown.
    # No synthetic bars are ever created.
    # ========================================================

    repair_result = repair_contract_history(
        token=token,
        contract=contract,
        respect_cooldown=True,
        cooldown_minutes=15,
    )

    if repair_result[
        "repaired"
    ]:

        data = load_contract_history(
            contract_id=contract_id,
            contract_name=contract_name,
        )

    if data.empty:

        raise RuntimeError(
            "No MNQ history available for "
            f"{contract_name}."
        )

    return (
        add_indicators(
            data
        ),
        contract,
    )

# ============================================================
# LEVELS
# ============================================================

def get_current_levels(df):

    levels = detect_key_levels(
        df,
        lookback=min(
            500,
            len(df),
        ),
        pivot_left=3,
        pivot_right=3,
        tolerance_points=8.0,
        max_levels=8,
    )

    resistance = sorted(
        levels["resistance"],
        key=lambda x:
            x["distance"],
    )

    support = sorted(
        levels["support"],
        key=lambda x:
            x["distance"],
    )

    return (
        resistance,
        support,
    )


# ============================================================
# C1-C5 HELPERS
# ============================================================

def stage_reached(
    current_stage,
    target_stage,
):

    order = {
        "NO SETUP": 0,
        "C1 BREAKOUT": 1,
        "C2 CONFIRMED": 2,
        "C3 RETEST": 3,
        "C4 DEFENSE": 4,
        "C5 CONFIRMED": 5,
    }

    return (
        order.get(
            current_stage,
            0,
        )
        >=
        order.get(
            target_stage,
            0,
        )
    )


# C1-C5 MINUTE PROGRESS UI

def stage_active(
    current_stage,
    target_stage,
    setup_side,
):
    """
    Visual-only helper.

    The engine's current stage is the last confirmed stage.
    Therefore the next stage is the one currently waiting
    for evidence.

    This does NOT change C1-C5 trading logic.
    """

    if setup_side is None:

        return False


    next_stage = {
        "C1 BREAKOUT":
            "C2 CONFIRMED",

        "C2 CONFIRMED":
            "C3 RETEST",

        "C3 RETEST":
            "C4 DEFENSE",

        "C4 DEFENSE":
            "C5 CONFIRMED",
    }


    return (
        next_stage.get(
            current_stage
        )
        == target_stage
    )


def five_minute_progress(
    now_time=None,
):
    """
    Visual progress inside the currently forming 5m clock bar.

    Returns five percentages, one for each one-minute segment.

    Example at 2m30s:
        [100, 100, 50, 0, 0]

    No trading decision is made here.
    """

    if now_time is None:

        now_time = pd.Timestamp.now(
            tz="UTC"
        )


    now_time = pd.Timestamp(
        now_time
    )


    if now_time.tzinfo is None:

        now_time = (
            now_time
            .tz_localize(
                "UTC"
            )
        )

    else:

        now_time = (
            now_time
            .tz_convert(
                "UTC"
            )
        )


    bar_start = now_time.floor(
        "5min"
    )


    elapsed_seconds = float(
        (
            now_time
            - bar_start
        ).total_seconds()
    )


    elapsed_seconds = max(
        0.0,
        min(
            elapsed_seconds,
            300.0,
        ),
    )


    percentages = []


    for minute_index in range(5):

        segment_start = (
            minute_index
            * 60.0
        )

        segment_elapsed = (
            elapsed_seconds
            - segment_start
        )


        percentage = (
            segment_elapsed
            / 60.0
            * 100.0
        )


        percentage = max(
            0.0,
            min(
                percentage,
                100.0,
            ),
        )


        percentages.append(
            percentage
        )


    completed_minutes = min(
        int(
            elapsed_seconds
            // 60.0
        ),
        4,
    )


    return {
        "segments":
            percentages,

        "completed_minutes":
            completed_minutes,

        "elapsed_seconds":
            elapsed_seconds,

        "bar_start":
            bar_start,
    }


def setup_box(
    title,
    description,
    reached,
    timestamp=None,
    active=False,
    now_time=None,
):
    """
    Render one C1-C5 visual card.

    reached=True:
        Stage confirmed -> all five one-minute segments GREEN.

    active=True:
        Current stage -> each minute progresses from RED to GREEN
        using five_minute_progress().

    otherwise:
        Waiting stage -> all five segments RED.

    VISUAL ONLY. No C1-C5 trading logic is changed.
    """

    if reached:
        icon = "[OK]"
        status = "OK"
        border_color = "rgba(34, 201, 139, .85)"
        background = "rgba(34, 201, 139, .05)"
        status_color = "#22c98b"

    elif active:
        icon = "[>]"
        status = T["in_progress"]
        border_color = "rgba(34, 201, 139, .80)"
        background = "rgba(17, 24, 32, .88)"
        status_color = "#22c98b"

    else:
        icon = "[ ]"
        status = TRANSLATIONS[
            st.session_state.get("language", "English")
        ]["wait"]
        border_color = "rgba(105, 117, 130, .75)"
        background = "rgba(17, 24, 32, .88)"
        status_color = "rgba(155, 166, 178, .95)"

    if timestamp is not None:
        time_text = (
            "<div style='"
            "font-size:9px;"
            "color:#9ba6b2;"
            "opacity:.75;"
            "margin-top:3px;"
            "white-space:nowrap;"
            "overflow:hidden;"
            "text-overflow:ellipsis;'>"
            f"{timestamp}"
            "</div>"
        )
    else:
        time_text = ""

    if reached:
        segment_values = [100.0, 100.0, 100.0, 100.0, 100.0]
        minute_text = "5 / 5 min"

    elif active:
        progress = five_minute_progress(now_time=now_time)
        segment_values = progress["segments"]
        elapsed = progress["elapsed_seconds"]
        whole_minutes = min(int(elapsed // 60.0), 4)
        seconds_in_minute = int(elapsed % 60.0)
        minute_text = (
            f"{whole_minutes} / 5 min"
            f" &nbsp; {seconds_in_minute:02d}s"
        )

    else:
        segment_values = [0.0, 0.0, 0.0, 0.0, 0.0]
        minute_text = TRANSLATIONS[
            st.session_state.get("language", "English")
        ]["wait"]

    segment_html = ""

    for percentage in segment_values:
        percentage = max(0.0, min(float(percentage), 100.0))

        segment_html += (
            "<div style='"
            "position:relative;"
            "flex:1;"
            "height:10px;"
            "background:#ff2020;"
            "border:1px solid rgba(255,255,255,.10);"
            "border-radius:4px;"
            "overflow:hidden;"
            "box-sizing:border-box;'>"
            "<div style='"
            "position:absolute;"
            "left:0;"
            "top:0;"
            "bottom:0;"
            f"width:{percentage:.1f}%;"
            "background:#22c98b;"
            "transition:width .35s ease;"
            "'></div>"
            "</div>"
        )

    html = (
        "<div style='"
        f"border:1px solid {border_color};"
        "border-radius:8px;"
        "padding:7px 9px 6px 9px;"
        f"background:{background};"
        "min-height:88px;"
        "box-sizing:border-box;'>"
        "<div style='"
        "display:flex;"
        "align-items:center;"
        "justify-content:space-between;"
        "gap:6px;'>"
        "<div style='"
        "font-size:14px;"
        "font-weight:700;"
        "color:#f2f5f7;'>"
        f"{title}"
        "</div>"
        "<div style='"
        "font-size:10px;"
        "font-weight:700;"
        f"color:{status_color};"
        "white-space:nowrap;'>"
        f"{icon} {status}"
        "</div>"
        "</div>"
        "<div style='"
        "font-size:11px;"
        "color:#a7b0ba;"
        "margin-top:3px;"
        "margin-bottom:10px;'>"
        f"{description}"
        "</div>"
        "<div style='"
        "display:flex;"
        "gap:6px;"
        "width:100%;'>"
        f"{segment_html}"
        "</div>"
        "<div style='"
        "font-size:9px;"
        f"color:{status_color};"
        "opacity:.90;"
        "margin-top:6px;"
        "font-weight:600;'>"
        f"{minute_text}"
        "</div>"
        f"{time_text}"
        "</div>"
    )

    st.markdown(
        html,
        unsafe_allow_html=True,
    )


def load_forward_data():

    if not FORWARD_FILE.exists():

        return pd.DataFrame()

    try:

        data = pd.read_csv(
            FORWARD_FILE
        )

    except Exception:

        return pd.DataFrame()

    for column in [
        "c5_time",
        "created_at",
        "entry_time",
        "exit_time",
    ]:

        if column in data.columns:

            data[column] = pd.to_datetime(
                data[column],
                utc=True,
                errors="coerce",
            )

    for column in [
        "level",
        "atr14",
        "distance_points",
        "distance_atr",
        "ema9",
        "ema21",
        "ema200",
        "vwap",
        "entry_price",
        "stop_price",
        "target_price",
        "risk_points",
        "result_r",
    ]:

        if column in data.columns:

            data[column] = pd.to_numeric(
                data[column],
                errors="coerce",
            )

    for column in [
        "h1",
        "h2",
        "h3",
        "vwap_aligned",
    ]:

        if (
            column in data.columns
            and data[column].dtype == object
        ):

            data[column] = (
                data[column]
                .astype(str)
                .str.lower()
                .map(
                    {
                        "true": True,
                        "false": False,
                    }
                )
            )

    return data


def get_freeze_time():

    if not FREEZE_FILE.exists():

        return "-"

    try:

        text = FREEZE_FILE.read_text(
            encoding="utf-8"
        )

    except Exception:

        return "-"

    for line in text.splitlines():

        if line.startswith(
            "FROZEN AT UTC:"
        ):

            return (
                line
                .replace(
                    "FROZEN AT UTC:",
                    "",
                )
                .strip()
            )

    return "-"


def forward_stats(
    df,
    hypothesis,
):

    empty_result = {
        "setups": 0,
        "completed": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": None,
        "total_r": 0.0,
        "avg_r": None,
        "pf": None,
    }

    if (
        df.empty
        or hypothesis not in df.columns
    ):

        return empty_result

    selected = df[
        df[hypothesis] == True
    ].copy()

    if selected.empty:

        return empty_result

    result = (
        empty_result.copy()
    )

    result["setups"] = len(
        selected
    )

    if "result_r" not in selected.columns:

        return result

    completed = selected[
        selected["result_r"]
        .notna()
    ].copy()

    result["completed"] = len(
        completed
    )

    if completed.empty:

        return result

    winners = completed[
        completed["result_r"] > 0
    ]

    losers = completed[
        completed["result_r"] < 0
    ]

    result["wins"] = len(
        winners
    )

    result["losses"] = len(
        losers
    )

    result["win_rate"] = (
        len(winners)
        / len(completed)
        * 100
    )

    result["total_r"] = float(
        completed["result_r"]
        .sum()
    )

    result["avg_r"] = float(
        completed["result_r"]
        .mean()
    )

    gross_profit = float(
        winners["result_r"]
        .sum()
    )

    gross_loss = abs(
        float(
            losers["result_r"]
            .sum()
        )
    )

    if gross_loss > 0:

        result["pf"] = (
            gross_profit
            / gross_loss
        )

    elif gross_profit > 0:

        result["pf"] = float(
            "inf"
        )

    return result


def fmt(
    value,
    decimals=2,
):

    if value is None:

        return "-"

    if pd.isna(
        value
    ):

        return "-"

    if value == float(
        "inf"
    ):

        return "inf"

    return (
        f"{value:.{decimals}f}"
    )


# ============================================================
# LIVE AUTO-REFRESH
# ============================================================

@st.fragment(run_every="20s")
def render_live_app():
    # Resolve the active UI language before any translated text is rendered.
    language = st.session_state.get(
        "language_selector_header",
        st.session_state.get("language", "English"),
    )

    st.session_state.language = language
    T = TRANSLATIONS[language]


    # ============================================================
    # LOAD MARKET
    # ============================================================

    try:

        df, active_contract = load_market_data()

        history_status = classify_mnq_history(
            len(df)
        )

        local_history_status = (
            load_local_history_status(
                active_contract
            )
        )

        local_sync_status = (
            classify_local_history_sync(
                latest_market_bar=
                    df.iloc[-1]["time"],

                latest_local_bar=
                    local_history_status[
                        "last_bar"
                    ],
            )
        )

        current_market_state = (
            get_cme_market_state()
        )

        roll_status = (
            get_roll_status()
        )

        operational_gate = (
            evaluate_operational_gate(
                contract_name=
                    active_contract.get(
                        "name"
                    ),

                history_status=
                    history_status,

                local_sync_state=
                    local_sync_status[
                        "state"
                    ],

                integrity_state=
                    local_history_status[
                        "integrity_state"
                    ],

                roll_status=
                    roll_status,

                market_state=
                    current_market_state.get(
                        "state"
                    ),
            )
        )

    except Exception:

        st.error(
            "Market data is temporarily unavailable. "
            "Please try again shortly."
        )

        st.stop()


    if df.empty:

        st.error(
            "No MNQ market data received."
        )

        st.stop()


    if operational_gate["allowed"]:

        setup = evaluate_setup_public(
            df,
            contract_id=active_contract.get(
                "id"
            ),
            contract_name=active_contract.get(
                "name"
            ),
            as_of_time=pd.Timestamp.now(
                tz="UTC"
            ),
        )

    else:

        setup = {
            "active": False,
            "setup_id": None,
            "side": None,
            "stage": "NO SETUP",
            "level": None,
            "key_level": None,
            "c1_time": None,
            "c2_time": None,
            "c3_time": None,
            "c4_time": None,
            "c5_time": None,
            "terminal_time": None,
            "terminal_reason": None,
            "message":
                operational_gate[
                    "message"
                ],
        }

    resistance, support = (
        get_current_levels(
            df
        )
    )

    latest = df.iloc[
        -1
    ]


    history_bars = len(df)
    history_state = history_status["state"]
    history_color = "#22c98b" if history_status["ready"] else "#e7cf54"
    gate_color = "#22c98b" if operational_gate["allowed"] else "#ff2020"
    gate_text = "ENABLED" if operational_gate["allowed"] else "BLOCKED"

    st.markdown(
        (
            "<div class='mnq-status-strip'>"
            f"<span><b>History</b> <i style='color:{history_color}'>"
            f"{history_state}</i> · {history_bars} / 500 bars</span>"
            f"<span><b>Gate</b> <i style='color:{gate_color}'>"
            f"{gate_text}</i></span>"
            f"<span class='mnq-status-message'>{setup['message']}</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


    # ============================================================
    # SINGLE-SCREEN TRADING TERMINAL HEADER
    # Intentionally rendered BELOW the History/Gate strip so Streamlit
    # native toolbar cannot overlay it. Presentation-only.
    # ============================================================

    setup_side = setup["side"] if setup["side"] else "NONE"

    if setup_side == "LONG":
        direction_class = "mnq-green"
    elif setup_side == "SHORT":
        direction_class = "mnq-red"
    else:
        direction_class = "mnq-neutral"

    setup_stage = setup["stage"] if setup.get("stage") else "NO SETUP"

    # Display-only translations.
    # Internal strategy values remain unchanged.
    setup_stage_display = (
        T["no_setup"]
        if setup_stage == "NO SETUP"
        else setup_stage
    )

    setup_side_display = (
        T["none"]
        if setup_side in (None, "", "NONE")
        else setup_side
    )

    if setup_stage == "INVALIDATED":
        stage_class = "mnq-red"
    elif setup_stage == "C5 CONFIRMED":
        stage_class = "mnq-green"
    elif setup_stage == "NO SETUP":
        stage_class = "mnq-neutral"
    else:
        stage_class = "mnq-yellow"

    if setup["level"] is not None:
        level_value = f"{setup['level']:.2f}"
        if setup_side == "LONG":
            level_class = "mnq-green"
        elif setup_side == "SHORT":
            level_class = "mnq-red"
        else:
            level_class = "mnq-neutral"
    else:
        level_value = "-"
        level_class = "mnq-neutral"

    latest_close = float(latest["close"])
    latest_open = float(latest["open"])

    if latest_close > latest_open:
        last_class = "mnq-green"
    elif latest_close < latest_open:
        last_class = "mnq-red"
    else:
        last_class = "mnq-neutral"

    title_col, s1, s2, s3, s4, s5 = st.columns(
        [2.0, 1.15, 1.45, 1.15, 1.15, 1.25],
        gap="small",
    )

    with title_col:
        st.markdown(
            "<div class='mnq-app-title'>MNQ Edge"
            f"<span style='font-size:0.92rem; font-weight:500; color:#b7bec9 !important;'>"
            f"{T['app_subtitle']}</span>"
            f"<span style='color:#e7cf54 !important;'>{T['beta']}</span>"
            "<span>5m · "
            f"{active_contract.get('name') or '-'}"
            "</span></div>",
            unsafe_allow_html=True,
        )

    # Process the language selector BEFORE rendering translated
    # header metrics. It remains visually located in column s5.
    with s5:
        language = st.selectbox(
            "🌐",
            ["English", "Español"],
            index=0 if st.session_state.language == "English" else 1,
            key="language_selector_header",
            label_visibility="collapsed",
        )

        st.session_state.language = language
        T = TRANSLATIONS[language]

    with s1:
        render_colored_metric(
            T["direction"],
            setup_side_display,
            direction_class,
        )

    with s2:
        render_colored_metric(
            T["stage"],
            setup_stage_display,
            stage_class,
        )

    with s3:
        render_colored_metric(
            T["key_level"],
            level_value,
            level_class,
        )

    with s4:
        render_colored_metric(
            T["last"],
            f"{latest_close:.2f}",
            last_class,
        )

    with s5:
        components.html(
            """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    html, body {
                        margin:0;
                        padding:0;
                        overflow:hidden;
                        background:transparent;
                        font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
                    }
                    .clock-label {
                        font-size:12px;
                        line-height:1.15;
                        color:rgba(155,166,178,.95);
                        margin:0 0 2px 0;
                    }
                    #mnq-live-clock {
                        font-size:23px;
                        line-height:1.15;
                        font-weight:500;
                        letter-spacing:-.3px;
                        color:rgb(242,245,247);
                        white-space:nowrap;
                        margin:0;
                    }
                    .clock-zone {
                        font-size:9px;
                        line-height:1.1;
                        color:rgba(155,166,178,.75);
                        margin:2px 0 0 0;
                    }
                </style>
            </head>
            <body>
                <div class="clock-label">Clock</div>
                <div id="mnq-live-clock">--:--:--</div>
                <div class="clock-zone">ET</div>
                <script>
                    function updateMnqClock() {
                        const now = new Date();
                        const formatter = new Intl.DateTimeFormat(
                            "en-US",
                            {
                                timeZone:"America/New_York",
                                hour:"2-digit",
                                minute:"2-digit",
                                second:"2-digit",
                                hour12:true
                            }
                        );
                        document.getElementById("mnq-live-clock").textContent = formatter.format(now);
                    }
                    updateMnqClock();
                    setInterval(updateMnqClock, 1000);
                </script>
            </body>
            </html>
            """,
            height=65,
            scrolling=False,
        )


    if operational_gate["warnings"]:
        with st.expander(
            f"Operational warnings ({len(operational_gate['warnings'])})",
            expanded=False,
        ):
            for warning in operational_gate["warnings"]:
                st.warning(warning)


    # ============================================================
    # CHART
    # ============================================================

    display_df = (
        df.tail(420)
        .copy()
    )

    fig = go.Figure()


    fig.add_trace(
        go.Candlestick(
            x=display_df["time"],
            open=display_df["open"],
            high=display_df["high"],
            low=display_df["low"],
            close=display_df["close"],
            increasing_line_color="#22c98b",
            increasing_fillcolor="#22c98b",
            decreasing_line_color="#ff2020",
            decreasing_fillcolor="#ff2020",
            name="MNQ",
        )
    )


    fig.add_trace(
        go.Scatter(
            x=display_df["time"],
            y=display_df["ema9"],
            mode="lines",
            line=dict(color="#72bfff", width=1.4),
            name="EMA 9",
        )
    )


    fig.add_trace(
        go.Scatter(
            x=display_df["time"],
            y=display_df["ema21"],
            mode="lines",
            line=dict(color="#ff2020", width=1.4),
            name="EMA 21",
        )
    )


    fig.add_trace(
        go.Scatter(
            x=display_df["time"],
            y=display_df["ema200"],
            mode="lines",
            line=dict(color="#e7cf54", width=1.4),
            name="EMA 200",
        )
    )


    fig.add_trace(
        go.Scatter(
            x=display_df["time"],
            y=display_df["vwap_plot"],
            mode="lines",
            line=dict(color="#2eb5a7", width=1.5),
            name="VWAP",
            connectgaps=False,
        )
    )


    # ============================================================
    # LEVEL LINES
    # ============================================================

    for index, item in enumerate(
        resistance[:3],
        start=1,
    ):

        level = float(
            item["level"]
        )

        fig.add_hline(
            y=level,
            line_dash="dash",
            line_width=1,
            line_color="#ff2020",
            annotation_text=(
                f"R{index} {level:.2f}"
            ),
            annotation_position="top left",
        )


    for index, item in enumerate(
        support[:3],
        start=1,
    ):

        level = float(
            item["level"]
        )

        fig.add_hline(
            y=level,
            line_dash="dot",
            line_width=1,
            line_color="#22c98b",
            annotation_text=(
                f"S{index} {level:.2f}"
            ),
            annotation_position="bottom left",
        )


    if setup["level"] is not None:

        setup_line_color = (
            "#22c98b"
            if setup["side"] == "LONG"
            else "#ff2020"
        )

        fig.add_hline(
            y=float(
                setup["level"]
            ),
            line_width=2,
            line_color=setup_line_color,
            annotation_text=(
                "SETUP "
                f"{setup['level']:.2f}"
            ),
            annotation_position="top right",
        )


    # ============================================================
    # C1-C5 MARKERS
    # ============================================================

    marker_specs = [
        (
            "C1",
            setup["c1_time"],
        ),
        (
            "C2",
            setup["c2_time"],
        ),
        (
            "C3",
            setup["c3_time"],
        ),
        (
            "C4",
            setup["c4_time"],
        ),
        (
            "C5",
            setup["c5_time"],
        ),
    ]


    for label, timestamp in marker_specs:

        if timestamp is None:

            continue

        match = df[
            df["time"]
            == timestamp
        ]

        if match.empty:

            continue

        candle = match.iloc[
            0
        ]

        if setup["side"] == "LONG":

            marker_y = float(
                candle["low"]
            )

            position = (
                "bottom center"
            )

            symbol = (
                "triangle-up"
            )

        else:

            marker_y = float(
                candle["high"]
            )

            position = (
                "top center"
            )

            symbol = (
                "triangle-down"
            )

        fig.add_trace(
            go.Scatter(
                x=[
                    timestamp
                ],
                y=[
                    marker_y
                ],
                mode="markers+text",
                text=[
                    label
                ],
                textposition=position,
                marker=dict(
                    size=10,
                    symbol=symbol,
                ),
                name=label,
            )
        )


    fig.update_layout(
        height=575,
        paper_bgcolor="#0b1016",
        plot_bgcolor="#0b1016",
        font=dict(color="#d7dde3"),
        xaxis=dict(
            gridcolor="#202a35",
            zerolinecolor="#202a35",
            showgrid=True,
        ),
        yaxis=dict(
            gridcolor="#202a35",
            zerolinecolor="#202a35",
            showgrid=True,
        ),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(
            l=5,
            r=5,
            t=15,
            b=5,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1,
            font=dict(
                size=10,
            ),
        ),
    )

    fig = apply_market_rangebreaks(
        fig,
        display_df,
    )


    # ============================================================
    # MAIN SINGLE-SCREEN WORKSPACE
    # ============================================================

    chart_col, rail_col = st.columns(
        [7.35, 2.65],
        gap="small",
    )

    with chart_col:
        st.plotly_chart(
            fig,
            width="stretch",
        )

    stage = setup["stage"]
    c1_c5_ui_now = pd.Timestamp.now(tz="UTC")

    with rail_col:
        st.markdown(
            f"<div class='mnq-rail-title'>{T['setup_lifecycle']}</div>",
            unsafe_allow_html=True,
        )

        setup_box(
            "C1",
            T["breakout"],
            stage_reached(stage, "C1 BREAKOUT"),
            setup["c1_time"],
            active=stage_active(stage, "C1 BREAKOUT", setup["side"]),
            now_time=c1_c5_ui_now,
        )

        setup_box(
            "C2",
            T["acceptance"],
            stage_reached(stage, "C2 CONFIRMED"),
            setup["c2_time"],
            active=stage_active(stage, "C2 CONFIRMED", setup["side"]),
            now_time=c1_c5_ui_now,
        )

        setup_box(
            "C3",
            T["retest"],
            stage_reached(stage, "C3 RETEST"),
            setup["c3_time"],
            active=stage_active(stage, "C3 RETEST", setup["side"]),
            now_time=c1_c5_ui_now,
        )

        setup_box(
            "C4",
            T["defense"],
            stage_reached(stage, "C4 DEFENSE"),
            setup["c4_time"],
            active=stage_active(stage, "C4 DEFENSE", setup["side"]),
            now_time=c1_c5_ui_now,
        )

        setup_box(
            "C5",
            T["confirmation"],
            stage_reached(stage, "C5 CONFIRMED"),
            setup["c5_time"],
            active=stage_active(stage, "C5 CONFIRMED", setup["side"]),
            now_time=c1_c5_ui_now,
        )

    # ============================================================
    # SECONDARY MARKET DETAILS
    # Kept available without occupying the primary trading screen.
    # ============================================================

    with st.expander(
        T["market_details"],
        expanded=False,
    ):
        level_cols = st.columns(6)

        for index in range(3):
            with level_cols[index]:
                if index < len(resistance):
                    item = resistance[index]
                    level = float(item["level"])
                    st.metric(
                        f"R{index + 1}",
                        f"{level:.2f}",
                        f"{item['touches']} touches",
                    )
                else:
                    st.metric(f"R{index + 1}", "-")

        for index in range(3):
            with level_cols[index + 3]:
                if index < len(support):
                    item = support[index]
                    level = float(item["level"])
                    st.metric(
                        f"S{index + 1}",
                        f"{level:.2f}",
                        f"{item['touches']} touches",
                    )
                else:
                    st.metric(f"S{index + 1}", "-")

        indicator_cols = st.columns(6)
        indicator_values = [
            (T["last"], latest["close"]),
            ("EMA 9", latest["ema9"]),
            ("EMA 21", latest["ema21"]),
            ("EMA 200", latest["ema200"]),
            ("VWAP", latest["vwap"]),
            ("ATR 14", latest["atr14"]),
        ]

        for column, item in zip(indicator_cols, indicator_values):
            label, value = item
            with column:
                st.metric(label, f"{float(value):.2f}")

        st.caption(
            f"{len(df):,} bars | Last closed bar: {latest['time']}"
        )


    # ============================================================
    # FORWARD VALIDATION
    # ============================================================

    forward_df = (
        load_forward_data()
    )

    freeze_time = (
        get_freeze_time()
    )


    with st.expander(
        T["how_to_use"],
        expanded=False,
    ):
        st.markdown(
            T["how_to_use_body"]
        )

    with st.expander(
        T["forward_validation"],
        expanded=False,
    ):

        st.caption(
            f"{T['frozen_from']}: {freeze_time}"
        )

        if forward_df.empty:

            logged = 0
            completed_count = 0
            open_count = 0
            no_fill_count = 0
            risk_reject_count = 0
            overlap_count = 0

        else:

            logged = len(
                forward_df
            )

            completed_count = int(
                forward_df[
                    "result_r"
                ]
                .notna()
                .sum()
            )

            exit_status = (
                forward_df[
                    "exit_status"
                ]
                .fillna("")
                .astype(str)
            )

            entry_status = (
                forward_df[
                    "entry_status"
                ]
                .fillna("")
                .astype(str)
            )

            open_count = int(
                (
                    exit_status
                    == "OPEN"
                ).sum()
            )

            no_fill_count = int(
                (
                    entry_status
                    == "NO_FILL"
                ).sum()
            )

            risk_reject_count = int(
                (
                    entry_status
                    == "RISK_REJECT"
                ).sum()
            )

            overlap_count = int(
                (
                    entry_status
                    == "SKIP_OVERLAP"
                ).sum()
            )


        f1, f2, f3, f4, f5, f6 = (
            st.columns(6)
        )

        f1.metric(
            T["logged_c5"],
            logged,
        )

        f2.metric(
            T["completed"],
            completed_count,
        )

        f3.metric(
            T["open_display"],
            open_count,
        )

        f4.metric(
            T["no_fill"],
            no_fill_count,
        )

        f5.metric(
            T["risk_gt_30"],
            risk_reject_count,
        )

        f6.metric(
            T["overlap"],
            overlap_count,
        )


        h1 = forward_stats(
            forward_df,
            "h1",
        )

        h2 = forward_stats(
            forward_df,
            "h2",
        )

        h3 = forward_stats(
            forward_df,
            "h3",
        )


        hypothesis_table = pd.DataFrame(
            [
                {
                    T["hypothesis"]:
                        T["h1_label"],

                    T["setups"]:
                        h1["setups"],

                    T["completed"]:
                        h1["completed"],

                    T["wins"]:
                        h1["wins"],

                    T["losses"]:
                        h1["losses"],

                    T["win_pct"]:
                        (
                            "-"
                            if h1["win_rate"]
                            is None
                            else
                            f"{h1['win_rate']:.2f}%"
                        ),

                    T["total_r"]:
                        fmt(
                            h1["total_r"],
                            3,
                        ),

                    T["avg_r"]:
                        fmt(
                            h1["avg_r"],
                            3,
                        ),

                    "PF":
                        fmt(
                            h1["pf"],
                            3,
                        ),
                },

                {
                    T["hypothesis"]:
                        T["h2_label"],

                    T["setups"]:
                        h2["setups"],

                    T["completed"]:
                        h2["completed"],

                    T["wins"]:
                        h2["wins"],

                    T["losses"]:
                        h2["losses"],

                    T["win_pct"]:
                        (
                            "-"
                            if h2["win_rate"]
                            is None
                            else
                            f"{h2['win_rate']:.2f}%"
                        ),

                    T["total_r"]:
                        fmt(
                            h2["total_r"],
                            3,
                        ),

                    T["avg_r"]:
                        fmt(
                            h2["avg_r"],
                            3,
                        ),

                    "PF":
                        fmt(
                            h2["pf"],
                            3,
                        ),
                },

                {
                    T["hypothesis"]:
                        T["h3_label"],

                    T["setups"]:
                        h3["setups"],

                    T["completed"]:
                        h3["completed"],

                    T["wins"]:
                        h3["wins"],

                    T["losses"]:
                        h3["losses"],

                    T["win_pct"]:
                        (
                            "-"
                            if h3["win_rate"]
                            is None
                            else
                            f"{h3['win_rate']:.2f}%"
                        ),

                    T["total_r"]:
                        fmt(
                            h3["total_r"],
                            3,
                        ),

                    T["avg_r"]:
                        fmt(
                            h3["avg_r"],
                            3,
                        ),

                    "PF":
                        fmt(
                            h3["pf"],
                            3,
                        ),
                },
            ]
        )


        st.dataframe(
            hypothesis_table,
            width="stretch",
            hide_index=True,
        )


        # ========================================================
        # FORWARD EQUITY
        # ========================================================

        if (
            not forward_df.empty
            and
            "result_r"
            in forward_df.columns
            and
            forward_df[
                "result_r"
            ].notna().any()
        ):

            completed = (
                forward_df[
                    forward_df[
                        "result_r"
                    ].notna()
                ]
                .copy()
                .sort_values(
                    "exit_time"
                )
            )

            completed[
                "Cumulative R"
            ] = (
                completed[
                    "result_r"
                ]
                .cumsum()
            )

            equity = (
                completed[
                    [
                        "exit_time",
                        "Cumulative R",
                    ]
                ]
                .dropna(
                    subset=[
                        "exit_time"
                    ]
                )
                .set_index(
                    "exit_time"
                )
            )

            if not equity.empty:

                st.line_chart(
                    equity,
                    height=220,
                )


        # ========================================================
        # RECENT FORWARD SETUPS
        # ========================================================

        if forward_df.empty:

            st.info(
                "No C5 setups logged "
                "after the freeze yet."
            )

        else:

            st.markdown(
                f"**{T['recent_forward_setups']}**"
            )

            display_columns = [
                "c5_time",
                "side",
                "session",
                "level",
                "distance_atr",
                "vwap_aligned",
                "h1",
                "h2",
                "h3",
                "entry_status",
                "entry_price",
                "risk_points",
                "exit_status",
                "result_r",
            ]

            available = [
                column
                for column
                in display_columns
                if column
                in forward_df.columns
            ]

            display_forward = (
                forward_df[
                    available
                ]
                .copy()
            )

            if (
                "c5_time"
                in display_forward.columns
            ):

                display_forward = (
                    display_forward
                    .sort_values(
                        "c5_time",
                        ascending=False,
                    )
                )

            st.dataframe(
                display_forward,
                width="stretch",
                hide_index=True,
                height=270,
            )




    # ============================================================
    # BETA / RISK DISCLAIMER
    # ============================================================

    with st.expander(
        T["disclaimer_title"],
        expanded=False,
    ):
        st.markdown(
            T["disclaimer_body"]
        )

    # ============================================================
    # SYSTEM STATUS
    # ============================================================

    render_recent_setups(
        limit=15,
    )
    render_system_status(
        latest_bar_time=latest[
            "time"
        ],
        contract_info=active_contract,
    )


# ============================================================
# START LIVE APP
# ============================================================

# Permanent top safe-area OUTSIDE the Streamlit fragment.
# This moves the fragment mount point below Streamlit's native toolbar.
st.markdown(
    "<div class='mnq-top-safe-space'></div>",
    unsafe_allow_html=True,
)

render_live_app()

