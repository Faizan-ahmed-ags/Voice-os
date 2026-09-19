"""Central configuration. All values overridable via config.json in repo root."""

DEFAULTS = {
    "universe": ["MSFT", "NVDA"],
    "paper_trading": True,        # Alpaca paper only when keys present + this true
    "starting_cash": 10000.0,     # SIM broker starting cash
    "daily_run_time": "21:45",    # UTC; ~4:45pm ET, just after US close (sim broker)
    "daily_run_time_mt5": "13:40", # UTC; just after US open — MT5 equity session only fills then
    "evolve_day": "sunday",
    "evolve_time": "17:00",
    "max_daily_loss_pct": 3.0,    # kill-switch: pause trading if day P&L below -3%
    "llm_model": "openai/gpt-oss-120b",  # Groq fallback brain (llama models retired)
}


def load():
    import json
    from .util import ROOT, load_json

    user = load_json(ROOT / "config.json", {}) or {}
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
    _apply_env_safety(cfg)
    return cfg


def _apply_env_safety(cfg):
    """TRADING_MODE / ALLOW_LIVE_TRADING in .env act as a hard ceiling:
    they can only make JARVIS safer, never riskier than config.json."""
    from . import llm
    e = llm.env()
    mode = str(e.get("TRADING_MODE", "")).strip().lower()
    if mode in ("paper", "sim"):
        cfg["paper_trading"] = True
    if str(e.get("ALLOW_LIVE_TRADING", "")).strip().lower() in ("", "0", "false", "no", "off"):
        cfg["paper_trading"] = True
    if str(e.get("MAX_OPEN_POSITIONS", "")).strip().isdigit():
        n = int(e["MAX_OPEN_POSITIONS"])
        cfg["max_open_positions"] = min(cfg.get("max_open_positions", n), n)


def save(cfg):
    import json
    from .util import ROOT, save_json

    save_json(ROOT / "config.json", cfg)
