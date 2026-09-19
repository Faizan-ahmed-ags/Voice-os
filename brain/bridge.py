"""Local HTTP bridge: dashboard UI <-> JARVIS brain (stdlib only, no deps).

Start with:  python -m brain.bridge            (default port 8765)
Serves JSON API on 127.0.0.1 only. The Vite dev server proxies /api here.
"""
import base64
import json
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import util
from . import config as cfgmod
from .brokers import get_broker
from .store import (clear_chats, get_memory, recent_chats, recent_decisions,
                    recent_webhooks, save_chat, save_webhook)

LOCK = threading.Lock()  # brain ops are not thread-safe; serialize them


def _fmt_money(x):
    return f"${x:,.2f}"


# ------------------------------------------------------------- command router

def cmd_status_text():
    cfg = cfgmod.load()
    broker = get_broker(cfg)
    lines = [f"Mode: {broker.name}. Portfolio equity {_fmt_money(broker.equity())}."]
    pos = broker.positions()
    if pos:
        lines.append("Open positions: " + ", ".join(f"{s} x{int(q)}" for s, q in pos.items()) + ".")
    else:
        lines.append("No open positions.")
    champs = []
    for sym in cfg["universe"]:
        m = get_memory(f"champion:{sym}")
        if m:
            champs.append(f"{sym} {m['status']} (AUC {m['cv']['auc_mean']:.2f})")
    lines.append("Models: " + ("; ".join(champs) if champs else "none trained yet."))
    return " ".join(lines)


def cmd_halal_text():
    cfg = cfgmod.load()
    from .halal import screen_universe
    res = screen_universe(cfg["universe"])
    lines = [f"{s}: {'PASS' if r['compliant'] else 'FAIL'} — {r['reason']}"
             for s, r in res.items()]
    return "Halal screen. " + " ".join(lines)


def cmd_train_text():
    cfg = cfgmod.load()
    from .model import train_model
    parts = []
    for sym in cfg["universe"]:
        out = train_model(sym)
        m = out["meta"]
        parts.append(f"{sym} {m['status']} AUC {m['cv']['auc_mean']:.3f}")
    return "Training complete. " + "; ".join(parts) + "."


def cmd_evolve_text():
    cfg = cfgmod.load()
    from .agent import review_and_evolve
    res = review_and_evolve(cfg, cfg["universe"])
    parts = []
    for sym, r in res.items():
        s = f"{sym}: {r['status']}"
        if "challenger_return" in r and r["challenger_return"] is not None:
            s += f" (challenger {r['challenger_return']}% vs incumbent {r['incumbent_return']}%)"
        if r.get("why"):
            s += f" — {r['why']}"
        parts.append(s)
    return "Evolution pass done. " + " | ".join(parts)


def cmd_decisions_text():
    ds = recent_decisions(5)
    if not ds:
        return "No trades yet. The brain trades only when a model passes the AUC edge gate and the halal screen."
    return "Recent decisions: " + "; ".join(
        f"{d['ts']} {d['symbol']} {d['action']} {d['qty']} @ {d['price']}" for d in ds)


def cmd_status_json():
    cfg = cfgmod.load()
    broker = get_broker(cfg)
    models = {}
    for sym in cfg["universe"]:
        m = get_memory(f"champion:{sym}")
        if m:
            models[sym] = {"status": m.get("status"), "auc_mean": m["cv"]["auc_mean"],
                           "acc_mean": m["cv"]["acc_mean"], "train_end": m.get("train_end")}
    pos = broker.positions()
    sim_state = util.load_json(util.DATA_DIR / "sim_state.json", {}) or {}
    positions = [{"symbol": s, "qty": q,
                  "basis": round(sim_state.get("positions", {}).get(s, {}).get("basis", 0), 2)}
                 for s, q in pos.items()]
    return {
        "mode": broker.name,
        "paper": broker.name != "alpaca-live",
        "equity": broker.equity(),
        "positions": positions,
        "models": models,
        "last_decisions": list(reversed(recent_decisions(10))),
        "last_evolution": get_memory("last_evolution"),
    }


def cmd_trades_text():
    return cmd_decisions_text()


# ------------------------------------------------------------- v2 JSON feeds

def cmd_agent_json():
    ev = get_memory("last_evolution") or {}
    lines = []
    try:
        with open(util.LOG_PATH, "r", encoding="utf-8") as f:
            lines = [ln.rstrip() for ln in f.readlines()[-80:]]
    except OSError:
        pass
    from .learner import stats
    from .store import recent_trades
    return {"last_evolution": ev, "activity": lines,
            "learning": stats(),
            "trades": recent_trades(12)}


def cmd_plan_json():
    from .plan import plan_snapshot
    return plan_snapshot()


def cmd_news_json():
    cfg = cfgmod.load()
    from .news import daily_news
    return daily_news(cfg["universe"])


def cmd_trades_json():
    cfg = cfgmod.load()
    broker = get_broker(cfg)
    sim_state = util.load_json(util.DATA_DIR / "sim_state.json", {}) or {}
    return {
        "decisions": list(reversed(recent_decisions(100))),
        "equity": broker.equity(),
        "mode": broker.name,
        "positions": sim_state.get("positions", {}),
    }


def cmd_positions_json():
    """Live open positions with real P&L (MT5) + ledger context."""
    cfg = cfgmod.load()
    from .mt5_bridge import positions as mt5_positions
    ledger = {t["symbol"]: t for t in store_open_trades()}
    out = []
    for sym, vol in mt5_positions().items():
        lt = ledger.get(sym, {})
        out.append({"symbol": sym, "qty": vol, "strategy": lt.get("strategy", "manual"),
                    "reason": (lt.get("reason") or "")[:160],
                    "opened_at": lt.get("opened_at"), "entry": lt.get("entry_price")})
    return {"positions": out, "broker": "mt5-demo" if out else None}


def store_open_trades():
    from .store import open_trades
    return open_trades()


def cmd_manual_order(payload):
    """Manual buy/sell from the UI. Same halal + risk gates as the cycle."""
    sym = str(payload.get("symbol", "")).upper().strip()
    side = str(payload.get("side", "")).lower().strip()
    if side not in ("buy", "sell"):
        return {"ok": False, "error": "side must be buy or sell"}
    if not sym:
        return {"ok": False, "error": "symbol required"}
    if sym not in cfgmod.load()["universe"]:
        return {"ok": False, "error": f"{sym} not in the trading universe"}
    from .halal import screen_symbol
    if not screen_symbol(sym).get("compliant"):
        return {"ok": False, "error": f"{sym} failed the halal screen"}
    cfg = cfgmod.load()
    from .brokers import get_broker
    broker = get_broker(cfg)
    try:
        equity = broker.equity()
    except Exception as e:
        return {"ok": False, "error": f"equity unavailable — {e}"}
    from .mt5_bridge import symbol_info as mt5_symbol_info
    price = mt5_symbol_info(sym)
    if not price:
        return {"ok": False, "error": "no live price — market closed or symbol unknown"}
    if side == "buy":
        from .risk import check_order
        allowed, qty, why = check_order(equity, price, "buy")
        if not allowed:
            return {"ok": False, "error": why}
        res = broker.buy(sym, qty, price, "manual order (UI)", sl_pct=4.5,
                         tp_pct=6.0, strategy="manual")
        if res.get("ok"):
            from .memory import decision_note
            decision_note(sym, "buy", res.get("filled_qty", qty), price,
                          "manual order (UI)")
        return res
    pos = broker.position(sym)
    if pos <= 0:
        return {"ok": False, "error": f"no open {sym} position to sell"}
    res = broker.sell(sym, pos, price, "manual close (UI)", strategy="manual")
    return res


def cmd_chart_json(q=None):
    """Candles + ALL journal/ledger trade markers for the chart page."""
    cfg = cfgmod.load()
    sym = (q or {}).get("symbol", cfg["universe"][0]).upper()
    tf = (q or {}).get("tf", "1D")
    if sym not in cfg["universe"]:
        return {"symbol": sym, "candles": [], "markers": [],
                "error": "not in universe"}
    from .mt5_bridge import candles as mt5_candles
    from .store import recent_trades
    candles = mt5_candles(sym, tf, 400)
    if not candles:
        try:
            from .data_feed import get_prices
            df = get_prices(sym)
            for _, r in df.tail(400).iterrows():
                ts = int(getattr(r.name, "timestamp", lambda: 0)())
                candles.append({"t": ts, "o": float(r["Open"]), "h": float(r["High"]),
                                "l": float(r["Low"]), "c": float(r["Close"])})
        except Exception:
            pass
    times = [c["t"] for c in candles]
    markers = []
    import bisect
    for tr in recent_trades(300):
        if tr["symbol"] != sym:
            continue
        px = tr.get("entry_price")
        for when, kind in ((tr["opened_at"], "entry"),
                           (tr.get("closed_at"), "exit")):
            if not when or px is None:
                continue
            try:
                from .util import parse_iso
                t = int(parse_iso(when).timestamp())
            except Exception:
                continue
            if not times or t < times[0]:
                continue
            # Snap the trade onto the candle that covers it: a 19:52 entry
            # belongs on the Sep-18 daily bar, not off the right edge.
            idx = bisect.bisect_right(times, t) - 1
            snapped = times[max(idx, 0)]
            markers.append({"t": snapped, "ts": t, "price": px, "kind": kind,
                            "side": tr["side"], "qty": tr["qty"],
                            "strategy": tr.get("strategy", "auto"),
                            "pnl": tr.get("pnl"),
                            "reason": (tr.get("reason") or "")[:140]})
    return {"symbol": sym, "tf": tf, "candles": candles, "markers": markers}


def cmd_journal_json(q=None):
    """Daily journal: one story per day from P&L + trades + cycles + lessons."""
    from .store import pnl_month, recent_trades, last_cycles
    from .util import utcnow
    now = utcnow()
    month = (q or {}).get("month") or now.strftime("%Y-%m")
    try:
        year, mon = int(month[:4]), int(month[5:7])
    except (ValueError, IndexError):
        return {"month": month, "days": []}
    month_data = pnl_month(year, mon)
    total = sum(float(d.get("realized") or 0) for d in month_data)
    green_days = sum(1 for d in month_data if float(d.get("realized") or 0) > 0)
    red_days = sum(1 for d in month_data if float(d.get("realized") or 0) < 0)
    by_day = {}
    for tr in recent_trades(400):
        day = (tr["opened_at"] or "")[:10]
        by_day.setdefault(day, []).append(tr)
    cycles_by_day = {}
    for c in last_cycles(200):
        day = (c.get("ts") or "")[:10]
        cycles_by_day[day] = c
    from .store import recent_lessons
    lessons = recent_lessons(30)
    lessons_by_day = {}
    for l in lessons:
        lessons_by_day.setdefault((l.get("ts") or "")[:10], []).append(l)
    days = []
    from .store import pnl_day
    for row in month_data:
        d = dict(row)
        day = d["date"]
        trades = by_day.get(day, [])
        if not trades and int(d.get("trades") or 0) > 0:
            # Ledger predates these trades — fall back to the decisions table.
            pd = pnl_day(day)
            trades = [{"opened_at": x["ts"], "symbol": x["symbol"],
                       "side": x["action"].lower(), "qty": x["qty"],
                       "entry_price": x["price"], "exit_price": None,
                       "pnl": None, "strategy": "seed", "exit_kind": None,
                       "reason": x.get("reason") or ""}
                      for x in (pd or {}).get("trades_detail", [])
                      if x["action"] in ("BUY", "SELL")]
        d["trade_rows"] = [{"time": (t["opened_at"] or "")[11:16], "symbol": t["symbol"],
                            "side": t["side"], "qty": t["qty"],
                            "entry": t["entry_price"], "exit": t.get("exit_price"),
                            "pnl": t.get("pnl"), "strategy": t.get("strategy"),
                            "exit_kind": t.get("exit_kind"),
                            "reason": (t.get("reason") or "")[:200]} for t in trades]
        c = cycles_by_day.get(day)
        d["cycle"] = {"trigger": c.get("trigger"), "orders": c.get("orders_placed")} if c else None
        d["lessons"] = [l.get("lesson") for l in lessons_by_day.get(day, [])]
        d["verdict"] = ("great" if d["realized"] > 0 else "down" if d["realized"] < 0
                        else "flat") if d["trades"] else "quiet"
        days.append(d)
    days.sort(key=lambda x: x["date"], reverse=True)
    return {"month": month, "days": days, "total": round(total, 2),
            "green_days": green_days, "red_days": red_days}


def cmd_connections_json():
    from .connections import connections_status
    return connections_status()


def cmd_llm_json():
    from .llm import health
    return health()


def cmd_pnl_json(q=None):
    from .store import pnl_month, pnl_day
    from . import risk
    q = q or {}
    today = util.utcnow().strftime("%Y-%m-%d")
    ref = q.get("month") or today[:7]
    try:
        year, month = int(ref[:4]), int(ref[5:7])
    except (ValueError, IndexError):
        year, month = int(today[:4]), int(today[5:7])
    days = pnl_month(year, month)
    total = round(sum(d["realized"] for d in days), 2)
    green = sum(1 for d in days if d["realized"] > 0)
    red = sum(1 for d in days if d["realized"] < 0)
    day_detail = pnl_day(q["day"]) if q.get("day") else None
    st = risk.day_state((days[-1]["end_equity"] if days else 10000.0))
    return {"month": f"{year:04d}-{month:02d}", "days": days, "total": total,
            "green_days": green, "red_days": red,
            "day": day_detail, "today_state": {k: v for k, v in st.items() if k != "_guard"}}


def cmd_cycle_json():
    from .daily import status
    return status()


def cmd_mt5_json():
    from .mt5_bridge import status, symbols_all, creds
    st = status()
    c = creds()
    st["creds_set"] = bool(c["login"] and c["password"] and c["server"])
    st["broker_symbols_sample"] = symbols_all()[:40] if st["connected"] else []
    return st


def self_path():
    # helper for query parsing inside cmd_pnl_json (no request context here)
    return globals().get("_LAST_QUERY", "")


def cmd_models_json():
    cfg = cfgmod.load()
    from .coinmodel import status as coin_status
    models = {}
    for sym in cfg["universe"]:
        m = get_memory(f"champion:{sym}")
        if m:
            models[sym] = {"status": m.get("status"),
                           "auc_mean": m["cv"]["auc_mean"],
                           "train_end": m.get("train_end")}
    out = coin_status()
    out["builtin"] = models
    return out


ROUTES = [
    (re.compile(r"(portfolio|status|equity|how much|worth|balance|positions)", re.I), cmd_status_text),
    (re.compile(r"(halal|compliance|compliant|shariah|screen)", re.I), cmd_halal_text),
    (re.compile(r"(train|retrain|model)", re.I), cmd_train_text),
    (re.compile(r"(evolve|improve|self.?improve|learn|grow)", re.I), cmd_evolve_text),
    (re.compile(r"(trade|decision|history|bought|sold)", re.I), cmd_decisions_text),
]


def route(text):
    for rx, fn in ROUTES:
        if rx.search(text):
            return fn()
    return ("I can answer: portfolio status, halal screen, train models, "
            "evolve strategies, trade history.")


# ------------------------------------------------------------------ HTTP hero

class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quiet
        pass

    # -------------------------------------------------- v2 GET endpoints

    def _api_get(self):
        """Dispatch /api/* GETs; returns True when handled."""
        p = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(p.query))
        route_map = {
            "/api/status": lambda: cmd_status_json(),
            "/api/agent": cmd_agent_json,
            "/api/plan": cmd_plan_json,
            "/api/news": cmd_news_json,
            "/api/trades": cmd_trades_json,
            "/api/chats": lambda: {"chats": recent_chats(300)},
            "/api/connections": cmd_connections_json,
            "/api/llm": cmd_llm_json,
            "/api/models": cmd_models_json,
            "/api/webhooks": lambda: {"webhooks": recent_webhooks(20)},
            "/api/pnl": lambda: cmd_pnl_json(q),
            "/api/cycle": cmd_cycle_json,
            "/api/mt5": cmd_mt5_json,
            "/api/positions": cmd_positions_json,
            "/api/chart": lambda: cmd_chart_json(q),
            "/api/journal": lambda: cmd_journal_json(q),
        }
        fn = route_map.get(p.path)
        if not fn:
            return False
        with LOCK:
            self._json(200, fn())
        return True

    def do_GET(self):
        try:
            if self.path.startswith("/api/"):
                if not self._api_get():
                    self._json(404, {"error": "not found"})
            else:
                code, ctype, body = serve_static(self.path)
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except Exception as e:
            util.log_event("BRIDGE", f"GET error on {self.path}: {e}")
            try:
                self._json(500, {"error": str(e)})
            except Exception:
                pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n or 0)
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            payload = {"raw": raw[:2000].decode("utf-8", "replace")}
        try:
            if self.path == "/api/ask":
                text = str(payload.get("text", ""))[:500]
                with LOCK:
                    reply = route(text)
                source = "local"
                if reply.startswith("I can answer:"):
                    # No rule matched — let the LLM brain answer freeform.
                    from . import llm
                    ans, prov = llm.chat(
                        [{"role": "system",
                          "content": "You are JARVIS, the user's local trading assistant. "
                                     "Answer in two short sentences maximum. You manage a "
                                     "halal paper portfolio (MSFT, NVDA). Be factual; no "
                                     "financial advice."},
                         {"role": "user", "content": text}],
                        json_mode=False, temperature=0.4, timeout=90)
                    if ans:
                        reply = ans.strip()
                        source = prov
                save_chat("you", text, page="home")
                save_chat("jarvis", reply, page="home")
                try:
                    from .memory import chat_note
                    chat_note(text, reply)
                except Exception:
                    pass
                self._json(200, {"reply": reply, "source": source})
            elif self.path == "/api/screen":
                with LOCK:
                    self._json(200, {"reply": cmd_halal_text()})
            elif self.path == "/api/train":
                with LOCK:
                    self._json(200, {"reply": cmd_train_text()})
                save_chat("jarvis", "retrained models on request", page="home")
            elif self.path == "/api/evolve":
                with LOCK:
                    self._json(200, {"reply": cmd_evolve_text()})
                save_chat("jarvis", "ran an evolution pass on request", page="home")
            elif self.path == "/api/chats/clear":
                with LOCK:
                    clear_chats()
                self._json(200, {"ok": True})
            elif self.path == "/api/webhook":
                self._handle_webhook(payload)
            elif self.path == "/api/models/coin":
                self._handle_coin_upload(payload)
            elif self.path == "/api/models/coin/delete":
                from .coinmodel import remove
                with LOCK:
                    remove(str(payload.get("name", "")))
                self._json(200, {"ok": True})
            elif self.path == "/api/mt5/creds":
                from .llm import set_env
                ok_all = True
                for k in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"):
                    v = str(payload.get(k.lower().replace("mt5_", ""), "") or "").strip()
                    if v:
                        ok_all = set_env(k, v) and ok_all
                if payload.get("test"):
                    from .mt5_bridge import connect, shutdown
                    with LOCK:
                        ok, info = connect()
                        if not ok:
                            shutdown()
                    self._json(200, {"ok": ok_all, "connected": ok,
                                     "account": info if ok else None,
                                     "error": None if ok else info})
                else:
                    self._json(200, {"ok": ok_all})
            elif self.path == "/api/manual/order":
                with LOCK:
                    self._json(200, cmd_manual_order(payload))
            elif self.path == "/api/cycle/run":
                from .daily import run_cycle
                with LOCK:
                    res = run_cycle(trigger="manual")
                self._json(200, res)
            elif self.path == "/api/learner/reconcile":
                from .learner import reconcile, reflect
                with LOCK:
                    rec = reconcile()
                    lessons = reflect()
                self._json(200, {"ok": True, **rec, "lessons": lessons})
            elif self.path == "/api/learner/run":
                from .learner import reconcile, reflect, stats
                with LOCK:
                    reconcile()
                    n = reflect()
                self._json(200, {"ok": True, **stats(), "new_lessons": n})
            else:
                self._json(404, {"error": "not found"})
        except Exception as e:
            util.log_event("BRIDGE", f"error on {self.path}: {e}")
            self._json(500, {"error": str(e)})

    def _handle_webhook(self, payload):
        """TradingView-style alert receiver: log + paper-record if halal."""
        from .llm import env
        secret = env().get("TRADINGVIEW_WEBHOOK_SECRET", "").strip()
        if secret and secret != "your_generated_secret":
            supplied = (self.headers.get("X-Webhook-Secret")
                        or str(payload.get("secret") or payload.get("passphrase") or ""))
            if supplied != secret:
                util.log_event("WEBHOOK", "rejected: bad or missing secret")
                self._json(401, {"ok": False, "error": "bad webhook secret"})
                return
        source = "tradingview"
        symbol = str(payload.get("symbol") or payload.get("ticker") or "").upper()
        action = str(payload.get("action") or payload.get("side") or "alert").lower()
        save_webhook(source, payload)
        recorded = None
        if symbol and action in ("buy", "sell"):
            sym = symbol.split(":")[-1]
            from .halal import screen_symbol
            screen = screen_symbol(sym)
            if screen.get("compliant"):
                from .store import record_decision
                price = float(payload.get("price") or 0.0)
                why = f"webhook alert: {json.dumps(payload)[:180]}"
                record_decision(util.iso(), sym, action, 0.0, price, "webhook-paper", why)
                try:
                    from .memory import decision_note
                    decision_note(sym, action, 0.0, price, why)
                except Exception:
                    pass
                recorded = "paper decision recorded"
            else:
                recorded = f"ignored: {screen.get('reason')}"
        util.log_event("WEBHOOK", f"{source}: {json.dumps(payload)[:180]}")
        self._json(200, {"ok": True, "recorded": recorded})

    def _handle_coin_upload(self, payload):
        """Accepts {filename, data_b64} and stores into data/custom_models/."""
        filename = str(payload.get("filename") or "")
        data_b64 = str(payload.get("data_b64") or "")
        if not filename or not data_b64:
            self._json(400, {"error": "need filename + data_b64"})
            return
        if len(data_b64) > 60 * 1024 * 1024:
            self._json(413, {"error": "file too large (>45MB)"})
            return
        from .coinmodel import save_upload
        with LOCK:
            stored = save_upload(filename, base64.b64decode(data_b64))
        save_chat("system", f"coin model uploaded: {stored}", page="brain")
        self._json(200, {"ok": True, "stored": stored})


DIST = util.ROOT / "dashboard" / "dist"
MIME = {"": "text/html", ".html": "text/html", ".js": "text/javascript",
        ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png",
        ".ico": "image/x-icon", ".woff2": "font/woff2"}


def serve_static(path):
    """Serve the built dashboard (dashboard/dist) with SPA fallback."""
    rel = path.lstrip("/") or "index.html"
    target = (DIST / rel).resolve()
    if not str(target).startswith(str(DIST.resolve())) or not target.is_file():
        target = DIST / "index.html"
    if not target.is_file():
        return 501, "text/plain", ("dashboard not built — run: cd dashboard && npm run build").encode()
    ext = target.suffix
    return 200, MIME.get(ext, "application/octet-stream"), target.read_bytes()


class DualHandler(Handler):
    """Kept for compatibility: Handler now serves API + static dashboard."""

    pass


def main():
    port = 8765
    srv = ThreadingHTTPServer(("127.0.0.1", port), DualHandler)
    util.log_event("BRIDGE", f"listening on 127.0.0.1:{port}")
    print(f"JARVIS console on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
