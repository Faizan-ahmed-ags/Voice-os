"""MetaTrader5 terminal bridge (official package, Windows).

Attaches to an installed & running MT5 terminal using credentials from
.env (MT5_LOGIN / MT5_PASSWORD / MT5_SERVER). Demo-only guard: refuses
live accounts while JARVIS_TRADING_MODE=demo. All functions never raise
to callers — errors come back as {"ok": False, "error": ...}.
"""
from pathlib import Path

from . import util
from .store import record_decision

_STATE = {"connected": False, "error": "not tried yet", "info": None}


def creds():
    from .llm import env
    e = env()
    login = str(e.get("MT5_LOGIN", "")).strip()
    return {
        "login": int(login) if login.isdigit() else 0,
        "password": str(e.get("MT5_PASSWORD", "")).strip(),
        "server": str(e.get("MT5_SERVER", "")).strip(),
    }


def _mt5():
    import MetaTrader5 as mt5
    return mt5


def _mode_allows_live():
    from .llm import env
    return str(env().get("JARVIS_TRADING_MODE", "demo")).strip().lower() in ("live", "real")


def connect():
    """Attach + login. Returns (ok, info_or_error)."""
    c = creds()
    if not (c["login"] and c["password"] and c["server"]):
        _STATE.update(connected=False,
                      error="MT5_LOGIN/PASSWORD/SERVER not set (Connections page)")
        return False, _STATE["error"]
    try:
        mt5 = _mt5()
        if not mt5.initialize():
            err = f"initialize failed ({mt5.last_error()})"
            _STATE.update(connected=False, error=err)
            return False, err
        if not mt5.login(c["login"], password=c["password"], server=c["server"]):
            err = f"login failed ({mt5.last_error()})"
            mt5.shutdown()
            _STATE.update(connected=False, error=err)
            return False, err
        acct = mt5.account_info()
        if acct is None:
            mt5.shutdown()
            _STATE.update(connected=False, error="account_info returned None")
            return False, _STATE["error"]
        if not _mode_allows_live() and not acct.trade_mode == 0:
            mt5.shutdown()
            err = ("LIVE account refused — JARVIS_TRADING_MODE=demo. "
                   "Use a demo account or explicitly switch modes in .env.")
            _STATE.update(connected=False, error=err)
            return False, err
        info = {
            "login": acct.login, "name": acct.name, "server": acct.server,
            "currency": acct.currency, "leverage": acct.leverage,
            "balance": round(acct.balance, 2), "equity": round(acct.equity, 2),
            "trade_mode": "demo" if acct.trade_mode == 0 else "live",
            "company": acct.company,
        }
        _STATE.update(connected=True, error=None, info=info)
        return True, info
    except Exception as e:
        _STATE.update(connected=False, error=str(e)[:200])
        return False, _STATE["error"]


def shutdown():
    try:
        _mt5().shutdown()
    except Exception:
        pass
    _STATE.update(connected=False)


def status():
    ok, info = (True, _STATE["info"]) if _STATE["connected"] else connect()
    return {
        "package": True,
        "connected": ok,
        "account": info if ok else None,
        "error": None if ok else info,
        "mode_allowed": _mode_allows_live(),
    }


def equity():
    ok, info = (True, _STATE["info"]) if _STATE["connected"] else connect()
    if not ok:
        return None
    try:
        acct = _mt5().account_info()
        return float(acct.equity) if acct else None
    except Exception:
        return None


def positions():
    """{symbol: volume} for open MT5 positions."""
    try:
        mt5 = _mt5()
        ps = mt5.positions_get()
        return {p.symbol: float(p.volume) for p in (ps or [])}
    except Exception:
        return {}


def position(symbol):
    return positions().get(symbol, 0.0)


def symbols_all():
    try:
        mt5 = _mt5()
        if _STATE["connected"] or connect()[0]:
            syms = mt5.symbols_get()
            return [s.name for s in (syms or [])]
    except Exception:
        pass
    return []


def _fill_type_for(symbol):
    """Pick the filling mode the symbol actually allows (FOK > IOC > RETURN)."""
    mt5 = _mt5()
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    if not info.visible:
        mt5.symbol_select(symbol, True)
    modes = int(getattr(info, "filling_mode", 0) or 0)
    if modes & 1:
        return mt5.ORDER_FILLING_FOK
    if modes & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def order(symbol, side, volume, reason="", sl_pct=None, tp_pct=None,
          prob=None, params=None, strategy="auto"):
    """Market order: side 'buy'/'sell', volume in lots. Halal + risk gates upstream.

    sl_pct/tp_pct attach broker-enforced stop-loss / take-profit brackets
    (percent from fill price), so exits happen at the broker 24/5 even with
    this console offline — 'close when in profit' without babysitting.
    prob/params ride along as decision context for the trade ledger, so the
    learning agent can later judge the entry, not just the outcome.
    """
    ok, _ = (True, None) if _STATE["connected"] else connect()
    if not ok:
        return {"ok": False, "error": _STATE["error"]}
    try:
        mt5 = _mt5()
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return {"ok": False, "error": f"unknown symbol {symbol}"}
        if not symbol_info.visible:
            mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"ok": False, "error": f"no tick for {symbol}"}
        price = tick.ask if side == "buy" else tick.bid
        want = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL

        # Hedging accounts open a NEW opposite position instead of closing.
        # Net-close any opposite positions by ticket first (demo-mode proof:
        # a naive sell left a long open AND opened a short). Only the volume
        # that cannot net-close continues as a new deal below.
        remaining = float(volume)
        net_closed = []
        try:
            poss = mt5.positions_get(symbol=symbol) or []
        except Exception:
            poss = []
        for p in poss:
            if remaining <= 0:
                break
            opposite = ((want == mt5.ORDER_TYPE_SELL and p.type == mt5.ORDER_TYPE_BUY)
                        or (want == mt5.ORDER_TYPE_BUY and p.type == mt5.ORDER_TYPE_SELL))
            if not opposite:
                continue
            vol = min(remaining, float(p.volume))
            tick2 = mt5.symbol_info_tick(symbol)
            if tick2 is None:
                break
            close_price = tick2.bid if want == mt5.ORDER_TYPE_SELL else tick2.ask
            creq = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": p.ticket,
                "symbol": symbol,
                "volume": vol,
                "type": want,
                "price": close_price,
                "deviation": 20,
                "magic": 20260914,
                "comment": ("jarvis net close " + (reason or ""))[:25],
                "type_filling": _fill_type_for(symbol) or 0,
                "type_time": mt5.ORDER_TIME_GTC,
            }
            r = mt5.order_send(creq)
            if r is not None and r.retcode == mt5.TRADE_RETCODE_DONE:
                net_closed.append({"ticket": p.ticket, "volume": vol, "price": float(close_price)})
                remaining -= vol
                record_decision(util.iso(), symbol,
                                "SELL" if want == mt5.ORDER_TYPE_SELL else "BUY",
                                vol, float(close_price), "mt5-demo",
                                f"net close #{p.ticket}: {reason}")
        if remaining <= 0:
            return {"ok": True, "filled": float(volume), "price": float(price),
                    "net_closed": net_closed}

        # attach TP/SL to the NEW position only (net closes exit at market)
        sl = tp = None
        if sl_pct and want == mt5.ORDER_TYPE_BUY:
            sl = round(price * (1 - sl_pct / 100.0), 2)
        elif sl_pct:
            sl = round(price * (1 + sl_pct / 100.0), 2)
        if tp_pct and want == mt5.ORDER_TYPE_BUY:
            tp = round(price * (1 + tp_pct / 100.0), 2)
        elif tp_pct:
            tp = round(price * (1 - tp_pct / 100.0), 2)

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": remaining,
            "type": want,
            "price": price,
            "sl": sl or 0.0,
            "tp": tp or 0.0,
            "deviation": 20,
            "magic": 20260914,
            "comment": (reason or "jarvis")[:25],
            "type_filling": _fill_type_for(symbol) or 0,
            "type_time": mt5.ORDER_TIME_GTC,
        }
        res = mt5.order_send(req)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            code = getattr(res, "retcode", "None")
            return {"ok": False, "error": f"order_send retcode={code}"}
        # newest matching open position = our ticket (hedging accounts)
        ticket = None
        try:
            side_type = (mt5.POSITION_TYPE_BUY if want == mt5.ORDER_TYPE_BUY
                         else mt5.POSITION_TYPE_SELL)
            cands = [p for p in (mt5.positions_get(symbol=symbol) or [])
                     if p.type == side_type
                     and abs(float(p.volume) - remaining) < 1e-9]
            ticket = max((int(p.ticket) for p in cands), default=None)
        except Exception:
            pass
        record_decision(util.iso(), symbol, side.upper(), float(volume),
                        float(price), "mt5-demo", reason)
        try:
            from .learner import capture
            capture(symbol, side, float(volume), float(price), ticket=ticket,
                    mode="mt5-demo", prob=prob, params=params, reason=reason,
                    sl_pct=sl_pct, tp_pct=tp_pct, strategy=strategy)
        except Exception:
            pass
        return {"ok": True, "filled": float(volume), "price": float(price),
                "ticket": ticket}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def deals(days=30):
    """Closed deals from history for P&L: [{date, symbol, profit, volume, side}]."""
    try:
        import datetime as dt
        mt5 = _mt5()
        if not (_STATE["connected"] or connect()[0]):
            return []
        frm = dt.datetime.now() - dt.timedelta(days=days)
        dl = mt5.history_deals_get(frm, dt.datetime.now() + dt.timedelta(days=1))
        out = []
        for d in (dl or []):
            if d.entry == 1:  # DEAL_ENTRY_OUT (closing side carries profit)
                out.append({
                    "date": util.iso_from_ts(d.time),
                    "symbol": d.symbol,
                    "profit": round(float(d.profit), 2),
                    "volume": float(d.volume),
                    "price": round(float(d.price), 5),
                    "position_id": int(d.position_id) if getattr(d, "position_id", 0) else None,
                })
        return out
    except Exception as e:
        util.log_event("MT5", f"deals failed: {e}")
        return []


def symbol_info(symbol):
    """Last trade price for a symbol (ask), or None when unavailable."""
    try:
        mt5 = _mt5()
        if not (_STATE["connected"] or connect()[0]):
            return None
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            return None
        return float(t.ask or t.bid or 0) or None
    except Exception:
        return None


def candles(symbol, timeframe="1D", count=400):
    """OHLC bars from the terminal for charting.

    timeframe: '1m','5m','15m','1h','4h','1D'. Returns
    [{t, o, h, l, c}] with unix-seconds; empty list when unavailable.
    """
    tf_map = {"1m": 1, "5m": 5, "15m": 15, "1h": 16385, "4h": 16388, "1D": 16408}
    try:
        mt5 = _mt5()
        if not (_STATE["connected"] or connect()[0]):
            return []
        tf = tf_map.get(timeframe, 16408)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, int(count))
        if rates is None:
            return []
        return [{"t": int(r["time"]), "o": float(r["open"]), "h": float(r["high"]),
                 "l": float(r["low"]), "c": float(r["close"])} for r in rates]
    except Exception as e:
        util.log_event("MT5", f"candles failed: {e}")
        return []


def available():
    try:
        _mt5()
        return True
    except Exception:
        return False
