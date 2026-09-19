"""Obsidian vault as JARVIS's long-term memory.

Writes plain markdown notes into the vault from .env (OBSIDIAN_VAULT_PATH,
default C:/Users/User/Documents/JARVIS-Memory). Each domain gets a subfolder;
all notes are timestamped so Obsidian's backlink graph can connect them.
Never raises — memory problems must not touch trading.
"""
from pathlib import Path

from . import util

DEFAULT_VAULT = Path.home() / "Documents" / "JARVIS-Memory"


def vault_root():
    from .llm import env
    p = env().get("OBSIDIAN_VAULT_PATH", "").strip()
    return Path(p) if p else DEFAULT_VAULT


def _write(folder, stem, body):
    try:
        d = vault_root() / folder
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{util.iso()[:10]}-{stem}.md"
        path.write_text(body, encoding="utf-8")
        return str(path)
    except OSError as e:
        util.log_event("MEMORY", f"obsidian write failed: {e}")
        return None


def decision_note(sym, action, qty, price, why):
    return _write("Decisions", f"{sym}-{action}", (
        f"---\ndate: {util.iso()}\ntype: decision\nsymbol: {sym}\n"
        f"action: {action}\nqty: {qty}\nprice: {price}\n---\n\n"
        f"# {sym} {action.upper()} @ {price}\n\n- qty: {qty}\n- price: {price}\n"
        f"- why: {why}\n"
    ))


def evolution_note(results):
    lines = [f"---\ndate: {util.iso()}\ntype: evolution\n---\n\n# Evolution pass\n"]
    for sym, r in results.items():
        lines.append(f"- **{sym}**: {r.get('status')} — {json_short(r)}")
    lines.append("")
    return _write("Evolutions", "pass", "\n".join(lines))


def daily_note(headline, body=""):
    return _write("Daily", "log", (
        f"---\ndate: {util.iso()}\ntype: daily\n---\n\n# {headline}\n\n{body}\n"
    ))


def chat_note(text, reply):
    snippet = lambda s: " ".join(str(s).split())[:200]
    return _write("Chats", "voice", f"> you: {snippet(text)}\n> jarvis: {snippet(reply)}\n")


def pnl_note(day):
    """Daily P&L journal entry. day = daily_pnl-style dict."""
    pl = day.get("realized", 0.0)
    emoji = "🟢" if pl >= 0 else "🔴"
    body = (
        f"---\ndate: {day.get('date')}\ntype: pnl\nmode: {day.get('mode')}\n---\n\n"
        f"# {emoji} {day.get('date')} — {pl:+.2f} {day.get('mode', '')}\n\n"
        f"- start equity: {day.get('start_equity')}\n- end equity: {day.get('end_equity')}\n"
        f"- realized: {pl}\n- trades: {day.get('trades')} (W {day.get('wins')} / L {day.get('losses')})\n"
    )
    return _write("Trading/Daily", f"pnl-{day.get('date')}", body)


def cycle_note(cycle):
    """Daily learn→predict→trade cycle summary. cycle = result dict from daily.run_cycle."""
    lines = [f"---\ndate: {util.iso()}\ntype: cycle\ntrigger: {cycle.get('trigger')}\n---\n\n",
             f"# Daily cycle — {cycle.get('status')}\n"]
    for sym, pred in (cycle.get("predictions") or {}).items():
        lines.append(f"- **{sym}**: {pred.get('action')} (p={pred.get('prob')}, {pred.get('reason', '')[:80]})")
    if cycle.get("orders"):
        for o in cycle["orders"]:
            lines.append(f"  - order: {o}")
    lines.append("")
    return _write("Trading/Cycles", "run", "\n".join(lines))


def json_short(d):
    import json
    try:
        return json.dumps(d, default=str)[:220]
    except (TypeError, ValueError):
        return str(d)[:220]
