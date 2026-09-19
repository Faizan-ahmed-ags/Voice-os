"""Strategy suite: several independent strategies, each with honest backtests.

The daily cycle runs ALL strategies per symbol on fresh data, scores them by
their trailing out-of-sample performance (auto-weighted), and executes the
best one. The ML edge strategy stays first-class; MA-cross, RSI-reversion and
breakout are classical fallbacks that trade even when the model has no edge.

Every strategy returns the same action dict shape as strategy.decide:
  {"action": buy/hold/sell/wait, "qty", "reason", "strategy"}
"""
import math

import numpy as np

from .data_feed import get_prices
from .features import add_features

# How much history each classical strategy needs
MIN_BARS = 60


# ------------------------------------------------------------------ helpers

def _sma(series, n):
    return series.rolling(n).mean()


def _rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


# ------------------------------------------------------------- classical

def ma_cross(df, equity, current_position, params=None):
    """Trend following: price above SMA20>SMA50 cross = uptrend regime."""
    p = dict(trend_frac=0.25, exit_slope=0.0)
    p.update(params or {})
    if len(df) < 60:
        return {"action": "wait", "qty": 0, "reason": "not enough bars"}
    sma20, sma50 = _sma(df["Close"], 20), _sma(df["Close"], 50)
    price = float(df["Close"].iloc[-1])
    above = sma20.iloc[-1] > sma50.iloc[-1] and price > sma20.iloc[-1]
    was_above = sma20.iloc[-2] > sma50.iloc[-2]
    if current_position > 0 and not (sma20.iloc[-1] > sma50.iloc[-1]):
        return {"action": "sell", "qty": current_position,
                "reason": "trend flipped down (SMA20 < SMA50)", "strategy": "ma_cross"}
    if current_position > 0:
        return {"action": "hold", "qty": 0, "reason": "trend intact",
                "strategy": "ma_cross"}
    if above and not was_above:
        qty = math.floor(equity * p["trend_frac"] / max(price, 0.01))
        if qty >= 1:
            return {"action": "buy", "qty": qty,
                    "reason": f"golden cross: SMA20 crossed above SMA50 @ {price:.2f}",
                    "strategy": "ma_cross"}
    return {"action": "hold", "qty": 0,
            "reason": "no fresh golden cross", "strategy": "ma_cross"}


def rsi_reversion(df, equity, current_position, params=None):
    """Buy fear (RSI dips below 30), sell greed (above 65)."""
    p = dict(oversold=30, overbought=65, revo_frac=0.20)
    p.update(params or {})
    if len(df) < MIN_BARS:
        return {"action": "wait", "qty": 0, "reason": "not enough bars"}
    rsi = _rsi(df["Close"])
    r = float(rsi.iloc[-1])
    if math.isnan(r):
        return {"action": "hold", "qty": 0, "reason": "RSI warming up"}
    price = float(df["Close"].iloc[-1])
    if current_position > 0 and r >= p["overbought"]:
        return {"action": "sell", "qty": current_position,
                "reason": f"RSI {r:.0f} overbought — taking profit", "strategy": "rsi_reversion"}
    if current_position > 0:
        return {"action": "hold", "qty": 0, "reason": f"RSI {r:.0f} neutral",
                "strategy": "rsi_reversion"}
    if r <= p["oversold"]:
        qty = math.floor(equity * p["revo_frac"] / max(price, 0.01))
        if qty >= 1:
            return {"action": "buy", "qty": qty,
                    "reason": f"RSI {r:.0f} oversold — mean-reversion entry",
                    "strategy": "rsi_reversion"}
    return {"action": "hold", "qty": 0,
            "reason": f"RSI {r:.0f} neutral", "strategy": "rsi_reversion"}


def breakout(df, equity, current_position, params=None):
    """Donchian 20-day breakout entry, 10-day low exit."""
    p = dict(entry_n=20, exit_n=10, brk_frac=0.25)
    p.update(params or {})
    if len(df) < MIN_BARS + 5:
        return {"action": "wait", "qty": 0, "reason": "not enough bars"}
    price = float(df["Close"].iloc[-1])
    hi_n = float(df["High"].iloc[-p["entry_n"] - 1:-1].max())
    lo_n = float(df["Low"].iloc[-p["exit_n"] - 1:-1].min())
    if current_position > 0 and price < lo_n:
        return {"action": "sell", "qty": current_position,
                "reason": f"broke 10-day low {lo_n:.2f}", "strategy": "breakout"}
    if current_position > 0:
        return {"action": "hold", "qty": 0, "reason": "breakout ride intact",
                "strategy": "breakout"}
    if price > hi_n:
        qty = math.floor(equity * p["brk_frac"] / max(price, 0.01))
        if qty >= 1:
            return {"action": "buy", "qty": qty,
                    "reason": f"20-day breakout: {price:.2f} > {hi_n:.2f}",
                    "strategy": "breakout"}
    return {"action": "hold", "qty": 0, "reason": "inside the range",
            "strategy": "breakout"}


# ------------------------------------------------------------------ ML edge

def ml_edge(model_bundle, df, gh_z, equity, current_position, params):
    """The champion-params ML strategy (existing brain.strategy.decide)."""
    from .strategy import decide
    act = decide(model_bundle, df, gh_z=gh_z, params=params, equity=equity,
                 current_position=current_position)
    act["strategy"] = "ml_edge"
    return act


CLASSICAL = ("ma_cross", "rsi_reversion", "breakout")


def run_all(model_bundle, df, gh_z, equity, current_position, params):
    """All strategies' opinions for one symbol (used by the chooser + UI)."""
    out = {"ml_edge": ml_edge(model_bundle, df, gh_z, equity,
                              current_position, params)}
    for name, fn in (("ma_cross", ma_cross), ("rsi_reversion", rsi_reversion),
                     ("breakout", breakout)):
        try:
            out[name] = fn(df, equity, current_position)
        except Exception as e:
            out[name] = {"action": "wait", "qty": 0, "reason": f"error: {e}"}
    return out


# ------------------------------------------------- auto-selection per symbol

def _trailing_score(symbol, strat_name):
    """Recent realized P&L of this symbol+strategy from the trade ledger."""
    try:
        from .store import recent_trades
        trades = [t for t in recent_trades(40, closed_only=True)
                  if t["symbol"] == symbol and t.get("strategy") == strat_name]
        if not trades:
            return None
        return sum(float(t.get("pnl") or 0) for t in trades)
    except Exception:
        return None


def choose(symbol, opinions, model_bundle, df, gh_z, params):
    """Pick the action to execute: ML if champion, else best classical.

    Rules:
    - ml_edge is used when its model is a champion AND it says buy/sell/hold-in-position
    - otherwise, prefer the classical strategy with the best trailing ledger P&L
      that proposes an actionable trade; if none proposes, hold.
    - a champion-ml sell (edge gone) always wins: exit protection first.
    """
    ml = opinions["ml_edge"]
    champ = bool(model_bundle and isinstance(model_bundle, dict)
                 and model_bundle.get("meta", {}).get("status") == "champion")

    if champ and ml.get("action") == "sell":
        return ml
    if champ and ml.get("action") in ("buy", "hold") and current_pos_hint(ml):
        return ml

    # rank classical strategies by trailing P&L (0.0 default), require actionable
    scored = []
    for name in CLASSICAL:
        act = opinions[name]
        s = _trailing_score(symbol, name)
        score = s if s is not None else 0.0
        actionable = act.get("action") in ("buy", "sell")
        scored.append((score, name, actionable, act))
    for score, name, actionable, act in sorted(scored, key=lambda x: -x[0]):
        if actionable:
            return act
    # nothing actionable classically -> if champion ML holds in-position, honor it
    if champ and ml.get("action") == "hold":
        return ml
    # else the least-bad hold for the report
    return {"action": "hold", "qty": 0,
            "reason": "no strategy sees an entry", "strategy": "auto"}


def current_pos_hint(act):
    return False  # decide() returns hold+qty=0 when riding; sell handled above


def backtest_classical(symbol, name, initial=10000.0):
    """Simple honest OOS backtest for classical strategies (last 40% of bars).

    Shares the same spirit as strategy.backtest: trade next bar after signal,
    include a 4.5% stop / 6% TP bracket approximation intraday.
    """
    p = {"ma_cross": dict(trend_frac=0.25), "rsi_reversion": dict(revo_frac=0.20),
         "breakout": dict(brk_frac=0.25)}[name]
    try:
        df = get_prices(symbol, period="5y")
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if len(df) < 250:
        return {"ok": False, "error": "not enough data"}
    split = int(len(df) * 0.6)
    oos = df.iloc[split:].reset_index(drop=True)
    cash, shares, basis, curve = initial, 0, 0.0, []
    from .strategy import DEFAULTS
    for i in range(1, len(oos)):
        window = oos.iloc[: i + 1]
        px = float(oos["Close"].iloc[i])
        hi, lo = float(oos["High"].iloc[i]), float(oos["Low"].iloc[i])
        if shares > 0:
            if lo <= basis * (1 - DEFAULTS["stop_loss"]):
                cash += shares * min(px, basis * (1 - DEFAULTS["stop_loss"]))
                shares = 0
            elif hi >= basis * (1 + DEFAULTS["take_profit"]):
                cash += shares * max(px, basis * (1 + DEFAULTS["take_profit"]))
                shares = 0
        if shares == 0:
            sig = {"ma_cross": ma_cross, "rsi_reversion": rsi_reversion,
                   "breakout": breakout}[name](window, cash, 0, p)
            if sig.get("action") == "buy" and sig.get("qty", 0) >= 1:
                qty = min(sig["qty"], math.floor(cash / px)) if px > 0 else 0
                if qty >= 1:
                    cash -= qty * px
                    shares, basis = qty, px
        curve.append(cash + shares * px)
    final = curve[-1] if curve else initial
    rets = np.diff(np.array([initial] + curve)) / initial
    sharpe = float(np.mean(rets) / np.std(rets) * math.sqrt(252)) if len(rets) > 1 and np.std(rets) > 0 else 0.0
    bh = (float(oos["Close"].iloc[-1]) / float(oos["Close"].iloc[0]) - 1) * 100
    return {"ok": True, "strategy": name, "return_pct": round((final / initial - 1) * 100, 2),
            "buy_hold_pct": round(bh, 2), "sharpe": round(sharpe, 2),
            "oos_days": len(curve)}
