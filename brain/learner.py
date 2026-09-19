"""The trade-learning agent: learns from EVERY trade.

Three jobs, run after each cycle (and on demand):
  capture()    — record every entry with full decision context (prob, params,
                 brackets, reason) into the `trades` ledger.
  reconcile()  — the ledger only knows exits the app placed itself. TP/SL and
                 manual closes happen broker-side, so closed deals are matched
                 back to open trades from MT5 deal history.
  reflect()    — every newly-closed round trip becomes a lesson (why it won or
                 lost, in which regime, at what cost). Lessons feed the
                 evolution agent's prompt and the Obsidian vault, so the
                 strategy improves from each trade instead of just each week.

Never raises to callers: learning must not touch trading.
"""
import json

from . import util
from . import mt5_bridge
from .store import (open_trades, closed_unreflected, recent_trades, recent_lessons,
                    record_trade, close_trade, mark_reflected, add_lesson,
                    decisions_for)


# ----------------------------------------------------------------- capture

def capture(sym, side, qty, price, ticket=None, mode="sim", prob=None,
            params=None, reason="", sl_pct=None, tp_pct=None, strategy="auto"):
    """Record an entry with its full decision context. Returns ledger row id."""
    try:
        tid = record_trade(
            opened_at=util.iso(), symbol=strategy_tag(sym, strategy), side=side,
            qty=qty, entry_price=price, ticket=ticket, mode=mode, prob=prob,
            params=json.dumps(params or {}, default=str), reason=reason,
            sl_pct=sl_pct, tp_pct=tp_pct, strategy=strategy,
        )
        util.log_event("LEARN", f"captured {sym} {side} {qty}@{price} (trade #{tid}, ticket {ticket})")
        return tid
    except Exception as e:
        util.log_event("LEARN", f"capture failed {sym}: {e}")
        return None


def strategy_tag(sym, strategy):
    return sym  # symbol stays clean; strategy lives in its own column


def _latest_gh_z(sym):
    try:
        from .store import gh_signal_history
        h = gh_signal_history(sym, 1)
        return h[0][2] if h else None
    except Exception:
        return None


# --------------------------------------------------------------- reconcile

def reconcile():
    """Match closed broker deals to open trades; close them in the ledger.

    Matching: prefer MT5 position ticket (order() records it), else fall back
    to same-symbol + same-qty open trade (FIFO). Returns summary dict.
    """
    closed = {"matched": 0, "still_open": 0, "unmatched_deals": 0}
    try:
        opens = open_trades()
        if not opens:
            return closed
        deals = mt5_bridge.deals(days=14) if mt5_bridge.available() else []
        if not deals:
            closed["still_open"] = len(opens)
            return closed
        used = set()  # deal indexes already consumed
        # index deals by symbol for speed
        by_sym = {}
        for i, d in enumerate(deals):
            by_sym.setdefault(d["symbol"], []).append(i)
        for t in opens:
            cands = [i for i in by_sym.get(t["symbol"], []) if i not in used]
            if not cands:
                closed["still_open"] += 1
                continue
            hit = None
            matched_by = None
            # 1) exact: closing deal's position_id == stored position ticket
            if t.get("ticket"):
                for i in cands:
                    if deals[i].get("position_id") == int(t["ticket"]):
                        hit, matched_by = i, "position_id"
                        break
            # 2) fallback: same symbol, same volume, first unconsumed
            if hit is None:
                for i in cands:
                    if abs(float(deals[i].get("volume") or 0) - float(t["qty"])) < 1e-9:
                        hit, matched_by = i, "volume"
                        break
            if hit is None:
                closed["still_open"] += 1
                continue
            d = deals[hit]
            used.add(hit)
            pnl = float(d.get("profit") or 0.0)
            exit_price = float(d.get("price") or 0.0)
            kind = _exit_kind(t, exit_price)
            ctx = {"close_deal_date": d.get("date"), "matched_by": matched_by}
            close_trade(t["id"], d.get("date") or util.iso(), exit_price,
                        round(pnl, 2), kind, json.dumps(ctx))
            closed["matched"] += 1
            util.log_event("LEARN", f"reconciled trade #{t['id']} {t['symbol']}: "
                                    f"pnl {pnl:+.2f} ({kind})")
        closed["unmatched_deals"] = len(deals) - len(used)
    except Exception as e:
        util.log_event("LEARN", f"reconcile failed: {e}")
    return closed


def _exit_kind(t, exit_price):
    """Classify how the trade left: tp / sl / manual, from brackets + prices."""
    entry = float(t.get("entry_price") or 0.0)
    if entry <= 0 or exit_price <= 0:
        return "closed"
    side = (t.get("side") or "buy").lower()
    moved = (exit_price - entry) / entry * 100.0
    if side == "sell":
        moved = -moved
    tp_pct = t.get("tp_pct")
    sl_pct = t.get("sl_pct")
    if tp_pct is not None and moved >= float(tp_pct) * 0.8:
        return "take_profit"
    if sl_pct is not None and moved <= -float(sl_pct) * 0.8:
        return "stop_loss"
    return "closed"


# ----------------------------------------------------------------- reflect

def reflect():
    """Turn unreflected closed trades into lessons. Returns count."""
    try:
        trades = closed_unreflected()
        for t in trades:
            try:
                _reflect_one(t)
            except Exception as e:
                util.log_event("LEARN", f"reflect trade #{t['id']} failed: {e}")
            mark_reflected(t["id"])
        return len(trades)
    except Exception as e:
        util.log_event("LEARN", f"reflect failed: {e}")
        return 0


def _reflect_one(t):
    sym = t["symbol"]
    pnl = float(t.get("pnl") or 0.0)
    kind = t.get("exit_kind") or "closed"
    prob = t.get("prob")
    params = t.get("params") or {}
    entry = float(t.get("entry_price") or 0.0)
    exitp = float(t.get("exit_price") or 0.0)
    move_pct = ((exitp - entry) / entry * 100.0) if entry > 0 and exitp > 0 else None
    win = pnl > 0
    ts = util.iso()

    parts = [f"{sym} {'WIN' if win else 'LOSS'} {pnl:+.2f}"]
    if prob is not None:
        parts.append(f"entry p={prob}")
    if move_pct is not None:
        parts.append(f"move {move_pct:+.2f}%")
    if t.get("sl_pct"):
        parts.append(f"bracket SL {t['sl_pct']}%")
    if t.get("tp_pct"):
        parts.append(f"TP {t['tp_pct']}%")
    summary = ", ".join(parts)

    # Lesson 1: the trade itself
    if kind == "take_profit":
        lesson = (f"{summary}. TP hit — the entry edge was real this time: "
                  f"prob-at-entry {prob} and params {params} are worth repeating "
                  f"for {sym}.")
        weight = 1.2
    elif kind == "stop_loss":
        lesson = (f"{summary}. Stopped out — entry {entry} was vulnerable to the "
                  f"4.5%-bracket noise band. If stop-outs cluster, raise the "
                  f"threshold or widen the stop within guardrails.")
        weight = 1.4  # losses teach more
    elif win:
        lesson = (f"{summary}. Manual/discretionary exit in profit — the move ran "
                  f"past our exit; consider trailing or wider TP if this repeats.")
        weight = 1.0
    else:
        lesson = (f"{summary}. Exited red before any bracket fired — spread plus "
                  f"adverse drift ate the trade; entries near session edges are suspect.")
        weight = 1.3
    add_lesson(ts, sym, lesson, json.dumps({"trade_id": t["id"], "exit_kind": kind})[:200],
               weight)

    # Lesson 2: rolling symbol stats (every 4 closed trades for the symbol)
    closed = [x for x in recent_trades(60, closed_only=True) if x["symbol"] == sym]
    if len(closed) % 4 == 0 and closed:
        wins = sum(1 for x in closed if float(x.get("pnl") or 0) > 0)
        total = round(sum(float(x.get("pnl") or 0) for x in closed), 2)
        hit = wins / len(closed) * 100.0
        verdict = ("edge is holding" if hit >= 55 and total > 0 else
                   "edge is marginal — evolution should challenge this symbol's params"
                   if hit >= 45 else
                   "edge is failing — tighten entries or stand this symbol down")
        add_lesson(ts, sym, (f"Rolling review of last {len(closed)} {sym} trades: "
                             f"{wins}W/{len(closed)-wins}L, hit-rate {hit:.0f}%, "
                             f"cumulative {total:+.2f}. {verdict}."),
                   "", 2.0)

    # Obsidian memory
    try:
        from .memory import _write
        _write("Trading/Lessons", f"trade-{t['id']}",
               f"---\ndate: {ts}\ntype: lesson\nsymbol: {sym}\n"
               f"pnl: {pnl}\nexit: {kind}\n---\n\n{lesson}\n")
    except Exception as e:
        util.log_event("LEARN", f"obsidian lesson failed: {e}")


def note_sim_exit(symbol, qty, price):
    """Sim fills are app-side, so sells close their ledger rows directly (FIFO)."""
    try:
        remaining = float(qty)
        for t in open_trades():
            if remaining <= 0:
                break
            if t["symbol"] != symbol or (t.get("side") or "buy") != "buy":
                continue
            vol = min(remaining, float(t["qty"]))
            entry = float(t["entry_price"] or 0.0)
            pnl = round((float(price) - entry) * vol, 2)
            close_trade(t["id"], util.iso(), float(price), pnl, "closed",
                        json.dumps({"sim_exit": True, "partial": vol < float(t["qty"])}))
            remaining -= vol
            util.log_event("LEARN", f"sim exit ledgered {symbol}: pnl {pnl:+.2f}")
        return True
    except Exception as e:
        util.log_event("LEARN", f"sim exit ledger failed: {e}")
        return False


# ------------------------------------------------------------------ summary

def stats():
    """Aggregate learning stats for the UI / evolution prompt."""
    closed = recent_trades(60, closed_only=True)
    opens = open_trades()
    wins = [t for t in closed if float(t.get("pnl") or 0) > 0]
    losses = [t for t in closed if float(t.get("pnl") or 0) <= 0]
    total = round(sum(float(t.get("pnl") or 0) for t in closed), 2)
    by_kind = {}
    for t in closed:
        k = t.get("exit_kind") or "closed"
        by_kind.setdefault(k, {"n": 0, "pnl": 0.0})
        by_kind[k]["n"] += 1
        by_kind[k]["pnl"] = round(by_kind[k]["pnl"] + float(t.get("pnl") or 0), 2)
    return {
        "closed": len(closed),
        "open": len(opens),
        "wins": len(wins),
        "losses": len(losses),
        "hit_rate_pct": round(len(wins) / len(closed) * 100, 1) if closed else None,
        "cumulative_pnl": total,
        "by_exit_kind": by_kind,
        "lessons": recent_lessons(12),
    }
