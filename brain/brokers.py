"""Broker abstraction. SIM = built-in simulator (no keys, default).

Alpaca paper trading activates only when secrets.json has alpaca_key_id +
alpaca_secret_key AND config.paper_trading is true. Live trading is
deliberately not implemented — that switch is manual and out of scope here.
"""
import json
from pathlib import Path

from . import util
from .store import record_decision

SIM_STATE = util.DATA_DIR / "sim_state.json"


def _secrets():
    return util.load_json(util.ROOT / "secrets.json", {}) or {}


class MT5Demo:
    """Routes orders to the attached MetaTrader 5 terminal (demo guard upstream)."""

    name = "mt5-demo"

    def equity(self, prices=None):
        from .mt5_bridge import equity as mt5_equity
        eq = mt5_equity()
        if eq is None:  # one retry — the terminal hiccups occasionally
            import time
            time.sleep(2)
            eq = mt5_equity()
        if not eq or eq <= 0:
            # NEVER fabricate 0 — a fake $0 equity journaled as a huge loss
            # and poisoned the daily-loss breaker once already.
            raise RuntimeError("MT5 equity unavailable (terminal not attached?)")
        return float(eq)

    def positions(self):
        from .mt5_bridge import positions as mt5_positions
        return mt5_positions()

    def position(self, symbol):
        from .mt5_bridge import position as mt5_position
        return mt5_position(symbol)

    def buy(self, symbol, qty, price=None, reason="", sl_pct=None, tp_pct=None,
            prob=None, params=None, strategy="auto"):
        from .mt5_bridge import order as mt5_order
        return mt5_order(symbol, "buy", float(qty), reason, sl_pct=sl_pct,
                         tp_pct=tp_pct, prob=prob, params=params, strategy=strategy)

    def sell(self, symbol, qty, price=None, reason="", prob=None, params=None, strategy="auto"):
        from .mt5_bridge import order as mt5_order
        return mt5_order(symbol, "sell", float(qty), reason,
                         prob=prob, params=params, strategy=strategy)


def get_broker(cfg):
    import os
    s = _secrets()
    # Alpaca activates only when explicitly selected (JARVIS_BROKER=alpaca, used
    # by the cloud runner) AND keys exist (env vars win over secrets.json).
    # Local machines keep MT5/sim behaviour even if keys happen to be present.
    pref = os.environ.get("JARVIS_BROKER", "").strip().lower()
    key = os.environ.get("ALPACA_KEY_ID") or s.get("alpaca_key_id")
    sec = os.environ.get("ALPACA_SECRET_KEY") or s.get("alpaca_secret_key")
    if pref in ("alpaca", "paper") and key and sec and cfg.get("paper_trading"):
        return AlpacaPaper(key, sec)
    try:
        from .mt5_bridge import status as mt5_status
        if mt5_status()["connected"]:
            return MT5Demo()
    except Exception:
        pass
    return SimBroker(cfg)


class SimBroker:
    """File-backed simulator: fills at last close, tracks cash + positions."""

    name = "sim"

    def __init__(self, cfg):
        self.state = util.load_json(SIM_STATE, None) or {
            "cash": float(cfg.get("starting_cash", 10000)),
            "positions": {},   # symbol -> {qty, basis}
        }

    def _save(self):
        util.save_json(SIM_STATE, self.state)

    def equity(self, prices=None):
        total = self.state["cash"]
        for sym, pos in self.state["positions"].items():
            px = (prices or {}).get(sym)
            total += pos["qty"] * (px if px else pos["basis"])
        return round(total, 2)

    def positions(self):
        return {s: p["qty"] for s, p in self.state["positions"].items() if p["qty"] > 0}

    def position(self, symbol):
        return self.state["positions"].get(symbol, {}).get("qty", 0)

    def buy(self, symbol, qty, price, reason="", sl_pct=None, tp_pct=None,
            prob=None, params=None, strategy="auto"):
        cost = qty * price
        if cost > self.state["cash"]:
            qty = int(self.state["cash"] // price)
            if qty < 1:
                return {"ok": False, "error": "insufficient cash"}
        self.state["cash"] -= qty * price
        pos = self.state["positions"].setdefault(symbol, {"qty": 0, "basis": price})
        tot = pos["qty"] + qty
        pos["basis"] = (pos["basis"] * pos["qty"] + price * qty) / tot
        pos["qty"] = tot
        self._save()
        record_decision(util.iso(), symbol, "BUY", qty, price, self.name, reason)
        try:
            from .learner import capture
            capture(symbol, "buy", qty, price, mode=self.name, prob=prob,
                    params=params, reason=reason, sl_pct=sl_pct, strategy=strategy)
        except Exception:
            pass
        return {"ok": True, "filled_qty": qty, "price": price}

    def sell(self, symbol, qty, price, reason="", prob=None, params=None):
        pos = self.state["positions"].get(symbol)
        if not pos or pos["qty"] <= 0:
            return {"ok": False, "error": "no position"}
        qty = min(qty, pos["qty"])
        self.state["cash"] += qty * price
        pos["qty"] -= qty
        if pos["qty"] == 0:
            self.state["positions"].pop(symbol)
        self._save()
        record_decision(util.iso(), symbol, "SELL", qty, price, self.name, reason)
        try:
            from .learner import note_sim_exit
            note_sim_exit(symbol, qty, price)  # sim sells close ledger rows directly
        except Exception:
            pass
        return {"ok": True, "filled_qty": qty, "price": price}


class AlpacaPaper:
    """Alpaca PAPER REST client (stdlib+requests only). Paper-only by URL —
    this class cannot reach the live endpoint. Supports broker-side brackets
    (stop_loss/take_profit travel WITH the order, like the MT5 adapter)."""

    name = "alpaca-paper"
    BASE = "https://paper-api.alpaca.markets"  # paper only, hard-coded

    def __init__(self, key, secret):
        self.key, self.secret = key, secret

    def _req(self, method, path, body=None, params=None):
        import requests

        r = requests.request(method, self.BASE + path, json=body, params=params,
                             headers={"APCA-API-KEY-ID": self.key,
                                      "APCA-API-SECRET-KEY": self.secret},
                             timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"alpaca {method} {path}: {r.status_code} {r.text[:200]}")
        return r.json() if r.text else {}

    def equity(self, prices=None):
        e = float(self._req("GET", "/v2/account")["equity"])
        if e <= 0:
            raise RuntimeError("alpaca equity read failed (<=0)")
        return e

    def positions(self):
        out = {}
        for p in self._req("GET", "/v2/positions"):
            out[p["symbol"]] = float(p["qty"])
        return out

    def position(self, symbol):
        for s, q in self.positions().items():
            if s == symbol:
                return q
        return 0

    def _capture(self, symbol, side, qty, price, prob, params, reason, sl_pct, tp_pct, order):
        try:
            from .learner import capture
            capture(symbol, side, float(qty), float(price) if price else None,
                    mode=self.name, prob=prob, params=params, reason=reason,
                    sl_pct=sl_pct, tp_pct=tp_pct,
                    ticket=str(order.get("id", ""))[:18])
        except Exception:
            pass

    def buy(self, symbol, qty, price=None, reason="", sl_pct=None, tp_pct=None,
            prob=None, params=None, strategy="auto"):
        body = {"symbol": symbol, "qty": qty, "side": "buy", "type": "market",
                "time_in_force": "day"}
        # Broker-side bracket: SL/TP travel with the order (like the MT5 adapter).
        # Needs a reference price — the daily cycle always passes the last close.
        if sl_pct and price:
            body["order_class"] = "bracket"
            body["stop_loss"] = {"stop_price": round(price * (1 - sl_pct / 100.0), 2)}
            body["take_profit"] = {"limit_price": round(price * (1 + (tp_pct or 6.0) / 100.0), 2)}
        order = self._req("POST", "/v2/orders", body)
        record_decision(util.iso(), symbol, "BUY", qty, price or 0, self.name, reason)
        self._capture(symbol, "buy", qty, price, prob, params, reason, sl_pct, tp_pct, order)
        return {"ok": True, "order": order}

    def sell(self, symbol, qty, price=None, reason="", prob=None, params=None, strategy="auto"):
        order = self._req("POST", "/v2/orders", {
            "symbol": symbol, "qty": qty, "side": "sell", "type": "market",
            "time_in_force": "day"})
        record_decision(util.iso(), symbol, "SELL", qty, price or 0, self.name, reason)
        self._capture(symbol, "sell", qty, price, prob, params, reason, None, None, order)
        return {"ok": True, "order": order}


def secrets_template():
    return {
        "_comment": "Copy to secrets.json (gitignored). Groq for the agent; Alpaca for paper trading.",
        "groq_api_key": "",
        "github_token": "",
        "alpaca_key_id": "",
        "alpaca_secret_key": "",
    }
