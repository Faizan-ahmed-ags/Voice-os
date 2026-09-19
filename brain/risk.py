"""Risk layer: position sizing + hard daily-loss circuit breaker.

These caps are read fresh from .env with sanity clamps and are NEVER
persisted into config.json, so an LLM proposal or config edit cannot
loosen them. Enforced before every order.
"""
from . import util
from .store import get_memory, set_memory

CLAMPS = {
    "risk_per_trade_pct": (0.1, 2.0),
    "max_daily_loss_pct": (1.0, 10.0),
}


def env_float(key, default):
    try:
        from .llm import env
        v = float(str(env().get(key, "") or default))
        return v
    except (TypeError, ValueError):
        return float(default)


def caps():
    """Effective risk caps (clamped)."""
    r = env_float("RISK_PER_TRADE_PCT", 1.0)
    d = env_float("MAX_DAILY_LOSS_PCT", 3.0)
    r = max(CLAMPS["risk_per_trade_pct"][0], min(CLAMPS["risk_per_trade_pct"][1], r))
    d = max(CLAMPS["max_daily_loss_pct"][0], min(CLAMPS["max_daily_loss_pct"][1], d))
    return {"risk_per_trade_pct": r, "max_daily_loss_pct": d}


def today():
    return util.utcnow().strftime("%Y-%m-%d")


def day_state(equity):
    """Return {date, start_equity, pnl, pnl_pct, blocked} for the current day."""
    c = caps()
    day = today()
    if not equity or float(equity) <= 0:
        # Bogus equity (broker glitch) would fake a total-loss day and
        # trip the breaker. Refuse to compute instead.
        raise ValueError(f"invalid equity for day_state: {equity!r}")
    guard = get_memory("day_guard", {}) or {}
    if guard.get("date") != day:
        guard = {"date": day, "start_equity": float(equity)}
    start = float(guard.get("start_equity") or equity)
    pnl = equity - start
    pnl_pct = (pnl / start * 100) if start else 0.0
    return {
        "date": day,
        "start_equity": round(start, 2),
        "equity": round(equity, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 3),
        "max_daily_loss_pct": c["max_daily_loss_pct"],
        "risk_per_trade_pct": c["risk_per_trade_pct"],
        "blocked": pnl_pct <= -c["max_daily_loss_pct"],
        "_guard": guard,
    }


def save_day_state(state):
    g = dict(state.get("_guard") or {})
    g.update({"date": state["date"], "start_equity": state["start_equity"],
              "last_equity": state["equity"]})
    set_memory("day_guard", g)


def check_order(equity, price, action="buy", stop_loss_frac=0.045):
    """Gate an order: returns (allowed, qty, reason).

    Sizing: risk 1% of equity assumed lost at the stop distance, so
    qty = equity * risk% / (price * stop%) — capped by 30% notional.
    Hard-blocked entirely when the daily cap is breached.
    """
    c = caps()
    st = day_state(equity)
    save_day_state(st)
    if st["blocked"]:
        return False, 0, (f"daily loss {st['pnl_pct']:.2f}% <= "
                          f"-{c['max_daily_loss_pct']}% — circuit breaker engaged")
    if action != "buy":
        return True, 0, "sell/close not size-limited"
    risk_dollars = equity * c["risk_per_trade_pct"] / 100
    per_share_risk = max(price * stop_loss_frac, 0.01)
    qty = int(risk_dollars / per_share_risk)
    max_notional = equity * 0.30
    qty = min(qty, int(max_notional / max(price, 0.01)))
    if qty < 1:
        return False, 0, "risk sizing produced qty < 1"
    return True, qty, (f"risk {c['risk_per_trade_pct']}%: qty {qty} "
                       f"(day pnl {st['pnl_pct']:+.2f}%)")
