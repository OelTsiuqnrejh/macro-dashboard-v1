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

@st.cache_data
def load_data(path: str = "macro_scored_data.csv") -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["Date"]).set_index("Date").sort_index()
    return df

try:
    df = load_data()
except FileNotFoundError:
    st.error("❌ Hittar inte `macro_scored_data.csv`. Se till att filen finns i din GitHub-mapp.")
    st.stop()

# =============================================================================
# HÅRDKODADE REGLER (Disciplinerad modell)
# =============================================================================
THRESH_LOWER = -1.1  # Risk-Off gräns (Walk-Forward optimerad)
THRESH_UPPER = 0.0   # Risk-On gräns

st.sidebar.title("📊 Macro Risk Dashboard")
st.sidebar.markdown(
    """
    **Strikt Beslutsstöd**
    Byggt på 5 makro-signaler: HY-spread, Jobless Claims, DXY, Copper/Gold, USD/JPY.
    
    *Tröskelvärdena är låsta baserat på historiskt Walk-Forward backtest för maximal disciplin.*
    """
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
    st.metric(label="Senaste datapunkt", value=latest_date.strftime("%Y-%m-%d"), delta=f"{(df.index[-1] - df.index[-2]).days} dag(ar) sedan föregående", delta_color="off")
with col2:
    st.metric(label="Total Macro Score", value=f"{current_score:+.2f}", delta=f"{delta:+.2f} dagsförändring", delta_color="normal")

with col3:
    if current_score >= THRESH_UPPER:
        color, text, subtext = "#1f7a3a", "✅ RISK-ON", f"Normal marknad (Score ≥ {THRESH_UPPER})"
    elif current_score < THRESH_LOWER:
        color, text, subtext = "#b22222", "⚠️ RISK-OFF", f"Varning! (Score < {THRESH_LOWER})"
    else:
        color, text, subtext = "#d4a017", "⚖️ NEUTRAL", f"Övergångszon"

    st.markdown(
        f"""<div style="background-color: {color}; padding: 1.5rem; border-radius: 0.5rem; text-align: center; color: white; font-size: 1.5rem; font-weight: bold; margin-top: 0.5rem;">
            {text}<br><span style="font-size: 0.9rem; font-weight: normal;">{subtext}</span></div>""",
        unsafe_allow_html=True,
    )

st.markdown("---")

# =============================================================================
# 2. MITTEN-SEKTION: DRIVKRAFTER (sub-scores)
# =============================================================================
st.subheader("Drivkrafter just nu")
score_cols = ["Score_HY", "Score_Jobs", "Score_DXY", "Score_CuAu", "Score_JPY"]
score_labels = {"Score_HY": "HY Credit Spread", "Score_Jobs": "Jobless Claims", "Score_DXY": "Dollar Index (DXY)", "Score_CuAu": "Copper / Gold", "Score_JPY": "USD/JPY (asym.)"}

driver_df = pd.DataFrame({"Signal": [score_labels[c] for c in score_cols], "Score": latest[score_cols].values}).sort_values("Score")
bar_colors = ["#b22222" if v < 0 else "#1f7a3a" for v in driver_df["Score"]]

fig_drivers = go.Figure(go.Bar(x=driver_df["Score"], y=driver_df["Signal"], orientation="h", marker_color=bar_colors, text=[f"{v:+.2f}" for v in driver_df["Score"]], textposition="outside", cliponaxis=False))
fig_drivers.update_layout(height=320, margin=dict(l=10, r=40, t=10, b=10), plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
fig_drivers.add_vline(x=0, line_color="gray", line_width=1)

st.plotly_chart(fig_drivers, use_container_width=True)

# =============================================================================
# 3. BOTTEN-SEKTION: HISTORISK KONTEXT (HELA PERIODEN)
# =============================================================================
st.subheader("Historisk kontext — Total Macro Score (Hela historiken)")

hist = df["Total_Macro_Score"] # Ändrad till att visa hela databasen
y_min, y_max = min(hist.min() - 1, -6), max(hist.max() + 1, 4)

fig_hist = go.Figure()
fig_hist.add_hrect(y0=y_min, y1=THRESH_LOWER, fillcolor="red", opacity=0.1, layer="below", line_width=0)
fig_hist.add_hrect(y0=THRESH_LOWER, y1=THRESH_UPPER, fillcolor="orange", opacity=0.1, layer="below", line_width=0)
fig_hist.add_hrect(y0=THRESH_UPPER, y1=y_max, fillcolor="green", opacity=0.05, layer="below", line_width=0)

fig_hist.add_hline(y=THRESH_LOWER, line_color="red", line_width=1.5, line_dash="dash")
fig_hist.add_hline(y=THRESH_UPPER, line_color="green", line_width=1.5, line_dash="dash")
fig_hist.add_hline(y=0, line_color="gray", line_width=1)

fig_hist.add_trace(go.Scatter(x=hist.index, y=hist.values, mode="lines", line=dict(color="#1f4e79", width=1.2), hovertemplate="%{x|%Y-%m-%d}<br>Score: %{y:+.2f}<extra></extra>"))
fig_hist.add_trace(go.Scatter(x=[latest_date], y=[current_score], mode="markers", marker=dict(size=14, color=color, line=dict(color="white", width=2))))

fig_hist.update_layout(height=500, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified", showlegend=False, yaxis=dict(range=[y_min, y_max]))
st.plotly_chart(fig_hist, use_container_width=True)

# =============================================================================
# NY SEKTION: MAKRO-REGIM KARTAN (2D Matrix med Momentum)
# =============================================================================
st.markdown("---")
st.subheader("Makro-Regim: Var är vi och vart är vi på väg?")
st.caption("Visar dagens position jämfört med för 3 månader (60 handelsdagar) sedan. Pilen indikerar riktning.")

# 1. Skapa Axlarna (Y = Tillväxt, X = Likviditet/Stress)
df["Growth_Axis"] = df["Score_CuAu"] + df["Score_Jobs"]
df["Liquidity_Axis"] = df["Score_HY"] + df["Score_DXY"] + df["Score_JPY"]

# 2. Ta fram data för "Idag" och "För 3 månader sedan" (ca 60 dagar)
LOOKBACK_DAYS = 60
today_data = df.iloc[-1]
past_data = df.iloc[-(LOOKBACK_DAYS + 1)] if len(df) > LOOKBACK_DAYS else df.iloc[0]

today_date_str = df.index[-1].strftime("%Y-%m-%d")
past_date_str = df.index[-(LOOKBACK_DAYS + 1)].strftime("%Y-%m-%d") if len(df) > LOOKBACK_DAYS else df.index[0].strftime("%Y-%m-%d")

# 3. Bygg Plotly-grafen
fig_regime = go.Figure()

# Lägg till rutorna (kvadranterna) med svag färg för tydlighet
fig_regime.add_hrect(y0=0, y1=5, fillcolor="green", opacity=0.05, layer="below")  # Övre halvan
fig_regime.add_hrect(y0=-5, y1=0, fillcolor="red", opacity=0.05, layer="below")   # Undre halvan

# Plotta punkten för "För 3 månader sedan"
fig_regime.add_trace(go.Scatter(
    x=[past_data["Liquidity_Axis"]], y=[past_data["Growth_Axis"]],
    mode="markers+text",
    marker=dict(size=10, color="gray"),
    text=[f"Då ({past_date_str})"], textposition="bottom center",
    name="Tidigare Regim", hoverinfo="skip"
))

# Plotta punkten för "Idag"
fig_regime.add_trace(go.Scatter(
    x=[today_data["Liquidity_Axis"]], y=[today_data["Growth_Axis"]],
    mode="markers+text",
    marker=dict(size=16, color="#1f4e79", line=dict(width=2, color="white")),
    text=[f"Idag ({today_date_str})"], textposition="top center",
    name="Nuvarande Regim"
))

# Rita Pilen (Momentum)
fig_regime.add_annotation(
    x=today_data["Liquidity_Axis"], y=today_data["Growth_Axis"],
    ax=past_data["Liquidity_Axis"], ay=past_data["Growth_Axis"],
    xref="x", yref="y", axref="x", ayref="y",
    showarrow=True, arrowhead=3, arrowsize=1.5, arrowwidth=2, arrowcolor="#1f4e79"
)

# Fixa Linjerna för X=0 och Y=0
fig_regime.add_hline(y=0, line_dash="dash", line_color="black", line_width=1)
fig_regime.add_vline(x=0, line_dash="dash", line_color="black", line_width=1)

# Text i hörnen (Regim-beskrivningar)
fig_regime.add_annotation(x=3, y=3, text="<b>GULDLOCK</b><br>Hög Tillväxt / God Likviditet", showarrow=False, font=dict(color="green"))
fig_regime.add_annotation(x=-3, y=3, text="<b>ÖVERHETTNING</b><br>Hög Tillväxt / Finansiell Stress", showarrow=False, font=dict(color="orange"))
fig_regime.add_annotation(x=-3, y=-3, text="<b>PANIK / KONTRAKTION</b><br>Låg Tillväxt / Finansiell Stress", showarrow=False, font=dict(color="red"))
fig_regime.add_annotation(x=3, y=-3, text="<b>ÅTERHÄMTNING / STIMULANS</b><br>Låg Tillväxt / God Likviditet", showarrow=False, font=dict(color="blue"))

# Uppdatera layouten så den blir kvadratisk och snygg
max_range = max(abs(df["Liquidity_Axis"]).max(), abs(df["Growth_Axis"]).max()) + 1

fig_regime.update_layout(
    xaxis=dict(title="Likviditet & Finansiell Hälsa (X)", range=[-max_range, max_range], zeroline=False),
    yaxis=dict(title="Makroekonomisk Tillväxt (Y)", range=[-max_range, max_range], zeroline=False),
    height=600, width=800,
    showlegend=False,
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=20, r=20, t=20, b=20)
)

st.plotly_chart(fig_regime, use_container_width=True)
