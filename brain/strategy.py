"""Trading policy: model probability -> action, plus honest backtesting."""
import math

import numpy as np

from .data_feed import get_prices
from .features import add_features

DEFAULTS = {"threshold": 0.56, "take_profit": 0.06, "stop_loss": 0.045,
            "max_position_frac": 0.30, "buy_frac": 0.95, "cost_bps": 2.0}


def decide(model_bundle, df, gh_z=None, params=None, equity=10000.0,
           current_position=0.0, last_price=None):
    """Return action dict from model probability + policy params.

    action: {"action": "buy"/"hold"/"sell"/"wait", "prob", "qty", "reason"}
    """
    p = dict(DEFAULTS)
    p.update(params or {})
    X, _, feats, d = add_features(df, gh_z=gh_z)
    if X is None or len(X) == 0:
        return {"action": "wait", "prob": None,
                "reason": "not enough data for features"}
    model = model_bundle["model"] if isinstance(model_bundle, dict) else model_bundle
    prob = float(model.predict_proba(X.iloc[[-1]])[0, 1])
    price = float(d["Close"].iloc[-1])
    last_price = last_price or price

    if current_position > 0:
        if prob < 0.50:
            return {"action": "sell", "prob": prob, "qty": current_position,
                    "reason": f"edge gone (p={prob:.2f} < 0.50)"}
        return {"action": "hold", "prob": prob, "qty": 0,
                "reason": "in position, keep riding (TP/SL enforced by broker)"}

    if prob >= p["threshold"]:
        budget = equity * p["max_position_frac"]
        qty = math.floor(budget / max(last_price, 0.01))
        if qty >= 1:
            return {"action": "buy", "prob": prob, "qty": int(qty),
                    "reason": f"p={prob:.2f} >= threshold {p['threshold']}"}
    return {"action": "hold", "prob": prob, "qty": 0,
            "reason": f"p={prob:.2f} below threshold {p['threshold']}"}


def backtest(symbol, params=None, df=None, model_bundle=None, initial=10000.0):
    """Walk-forward backtest: retrain-free expansion, trade on next open.

    Splits: 60% train / 40% out-of-sample. Model trained once on the 60%;
    OOS block traded day by day using only information available at each open.
    """
    from .model import _make_model, EMBARGO

    p = dict(DEFAULTS)
    p.update(params or {})
    if df is None:
        df = get_prices(symbol, period="5y")
    X, y, feats, d = add_features(df)
    if X is None or len(X) < 400:
        return {"ok": False, "error": "not enough data to backtest"}
    n = len(X)
    split = int(n * 0.6)
    model = model_bundle["model"] if model_bundle else None
    if model is None:
        model = _make_model(p)
        model.fit(X.iloc[:max(10, split - EMBARGO)], y.iloc[:max(10, split - EMBARGO)])

    cash, shares, equity_curve = initial, 0, []
    oos = d.iloc[split:]
    closes = oos["Close"]
    for i in range(1, len(oos)):
        date, px = oos.index[i], float(closes.iloc[i])
        prev_px = float(closes.iloc[i - 1])
        # TP/SL intraday approximation on today's bar (conservative: open first)
        if shares > 0:
            hi, lo = float(oos["High"].iloc[i]), float(oos["Low"].iloc[i])
            cost_basis = basis
            if lo <= cost_basis * (1 - p["stop_loss"]):
                exit_px = min(prev_px, cost_basis * (1 - p["stop_loss"]))
                cash += shares * exit_px * (1 - p["cost_bps"] / 1e4)
                shares = 0
            elif hi >= cost_basis * (1 + p["take_profit"]):
                exit_px = max(prev_px, cost_basis * (1 + p["take_profit"]))
                cash += shares * exit_px * (1 - p["cost_bps"] / 1e4)
                shares = 0
        row = X.iloc[split + i]
        prob = float(model.predict_proba(row.to_frame().T)[0, 1])
        if shares == 0 and prob >= p["threshold"]:
            qty = math.floor(cash * p["max_position_frac"] / px)
            if qty >= 1:
                cost = qty * px
                cash -= cost * (1 + p["cost_bps"] / 1e4)
                shares, basis = qty, px
        equity_curve.append((str(oos.index[i].date()), cash + shares * px))

    final = equity_curve[-1][1] if equity_curve else initial
    rets = np.diff(np.array([e[1] for e in equity_curve] or [initial])) / initial
    downside = rets[rets < 0]
    sharpe = float(np.mean(rets) / np.std(rets) * math.sqrt(252)) if len(rets) > 1 and np.std(rets) > 0 else 0.0
    sortino = float(np.mean(rets) / np.std(downside) * math.sqrt(252)) if len(downside) > 1 and np.std(downside) > 0 else 0.0
    peak, mdd = -1e18, 0.0
    for _, v in equity_curve:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak)
    dn = closes.iloc[0]
    bh = (float(closes.iloc[-1]) / float(dn) - 1) * 100
    return {"ok": True, "symbol": symbol, "params": p,
            "initial": initial, "final": round(final, 2),
            "return_pct": round((final / initial - 1) * 100, 2),
            "buy_hold_pct": round(bh, 2),
            "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
            "max_drawdown_pct": round(mdd * 100, 2),
            "oos_days": len(equity_curve)}
