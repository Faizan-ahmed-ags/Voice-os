"""The everyday loop: learn (retrain) -> predict -> trade by rules -> journal.

Runs after US market close. Orders route through the active broker:
MT5 demo when connected, else SIM. Risk caps from brain.risk are hard.
"""
import json
import threading

from . import util
from . import config as cfgmod
from . import risk
from . import mt5_bridge
from .halal import screen_universe
from .store import (get_memory, set_memory, upsert_daily_pnl, record_cycle,
                    last_cycle)
from .main import _load_model

_LOCK = threading.Lock()
_in_progress = False


def status():
    cfg = cfgmod.load()
    last = last_cycle()
    mt5 = mt5_bridge.status()
    mt5_on = mt5["connected"]
    sched = (cfg.get("daily_run_time_mt5", "13:40") if mt5_on
             else cfg.get("daily_run_time", "21:45"))
    return {
        "in_progress": _in_progress,
        "schedule": sched + " UTC (after US open)" if mt5_on else sched + " UTC (after US close)",
        "broker": ("mt5-demo" if mt5_on else "sim"),
        "mt5": mt5,
        "risk": risk.caps(),
        "last_cycle": last,
    }


def _prediction_for(sym, bundle, df, gh_z, equity, pos, params):
    """Model probability -> proposed action, without placing anything."""
    from .strategy import decide
    act = decide(bundle, df, gh_z=gh_z, params=params, equity=equity,
                 current_position=pos)
    return act


def run_cycle(trigger="manual"):
    """One full daily cycle. Returns a result dict (also stored + journaled)."""
    global _in_progress
    if not _LOCK.acquire(blocking=False):
        return {"ok": False, "error": "a cycle is already running"}
    _in_progress = True
    try:
        cfg = cfgmod.load()
        import os
        broker_kind = "mt5-demo" if mt5_bridge.status()["connected"] else "sim"
        if os.environ.get("JARVIS_BROKER", "").strip().lower() in ("alpaca", "paper"):
            broker_kind = "alpaca-paper"
        from .brokers import get_broker
        broker = get_broker(cfg)

        predictions = {}
        orders = []
        screened = screen_universe(cfg["universe"])
        model_ok = True

        # ---- 1. LEARN: retrain every universe model on the latest data
        from .model import train_model
        learned = {}
        for sym in cfg["universe"]:
            try:
                out = train_model(sym)
                learned[sym] = out["meta"]["cv"]["auc_mean"]
            except Exception as e:
                model_ok = False
                util.log_event("CYCLE", f"train {sym} failed: {e}")
                learned[sym] = None

        # ---- 2. PREDICT + 3. TRADE (rules + halal + risk)
        from .data_feed import get_prices, github_signal
        champs = util.load_json(util.DATA_DIR / "champion_params.json", {}) or {}
        for sym, comp in screened.items():
            entry = {"compliant": comp["compliant"], "reason": comp["reason"]}
            predictions[sym] = entry
            if not comp["compliant"]:
                entry["action"] = "skip"
                continue
            bundle = _load_model(sym)
            df = None
            gh_z = None
            try:
                df = get_prices(sym)
                _, gh_z = github_signal(sym)
            except Exception as e:
                util.log_event("CYCLE", f"data {sym}: {e}")
            if df is None or bundle is None:
                entry["action"] = "wait"
                entry["reason"] = "no data/model yet"
                continue
            try:
                equity = broker.equity()
            except Exception as e:
                entry["action"] = "skip"
                entry["reason"] = f"equity unavailable — {e}"
                continue
            pos = broker.position(sym)
            from .strategies import run_all, choose
            try:
                opinions = run_all(bundle, df, gh_z, equity, pos,
                                   champs.get(sym) or {})
                act = choose(sym, opinions, equity, pos)
            except Exception as e:
                entry["action"] = "wait"
                entry["reason"] = f"strategy suite error: {e}"
                continue
            entry["strategies"] = {k: {"action": v.get("action"),
                                        "reason": v.get("reason")}
                                    for k, v in opinions.items()}
            entry.update(action=act["action"], strategy=act.get("strategy"),
                         prob=round(act["prob"], 3) if act.get("prob") else None,
                         reason=act["reason"])

            strat = act.get("strategy", "auto")
            if act["action"] == "buy":
                price = float(df["Close"].iloc[-1])
                allowed, qty, why = risk.check_order(equity, price, "buy")
                entry["risk"] = why
                if not allowed:
                    entry["action"] = "blocked"
                    entry["reason"] = why
                    continue
                res = broker.buy(sym, qty, price, act["reason"], sl_pct=4.5,
                                 tp_pct=6.0, prob=act.get("prob"),
                                 params=champs.get(sym) or {}, strategy=strat)
                entry["order"] = res
                if res.get("ok"):
                    orders.append(f"BUY {sym} {qty} @ {price} [{strat}]")
                    from .memory import decision_note
                    decision_note(sym, "buy", qty, price,
                                  f"[{strat}] {act['reason']}")

            elif act["action"] == "sell":
                price = float(df["Close"].iloc[-1])
                if broker.name == "mt5-demo":
                    res = broker.sell(sym, act["qty"], price, act["reason"],
                                      prob=act.get("prob"),
                                      params=champs.get(sym) or {},
                                      strategy=strat)
                else:
                    res = broker.sell(sym, act["qty"], price, act["reason"],
                                      prob=act.get("prob"),
                                      params=champs.get(sym) or {})
                entry["order"] = res
                if res.get("ok"):
                    orders.append(f"SELL {sym} @ {price} [{strat}]")

        # ---- 4. JOURNAL: P&L snapshot + cycle note
        # Equity must be real; a broker glitch must never journal a fake loss.
        equity = None
        try:
            equity = broker.equity()
        except Exception as e:
            util.log_event("CYCLE", f"journal skipped: equity unavailable ({e})")
        if equity and equity > 0:
            st = risk.day_state(equity)
            day = st["date"]
            prev = get_memory(f"pnl_start:{day}", None)
            if prev is None:
                set_memory(f"pnl_start:{day}", equity)
                start_eq = equity
            else:
                start_eq = prev
            wins = losses = 0
            from .store import pnl_day
            detail = pnl_day(day) or {}
            for t in detail.get("trades_detail", []):
                if t["action"] == "SELL":
                    wins += 1  # refined below by MT5 deal profits when available
            realized = round(equity - start_eq, 2)
            upsert_daily_pnl(day, start_eq, equity, realized=realized,
                             trades=len(detail.get("trades_detail", [])),
                             wins=wins, losses=losses, mode=broker_kind)
            from .memory import pnl_note, cycle_note
            pnl_note({"date": day, "start_equity": start_eq, "end_equity": equity,
                      "realized": realized, "trades": len(detail.get("trades_detail", [])),
                      "wins": wins, "losses": losses, "mode": broker_kind})
            day_pnl_pct = st["pnl_pct"]
        else:
            from .memory import cycle_note
            day = None
            day_pnl_pct = None
        # ---- 5. LEARN FROM TRADES: reconcile broker-side exits + reflect
        rec, lessons_n = {"matched": 0}, 0
        try:
            from .learner import reconcile, reflect
            rec = reconcile()
            lessons_n = reflect()
            if rec["matched"] or lessons_n:
                util.log_event("LEARN", f"post-cycle: {rec['matched']} reconciled, "
                                        f"{lessons_n} lessons")
        except Exception as e:
            util.log_event("LEARN", f"post-cycle learning failed: {e}")

        result = {"ok": True, "trigger": trigger, "status": "completed",
                  "broker": broker_kind, "learned_auc": learned,
                  "predictions": predictions, "orders": orders,
                  "reconciled": rec.get("matched", 0), "lessons": lessons_n,
                  "equity": equity, "day_pnl_pct": day_pnl_pct}
        cycle_note(result)
        record_cycle(trigger, "completed", symbols_scanned=len(screened),
                     orders_placed=len(orders), predictions=predictions,
                     notes=json.dumps(orders))
        util.log_event("CYCLE", f"done: {len(orders)} orders, equity {equity}")
        return result
    finally:
        _in_progress = False
        _LOCK.release()


def schedule_loop(stop_event):
    """Background thread: run the cycle once per day at the configured time."""
    import time
    while not stop_event.is_set():
        try:
            cfg = cfgmod.load()
            # MT5 fills equity orders only inside the session -> run after US open;
            # sim has no session -> keep the after-close schedule.
            key = ("daily_run_time_mt5" if mt5_bridge.status()["connected"]
                   else "daily_run_time")
            hh, mm = cfg.get(key, "21:45").split(":")
            now = util.utcnow()
            target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if now >= target:
                target = target.replace(day=target.day) + _one_day(target)
            wait = max(5, (target - now).total_seconds())
            if stop_event.wait(timeout=wait):
                break
            cfg = cfgmod.load()
            done_key = f"cycle_done:{util.utcnow().strftime('%Y-%m-%d')}"
            if get_memory(done_key, False):
                continue
            if util.utcnow().weekday() >= 5:
                # Sat/Sun: no US session, every equity order would bounce 10018.
                set_memory(done_key, True)
                continue
            run_cycle(trigger="schedule")
            set_memory(done_key, True)
        except Exception as e:
            util.log_event("CYCLE", f"schedule error: {e}")
            if stop_event.wait(timeout=300):
                break


def _one_day(t):
    import datetime as dt
    return dt.timedelta(days=1)
