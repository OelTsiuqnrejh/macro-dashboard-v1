import pandas as pd
import numpy as np
import yfinance as yf
from fredapi import Fred
from datetime import datetime
import os
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# KONFIGURATION & SÄKERHET
# =============================================================================
# Hämtar API-nyckeln från GitHub Secrets (dolt kassaskåp)
FRED_API_KEY = os.environ.get("FRED_API_KEY")

if not FRED_API_KEY:
    raise ValueError("❌ HITTAR INGEN FRED API-NYCKEL! Lägg till den i GitHub Secrets.")

START_DATE = "2000-01-01"
END_DATE = datetime.today().strftime("%Y-%m-%d")

FRED_TICKERS = {
    "HY_Spread":      "BAA10Y",   # Moody's Baa - 10Y Treasury
    "Jobless_Claims": "ICSA",     # Initial Jobless Claims
}

YF_TICKERS = {
    "USDJPY": "JPY=X",
    "DXY":    "DX-Y.NYB",
    "Copper": "HG=F",
    "Gold":   "GC=F",
}

TRADING_DAY_LAG = {"HY_Spread": 1, "Jobless_Claims": 0}
ROLLING_WINDOW = 126  # ~6 månader handelsdagar
OUTPUT_FILE = "macro_scored_data.csv"

# =============================================================================
# DEL 1: DATAPIPELINE (Modul 1)
# =============================================================================
def normalize_index(idx):
    idx = pd.to_datetime(idx)
    if hasattr(idx, "tz") and idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()

def fetch_fred_series(api_key, tickers, start, end):
    fred = Fred(api_key=api_key)
    series_dict = {}
    for name, ticker in tickers.items():
        s = fred.get_series(ticker, observation_start=start, observation_end=end)
        s = s.dropna()
        s.index = normalize_index(s.index)
        s.name = name
        series_dict[name] = s
    return series_dict

def fetch_yahoo_data(tickers, start, end):
    df = pd.DataFrame()
    for name, ticker in tickers.items():
        data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"].iloc[:, 0]
        else:
            close = data["Close"]
        df[name] = close
    df.index = normalize_index(df.index)
    return df

def get_macro_data():
    fred_series = fetch_fred_series(FRED_API_KEY, FRED_TICKERS, START_DATE, END_DATE)
    yahoo_df = fetch_yahoo_data(YF_TICKERS, START_DATE, END_DATE)
    
    trading_days = pd.DatetimeIndex(yahoo_df.dropna(how="all").index.unique().sort_values())
    
    all_indices = [trading_days] + [s.index for s in fred_series.values()]
    combined_index = all_indices[0]
    for idx in all_indices[1:]:
        combined_index = combined_index.union(idx)
    combined_index = pd.DatetimeIndex(combined_index.unique().sort_values())

    aligned = pd.DataFrame(index=combined_index)
    for name, s in fred_series.items():
        s_dedup = s[~s.index.duplicated(keep="last")]
        aligned[name] = s_dedup.reindex(combined_index).ffill()
    
    yahoo_dedup = yahoo_df[~yahoo_df.index.duplicated(keep="last")]
    for col in yahoo_dedup.columns:
        aligned[col] = yahoo_dedup[col].reindex(combined_index).ffill()

    df_final = aligned.reindex(trading_days)

    for col, lag in TRADING_DAY_LAG.items():
        if col in df_final.columns and lag > 0:
            df_final[col] = df_final[col].shift(lag)

    df_final["Copper_Gold_Ratio"] = df_final["Copper"] / df_final["Gold"]
    df_final = df_final.dropna(how="any")
    
    return df_final[["HY_Spread", "Jobless_Claims", "USDJPY", "DXY", "Copper", "Gold", "Copper_Gold_Ratio"]]

# =============================================================================
# DEL 2: Z-SCORE MOTORN (Modul 2)
# =============================================================================
def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std()
    std_safe = std.replace(0, np.nan)
    z = (series - mean) / std_safe
    return z.fillna(0).where(mean.notna())

def apply_scoring(df):
    df['Z_HY_Spread']         = rolling_zscore(df['HY_Spread'], ROLLING_WINDOW)
    df['Z_Jobless_Claims']    = rolling_zscore(df['Jobless_Claims'], ROLLING_WINDOW)
    df['Z_USDJPY']            = rolling_zscore(df['USDJPY'], ROLLING_WINDOW)
    df['Z_DXY']               = rolling_zscore(df['DXY'], ROLLING_WINDOW)
    df['Z_Copper_Gold_Ratio'] = rolling_zscore(df['Copper_Gold_Ratio'], ROLLING_WINDOW)

    # Harmoniseringsregler (negativt = risk-off)
    df['Score_HY']   = -1 * df['Z_HY_Spread']
    df['Score_Jobs'] = -1 * df['Z_Jobless_Claims']
    df['Score_DXY']  = -1 * df['Z_DXY']
    df['Score_CuAu'] = df['Z_Copper_Gold_Ratio']
    
    # Asymmetrisk JPY (0.0 vid försvagning, negativ vid panik)
    df['Score_JPY'] = np.where(df['Z_USDJPY'] < 0, df['Z_USDJPY'], 0.0)
    df.loc[df['Z_USDJPY'].isna(), 'Score_JPY'] = np.nan

    score_cols = ['Score_HY', 'Score_Jobs', 'Score_DXY', 'Score_CuAu', 'Score_JPY']
    df['Total_Macro_Score'] = df[score_cols].sum(axis=1, skipna=False)

    # Släpp uppvärmningsperioden
    df_scored = df.dropna(subset=['Total_Macro_Score']).copy()
    return df_scored

# =============================================================================
# KÖRNING
# =============================================================================
if __name__ == "__main__":
    print("🚀 Startar uppdatering av databas...")
    raw_data = get_macro_data()
    print("✅ Rådata hämtad och synkroniserad.")
    
    scored_data = apply_scoring(raw_data)
    print("✅ Z-scores och Total Macro Score beräknad.")
    
    scored_data.index.name = "Date"
    scored_data.to_csv(OUTPUT_FILE, index=True)
    print(f"🎉 SUCCESS! Sparad till {OUTPUT_FILE}. Senaste datum: {scored_data.index[-1].date()}")
