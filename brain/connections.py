"""Connection status checks: Alpaca, Groq, MT5, TradingView, webhook.

MT5 is detection + setup guidance only (no trading bridge) per plan.
All checks are fast and never raise.
"""
from pathlib import Path

from . import util

# Common MT5 terminal install locations on Windows.
MT5_PATHS = [
    Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
    Path(r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe"),
    Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" ,
]

MT5_GUIDE = [
    "1. Download MT5 from https://www.metatrader5.com/en/download and install.",
    "2. Open MT5, File > 'Open an Account', pick your broker, choose the DEMO server.",
    "3. Paste login / password / server into the MT5 demo account form on this page, then 'save & test connection'.",
    "4. Keep the terminal installed (JARVIS attaches via the MetaTrader5 package); restart the console after saving creds.",
]


def _alpaca():
    secrets = util.load_json(util.ROOT / "secrets.json", {}) or {}
    key = secrets.get("alpaca_key_id")
    secret = secrets.get("alpaca_secret_key")
    paper = bool(secrets.get("alpaca_paper", True))
    if not key or not secret:
        return {"configured": False, "paper": None,
                "how": "Put alpaca_key_id + alpaca_secret_key in secrets.json (paper keys from app.alpaca.markets)."}
    return {"configured": True, "paper": paper,
            "how": "Keys detected — run-once will use the Alpaca paper broker."}


def _groq():
    secrets = util.load_json(util.ROOT / "secrets.json", {}) or {}
    ok = bool(secrets.get("groq_api_key"))
    if not ok:
        from .llm import env
        ok = bool(env().get("GROQ_API_KEY", "").strip())
    return {"configured": ok,
            "how": "" if ok else "Add GROQ_API_KEY to .env (console.groq.com) to enable the self-evolution agent."}


def _mt5():
    installed = [str(p) for p in MT5_PATHS if p.exists()]
    try:
        import MetaTrader5  # noqa: F401
        pkg = True
    except ImportError:
        pkg = False
    return {
        "installed": bool(installed),
        "paths_found": installed,
        "python_package": pkg,
        "bridge_wired": False,
        "guide": MT5_GUIDE,
        "note": ("terminal detected — Python bridge not wired yet (status page only, per plan)"
                 if installed else
                 "MT5 not detected on this machine — follow the guide to install the demo terminal."),
    }


def _tradingview():
    return {"configured": True,
            "note": "Charts render client-side on the Connections page; alerts arrive via the webhook below."}


def _webhook():
    return {
        "url": "http://127.0.0.1:8765/api/webhook",
        "method": "POST",
        "note": ("Point TradingView alert webhooks here. JSON is logged and, in paper mode, "
                 "a paper decision is recorded if the symbol passes the halal screen. "
                 "Local-only: not reachable from the internet."),
    }


def connections_status():
    try:
        alpaca = _alpaca()
    except Exception as e:
        alpaca = {"configured": False, "how": f"check failed: {e}"}
    try:
        groq = _groq()
    except Exception as e:
        groq = {"configured": False, "how": f"check failed: {e}"}
    try:
        mt5 = _mt5()
    except Exception as e:
        mt5 = {"installed": False, "note": f"check failed: {e}", "guide": MT5_GUIDE}
    try:
        from .brokers import get_broker
        broker_name = get_broker(load_cfg()).name
    except Exception:
        broker_name = "sim"
    return {
        "alpaca": alpaca,
        "groq": groq,
        "mt5": mt5,
        "tradingview": _tradingview(),
        "webhook": _webhook(),
        "active_broker": broker_name,
    }


def load_cfg():
    from .config import load
    return load()
