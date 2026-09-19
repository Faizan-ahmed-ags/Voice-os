"""SQLite persistence for memory, model registry, decisions, GitHub signal."""
import json
import sqlite3

from .util import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    created_at TEXT NOT NULL,
    train_start TEXT NOT NULL,
    train_end TEXT NOT NULL,
    metrics TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    mode TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gh_signal (
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    raw INTEGER NOT NULL,
    z REAL,
    PRIMARY KEY (ts, symbol)
);
"""


def connect():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=15)  # wait out writer locks (bridge + learner + terminal scripts)
    conn.executescript(SCHEMA)
    return conn


def get_memory(key, default=None):
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM memory WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default
    finally:
        conn.close()


def set_memory(key, value):
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO memory(key,value,updated_at) VALUES(?,?,datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, json.dumps(value)),
        )
        conn.commit()
    finally:
        conn.close()


def record_decision(ts, symbol, action, qty, price, mode, reason):
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO decisions(ts,symbol,action,qty,price,mode,reason) VALUES(?,?,?,?,?,?,?)",
            (ts, symbol, action, qty, price, mode, reason),
        )
        conn.commit()
    finally:
        conn.close()


def recent_decisions(limit=20):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT ts,symbol,action,qty,price,mode,reason FROM decisions "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(zip(("ts", "symbol", "action", "qty", "price", "mode", "reason"), r)) for r in rows]
    finally:
        conn.close()


def decisions_for(symbol, limit=30):
    """Recent decisions for one symbol, oldest first (context capture helper)."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT ts,symbol,action,qty,price,mode,reason FROM decisions "
            "WHERE symbol=? ORDER BY id DESC LIMIT ?", (symbol, limit)
        ).fetchall()
        return list(reversed([dict(zip(("ts", "symbol", "action", "qty", "price", "mode", "reason"), r))
                              for r in rows]))
    finally:
        conn.close()


def save_gh_signal(ts, symbol, raw, z):
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO gh_signal(ts,symbol,raw,z) VALUES(?,?,?,?)",
            (ts, symbol, raw, z),
        )
        conn.commit()
    finally:
        conn.close()


def gh_signal_history(symbol, limit=60):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT ts, raw, z FROM gh_signal WHERE symbol=? ORDER BY ts DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return list(reversed(rows))
    finally:
        conn.close()


# ------------------------------------------------- v2 tables: chats, webhooks

V2_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    page TEXT DEFAULT 'home'
);
CREATE TABLE IF NOT EXISTS webhook_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


def ensure_v2_tables():
    conn = connect()
    try:
        conn.executescript(V2_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def save_chat(kind, text, page="home"):
    ensure_v2_tables()
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO chats(ts,kind,text,page) VALUES(?,?,?,?)",
            (util_iso_now(), kind, str(text)[:2000], page),
        )
        conn.commit()
    finally:
        conn.close()


def recent_chats(limit=200):
    ensure_v2_tables()
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT ts,kind,text,page FROM chats ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return list(reversed([dict(zip(("ts", "kind", "text", "page"), r)) for r in rows]))
    finally:
        conn.close()


def clear_chats():
    ensure_v2_tables()
    conn = connect()
    try:
        conn.execute("DELETE FROM chats")
        conn.commit()
    finally:
        conn.close()


def save_webhook(source, payload):
    ensure_v2_tables()
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO webhook_log(ts,source,payload) VALUES(?,?,?)",
            (util_iso_now(), source, json.dumps(payload, default=str)[:4000]),
        )
        conn.commit()
    finally:
        conn.close()


def recent_webhooks(limit=20):
    ensure_v2_tables()
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT ts,source,payload FROM webhook_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return list(reversed([dict(zip(("ts", "source", "payload"), r)) for r in rows]))
    finally:
        conn.close()


def util_iso_now():
    from .util import iso
    return iso()


# ------------------------------------------------- v3 tables: pnl, cycles

V3_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_pnl (
    date TEXT PRIMARY KEY,
    start_equity REAL NOT NULL,
    end_equity REAL NOT NULL,
    realized REAL NOT NULL,
    unrealized REAL DEFAULT 0,
    trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    mode TEXT DEFAULT 'sim',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cycle_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    symbols_scanned INTEGER DEFAULT 0,
    orders_placed INTEGER DEFAULT 0,
    predictions TEXT DEFAULT '{}',
    notes TEXT DEFAULT ''
);
"""


def _ensure(schema):
    conn = connect()
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()


def ensure_v3_tables():
    _ensure(V3_SCHEMA)


def upsert_daily_pnl(date, start_equity, end_equity, realized=0.0, unrealized=0.0,
                     trades=0, wins=0, losses=0, mode="sim"):
    ensure_v3_tables()
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO daily_pnl(date,start_equity,end_equity,realized,unrealized,"
            "trades,wins,losses,mode,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET end_equity=excluded.end_equity, "
            "realized=excluded.realized, unrealized=excluded.unrealized, "
            "trades=excluded.trades, wins=excluded.wins, losses=excluded.losses, "
            "mode=excluded.mode, updated_at=excluded.updated_at",
            (date, start_equity, end_equity, realized, unrealized, trades, wins,
             losses, mode, util_iso_now()))
        conn.commit()
    finally:
        conn.close()


def pnl_month(year, month):
    ensure_v3_tables()
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT date,start_equity,end_equity,realized,unrealized,trades,wins,losses,mode "
            "FROM daily_pnl WHERE date LIKE ? ORDER BY date", (f"{year:04d}-{month:02d}-%",)
        ).fetchall()
        return [dict(zip(("date", "start_equity", "end_equity", "realized", "unrealized",
                          "trades", "wins", "losses", "mode"), r)) for r in rows]
    finally:
        conn.close()


def pnl_day(date):
    ensure_v3_tables()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT date,start_equity,end_equity,realized,unrealized,trades,wins,losses,mode "
            "FROM daily_pnl WHERE date=?", (date,)).fetchone()
        if not row:
            return None
        d = dict(zip(("date", "start_equity", "end_equity", "realized", "unrealized",
                      "trades", "wins", "losses", "mode"), row))
        trades = conn.execute(
            "SELECT ts,symbol,action,qty,price,mode,reason FROM decisions "
            "WHERE ts LIKE ? ORDER BY id", (f"{date}%",)).fetchall()
        d["trades_detail"] = [dict(zip(("ts", "symbol", "action", "qty", "price", "mode", "reason"), t))
                              for t in trades]
        return d
    finally:
        conn.close()


def record_cycle(trigger, status, symbols_scanned=0, orders_placed=0,
                 predictions=None, notes=""):
    ensure_v3_tables()
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO cycle_runs(ts,trigger,status,symbols_scanned,orders_placed,"
            "predictions,notes) VALUES(?,?,?,?,?,?,?)",
            (util_iso_now(), trigger, status, symbols_scanned, orders_placed,
             json.dumps(predictions or {}, default=str)[:3000], notes[:500]))
        conn.commit()
        rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return rid
    finally:
        conn.close()


def last_cycles(limit=10):
    ensure_v3_tables()
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT ts,trigger,status,symbols_scanned,orders_placed,predictions,notes "
            "FROM cycle_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(zip(("ts", "trigger", "status", "symbols_scanned", "orders_placed",
                          "predictions", "notes"), r))
            try:
                d["predictions"] = json.loads(d["predictions"])
            except (ValueError, TypeError):
                pass
            out.append(d)
        return out
    finally:
        conn.close()


def last_cycle():
    c = last_cycles(1)
    return c[0] if c else None


# ------------------------------------------------- v4 tables: trades, lessons

V4_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL DEFAULT 'buy',
    qty REAL NOT NULL,
    entry_price REAL NOT NULL,
    ticket INTEGER,
    mode TEXT NOT NULL DEFAULT 'sim',
    prob REAL,
    params TEXT DEFAULT '{}',
    reason TEXT DEFAULT '',
    sl_pct REAL,
    tp_pct REAL,
    closed_at TEXT,
    exit_price REAL,
    pnl REAL,
    exit_kind TEXT,
    strategy TEXT DEFAULT 'auto',
    reflected INTEGER DEFAULT 0,
    exit_ctx TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol, closed_at);
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    scope TEXT NOT NULL,
    lesson TEXT NOT NULL,
    evidence TEXT DEFAULT '',
    weight REAL DEFAULT 1.0
);
"""

_T_SELECT = ("SELECT id,opened_at,symbol,side,qty,entry_price,ticket,mode,prob,params,"
             "reason,sl_pct,tp_pct,closed_at,exit_price,pnl,exit_kind,strategy,"
             "reflected,exit_ctx FROM trades")


def ensure_v4_tables():
    _ensure(V4_SCHEMA)
    # Migrations for ledgers created before a column existed — SQLite's
    # CREATE TABLE IF NOT EXISTS never alters existing tables.
    conn = connect()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()}
        for name, ddl in (("strategy", "TEXT DEFAULT 'auto'"),
                          ("reflected", "INTEGER DEFAULT 0"),
                          ("exit_ctx", "TEXT DEFAULT '{}'")):
            if name not in cols:
                conn.execute(f"ALTER TABLE trades ADD COLUMN {name} {ddl}")
        conn.commit()
    finally:
        conn.close()


def _trade_row(r):
    d = dict(zip(("id", "opened_at", "symbol", "side", "qty", "entry_price", "ticket",
                  "mode", "prob", "params", "reason", "sl_pct", "tp_pct", "closed_at",
                  "exit_price", "pnl", "exit_kind", "strategy", "reflected", "exit_ctx"), r))
    try:
        d["params"] = json.loads(d["params"] or "{}")
    except (ValueError, TypeError):
        pass
    return d


def record_trade(opened_at, symbol, side="buy", qty=0.0, entry_price=0.0,
                 ticket=None, mode="sim", prob=None, params="{}", reason="",
                 sl_pct=None, tp_pct=None, strategy="auto"):
    """Insert a trade with its full decision context; returns its row id."""
    ensure_v4_tables()
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO trades(opened_at,symbol,side,qty,entry_price,ticket,mode,"
            "prob,params,reason,sl_pct,tp_pct,strategy) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (opened_at, symbol, side, float(qty), float(entry_price), ticket, mode,
             prob, params if isinstance(params, str) else json.dumps(params, default=str),
             str(reason)[:300], sl_pct, tp_pct, strategy))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def open_trades():
    ensure_v4_tables()
    conn = connect()
    try:
        rows = conn.execute(_T_SELECT + " WHERE closed_at IS NULL ORDER BY id DESC").fetchall()
        return [_trade_row(r) for r in rows]
    finally:
        conn.close()


def recent_trades(limit=30, closed_only=False):
    ensure_v4_tables()
    conn = connect()
    try:
        sql = _T_SELECT
        if closed_only:
            sql += " WHERE closed_at IS NOT NULL"
        sql += " ORDER BY id DESC LIMIT ?"
        return [_trade_row(r) for r in conn.execute(sql, (limit,)).fetchall()]
    finally:
        conn.close()


def closed_unreflected():
    ensure_v4_tables()
    conn = connect()
    try:
        rows = conn.execute(
            _T_SELECT + " WHERE reflected=0 AND closed_at IS NOT NULL ORDER BY id"
        ).fetchall()
        return [_trade_row(r) for r in rows]
    finally:
        conn.close()


def close_trade(tid, closed_at, exit_price, pnl, exit_kind, exit_ctx="{}"):
    ensure_v4_tables()
    conn = connect()
    try:
        conn.execute(
            "UPDATE trades SET closed_at=?, exit_price=?, pnl=?, exit_kind=?, exit_ctx=? "
            "WHERE id=?",
            (closed_at, exit_price, pnl, exit_kind, exit_ctx or "{}", tid))
        conn.commit()
    finally:
        conn.close()


def set_trade_ticket(tid, ticket):
    ensure_v4_tables()
    conn = connect()
    try:
        conn.execute("UPDATE trades SET ticket=? WHERE id=?", (ticket, tid))
        conn.commit()
    finally:
        conn.close()


def mark_reflected(tid):
    ensure_v4_tables()
    conn = connect()
    try:
        conn.execute("UPDATE trades SET reflected=1 WHERE id=?", (tid,))
        conn.commit()
    finally:
        conn.close()


def add_lesson(ts, scope, lesson, evidence="", weight=1.0):
    ensure_v4_tables()
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO lessons(ts,scope,lesson,evidence,weight) VALUES(?,?,?,?,?)",
            (ts, scope, lesson, evidence, weight))
        conn.execute(
            "DELETE FROM lessons WHERE id NOT IN "
            "(SELECT id FROM lessons ORDER BY id DESC LIMIT 200)")
        conn.commit()
    finally:
        conn.close()


def recent_lessons(limit=15):
    ensure_v4_tables()
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT ts,scope,lesson,evidence,weight FROM lessons "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(zip(("ts", "scope", "lesson", "evidence", "weight"), r)) for r in rows]
    finally:
        conn.close()
