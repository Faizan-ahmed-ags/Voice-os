"""The Plan page data: what JARVIS intends to do and under which rules.

Combines: halal screen, champion strategy params + guardrail bounds,
latest backtest, and the daemon schedule.
"""
from . import util
from .agent import BOUNDS
from .config import load
from .halal import screen_universe
from .store import get_memory

_SCHEDULE_NOTE = (
    "run-once executes daily just after US market close; evolution runs weekly. "
    "Start it with: python -m brain.main daemon"
)


def _latest_backtest(symbol):
    cache = util.load_json(util.DATA_DIR / "backtest_cache.json", {}) or {}
    entry = cache.get(symbol)
    if entry:
        return entry
    try:
        from .strategy import backtest
        res = backtest(symbol)
        if res.get("ok"):
            keep = {k: res[k] for k in (
                "return_pct", "buy_hold_pct", "sharpe", "sortino",
                "max_drawdown_pct", "oos_days", "params") if k in res}
            cache[symbol] = keep
            util.save_json(util.DATA_DIR / "backtest_cache.json", cache)
            return keep
    except Exception as e:
        return {"error": str(e)}
    return None


def plan_snapshot():
    cfg = load()
    halal = screen_universe(cfg["universe"])
    champs = util.load_json(util.DATA_DIR / "champion_params.json", {}) or {}
    symbols = []
    for sym in cfg["universe"]:
        m = get_memory(f"champion:{sym}")
        symbols.append({
            "symbol": sym,
            "halal": halal.get(sym),
            "model": {"status": (m or {}).get("status"), "auc": ((m or {}).get("cv") or {}).get("auc_mean")}
            if m else None,
            "params": champs.get(sym, "defaults"),
            "backtest": _latest_backtest(sym),
        })
    return {
        "universe": cfg["universe"],
        "symbols": symbols,
        "guardrails": {k: {"min": v[0], "max": v[1]} for k, v in BOUNDS.items()},
        "schedule": {"daily_run_time": cfg["daily_run_time"],
                     "evolve": f"{cfg['evolve_day']} {cfg['evolve_time']} UTC",
                     "note": _SCHEDULE_NOTE},
        "risk": {"max_daily_loss_pct": cfg["max_daily_loss_pct"],
                 "starting_cash": cfg["starting_cash"],
                 "paper_trading": cfg["paper_trading"]},
    }
