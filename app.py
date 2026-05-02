# =============================================================================
# MODUL 4: MACRO RISK DASHBOARD
# Körs med:  streamlit run app.py
# =============================================================================

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go

# =============================================================================
# SIDKONFIGURATION
# =============================================================================
st.set_page_config(
    page_title="Macro Risk Dashboard",
    page_icon="📊",
    layout="wide",
)

# =============================================================================
# DATA-LADDNING (cachad)
# =============================================================================
@st.cache_data
def load_data(path: str = "macro_scored_data.csv") -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["Date"]).set_index("Date").sort_index()
    return df

try:
    df = load_data()
except FileNotFoundError:
    st.error("❌ Hittar inte `macro_scored_data.csv`. Lägg filen i samma mapp som `app.py`.")
    st.stop()

# =============================================================================
# SIDEBAR
# =============================================================================
st.sidebar.title("📊 Macro Risk Dashboard")
st.sidebar.markdown(
    """
    Dagligt beslutstöd byggt på 5 makro-signaler:
    HY-spread, Jobless Claims, DXY, Copper/Gold, USD/JPY.

    Varje signal Z-scoras (6M rullande), harmoniseras
    så att **negativt = risk-off**, och summeras till en
    **Total Macro Score**.
    """
)
st.sidebar.markdown("---")

threshold = st.sidebar.slider(
    "Varnings-tröskel (Total Macro Score)",
    min_value=-5.0,
    max_value=0.0,
    value=-1.1,
    step=0.1,
    help="Walk-forward-optimerat värde har stabiliserat sig kring -1.1.",
)

st.sidebar.markdown("---")
st.sidebar.caption(f"Datapunkter i databas: **{len(df):,}**")
st.sidebar.caption(f"Period: **{df.index.min().date()} → {df.index.max().date()}**")

# =============================================================================
# 1. TOPP-SEKTION: CURRENT STATUS
# =============================================================================
latest = df.iloc[-1]
latest_date = df.index[-1]
current_score = latest["Total_Macro_Score"]
prev_score = df["Total_Macro_Score"].iloc[-2]
delta = current_score - prev_score

st.title("Current Status")

col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    st.metric(
        label="Senaste datapunkt",
        value=latest_date.strftime("%Y-%m-%d"),
        delta=f"{(df.index[-1] - df.index[-2]).days} dag(ar) sedan föregående",
        delta_color="off",
    )

with col2:
    st.metric(
        label="Total Macro Score",
        value=f"{current_score:+.2f}",
        delta=f"{delta:+.2f} dagsförändring",
        delta_color="normal",
    )

with col3:
    if current_score >= threshold:
        st.markdown(
            f"""
            <div style="
                background-color: #1f7a3a;
                padding: 1.5rem;
                border-radius: 0.5rem;
                text-align: center;
                color: white;
                font-size: 1.5rem;
                font-weight: bold;
                margin-top: 0.5rem;
            ">
                ✅ RISK-ON (Normal marknad)<br>
                <span style="font-size: 0.9rem; font-weight: normal;">
                    Score {current_score:+.2f} ≥ tröskel {threshold:+.2f}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div style="
                background-color: #b22222;
                padding: 1.5rem;
                border-radius: 0.5rem;
                text-align: center;
                color: white;
                font-size: 1.5rem;
                font-weight: bold;
                margin-top: 0.5rem;
            ">
                ⚠️ RISK-OFF (Varning!)<br>
                <span style="font-size: 0.9rem; font-weight: normal;">
                    Score {current_score:+.2f} &lt; tröskel {threshold:+.2f}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("---")

# =============================================================================
# 2. MITTEN-SEKTION: DRIVKRAFTER (sub-scores)
# =============================================================================
st.subheader("Drivkrafter just nu")
st.caption(
    "Vilka signaler drar ner respektive lyfter scoren? "
    "Negativa staplar = bidrar till risk-off."
)

score_cols = ["Score_HY", "Score_Jobs", "Score_DXY", "Score_CuAu", "Score_JPY"]
score_labels = {
    "Score_HY":   "HY Credit Spread",
    "Score_Jobs": "Jobless Claims",
    "Score_DXY":  "Dollar Index (DXY)",
    "Score_CuAu": "Copper / Gold",
    "Score_JPY":  "USD/JPY (asym.)",
}

driver_values = latest[score_cols]
driver_df = pd.DataFrame({
    "Signal": [score_labels[c] for c in score_cols],
    "Score":  driver_values.values,
}).sort_values("Score")  # Mest negativ överst i en horisontell bar chart

bar_colors = ["#b22222" if v < 0 else "#1f7a3a" for v in driver_df["Score"]]

fig_drivers = go.Figure(
    go.Bar(
        x=driver_df["Score"],
        y=driver_df["Signal"],
        orientation="h",
        marker_color=bar_colors,
        text=[f"{v:+.2f}" for v in driver_df["Score"]],
        textposition="outside",
        cliponaxis=False,
    )
)
fig_drivers.update_layout(
    height=320,
    margin=dict(l=10, r=40, t=10, b=10),
    xaxis_title="Z-score-bidrag",
    yaxis_title=None,
    plot_bgcolor="rgba(0,0,0,0)",
    showlegend=False,
)
fig_drivers.add_vline(x=0, line_color="gray", line_width=1)

st.plotly_chart(fig_drivers, use_container_width=True)

# Liten tabell under för exakta siffror
with st.expander("Visa exakta värden"):
    detail_df = pd.DataFrame({
        "Signal":   [score_labels[c] for c in score_cols],
        "Sub-score": [f"{latest[c]:+.3f}" for c in score_cols],
    })
    st.dataframe(detail_df, hide_index=True, use_container_width=True)

st.markdown("---")

# =============================================================================
# 3. BOTTEN-SEKTION: HISTORISK KONTEXT (5 år)
# =============================================================================
st.subheader("Historisk kontext — Total Macro Score (senaste 5 åren)")

cutoff = latest_date - pd.DateOffset(years=5)
hist = df.loc[df.index >= cutoff, "Total_Macro_Score"]

fig_hist = go.Figure()

# Total Macro Score
fig_hist.add_trace(
    go.Scatter(
        x=hist.index,
        y=hist.values,
        mode="lines",
        name="Total Macro Score",
        line=dict(color="#1f4e79", width=1.6),
        hovertemplate="%{x|%Y-%m-%d}<br>Score: %{y:+.2f}<extra></extra>",
    )
)

# Fyll under tröskeln med svag röd
risk_off = hist.where(hist < threshold)
fig_hist.add_trace(
    go.Scatter(
        x=hist.index,
        y=risk_off.values,
        mode="lines",
        line=dict(color="rgba(178,34,34,0.0)", width=0),
        fill="tozeroy",
        fillcolor="rgba(178,34,34,0.15)",
        name="Risk-off-zon",
        hoverinfo="skip",
        showlegend=False,
    )
)

# Nollinje
fig_hist.add_hline(y=0, line_color="gray", line_width=1)

# Tröskellinje
fig_hist.add_hline(
    y=threshold,
    line_color="red",
    line_width=1.5,
    line_dash="dash",
    annotation_text=f"Tröskel {threshold:+.2f}",
    annotation_position="top right",
    annotation_font_color="red",
)

# Markera var senaste datapunkt ligger
fig_hist.add_trace(
    go.Scatter(
        x=[latest_date],
        y=[current_score],
        mode="markers",
        marker=dict(
            size=12,
            color="#b22222" if current_score < threshold else "#1f7a3a",
            line=dict(color="white", width=2),
        ),
        name="Idag",
        hovertemplate="Idag<br>%{x|%Y-%m-%d}<br>Score: %{y:+.2f}<extra></extra>",
    )
)

fig_hist.update_layout(
    height=420,
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis_title=None,
    yaxis_title="Total Macro Score",
    plot_bgcolor="rgba(0,0,0,0)",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)

st.plotly_chart(fig_hist, use_container_width=True)

# =============================================================================
# FOOTER
# =============================================================================
st.markdown("---")
st.caption(
    "Tröskel justeras i sidopanelen. Walk-forward-optimerat värde är ca **-1.1**. "
    "Vid score under tröskeln: var i cash dagen efter signal."
)
