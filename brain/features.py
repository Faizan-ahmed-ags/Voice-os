"""Feature engineering from price data (+ optional GitHub signal)."""
import numpy as np


def add_features(df, gh_z=None):
    """df: OHLCV DataFrame indexed by Date. Returns (X, y, feature_names, df2)."""
    try:
        import pandas as pd
    except ImportError:
        return None, None, None, None
    if df is None or len(df) < 60:
        return None, None, None, None

    d = df.copy()
    c = d["Close"]
    d["ret1"] = c.pct_change()
    d["ret5"] = c.pct_change(5)
    d["ret21"] = c.pct_change(21)
    d["vol21"] = d["ret1"].rolling(21).std() * np.sqrt(252)
    d["sma10"] = c.rolling(10).mean() / c - 1
    d["sma50"] = c.rolling(50).mean() / c - 1
    d["sma200"] = c.rolling(200).mean() / c - 1
    hi = d["High"].rolling(55).max()
    lo = d["Low"].rolling(55).min()
    d["don55"] = (c - lo) / (hi - lo).replace(0, np.nan)
    delta = c.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    dn = (-delta.clip(upper=0)).rolling(14).mean()
    d["rsi14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    ewm_up = up.ewm(alpha=1 / 14).mean()
    ewm_dn = dn.ewm(alpha=1 / 14).mean()
    d["rsi_smooth"] = 100 - 100 / (1 + ewm_up / ewm_dn.replace(0, np.nan))
    macd = c.ewm(span=12).mean() - c.ewm(span=26).mean()
    d["macd"] = macd / c
    d["macd_sig"] = (macd - macd.ewm(span=9).mean()) / c
    bb = c.rolling(20).std()
    d["bb_pos"] = (c - c.rolling(20).mean()) / (2 * bb).replace(0, np.nan)
    d["atr14"] = ((d["High"] - d["Low"]).rolling(14).mean()) / c
    d["vol_z"] = (d["Volume"] - d["Volume"].rolling(21).mean()) / (
        d["Volume"].rolling(21).std().replace(0, np.nan))
    if gh_z is not None:
        d["gh_z"] = gh_z
    else:
        d["gh_z"] = 0.0

    # Label: will close be higher 5 sessions ahead (risk-adjusted)?
    fwd = c.shift(-5) / c - 1
    d["fwd_ret5"] = fwd
    d["label"] = (fwd > 0).astype(int)

    feats = ["ret1", "ret5", "ret21", "vol21", "sma10", "sma50", "sma200",
             "don55", "rsi14", "rsi_smooth", "macd", "macd_sig", "bb_pos",
             "atr14", "vol_z", "gh_z"]
    d = d.dropna(subset=feats)
    d = d[d["fwd_ret5"].notna()]  # keep only rows whose label is known
    X = d[feats].astype(float)
    y = d["label"].astype(int)
    return X, y, feats, d
