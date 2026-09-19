"""Data layer: price candles via yfinance, GitHub-activity signal via REST.

Every fetcher degrades gracefully: no network / no library -> cached or None.
"""
import re
import time
from datetime import timedelta

from . import util
from .store import save_gh_signal

PRICE_CACHE_HOURS = 8

# Curated map: tradable symbol -> GitHub repos whose activity we track as a
# developer-momentum signal. Keep this list small and high-signal.
GH_REPOS = {
    "MSFT": ["microsoft/vscode", "microsoft/TypeScript"],
    "NVDA": ["NVIDIA/cutlass", "NVIDIA/TensorRT-LLM"],
}


def _cache_key(symbol, interval, period):
    return f"prices:{symbol}:{interval}:{period}"


def get_prices(symbol, period="2y", interval="1d", max_age_hours=PRICE_CACHE_HOURS):
    """DataFrame[Open,High,Low,Close,Volume] from yfinance with JSON cache."""
    cache = util.load_json(util.DATA_DIR / "prices.json", {}) or {}
    key = _cache_key(symbol, interval, period)
    entry = cache.get(key)
    if entry:
        age_h = (util.utcnow() - util.iso_to_dt(entry["fetched_at"])).total_seconds() / 3600
        if age_h < max_age_hours:
            return pd_read(entry["rows"])

    try:
        import yfinance as yf

        df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
        if df is None or df.empty:
            raise RuntimeError("empty history")
        df = df[["Open", "High", "Low", "Close", "Volume"]].round(4)
        rows = [
            [str(idx), float(r.Open), float(r.High), float(r.Low), float(r.Close), float(r.Volume)]
            for idx, r in df.iterrows()
        ]
        cache[key] = {"fetched_at": util.iso(), "rows": rows}
        util.save_json(util.DATA_DIR / "prices.json", cache)
        return pd_read(rows)
    except Exception as e:
        if entry:  # stale cache beats nothing
            util.log_event("DATA", f"{symbol}: using stale cache ({e})")
            return pd_read(entry["rows"])
        util.log_event("DATA", f"{symbol}: price fetch failed — {e}")
        return None


def pd_read(rows):
    try:
        import pandas as pd

        df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        df["Date"] = pd.to_datetime(df["Date"], utc=True)
        return df.set_index("Date")
    except ImportError:
        return None


# ---------------------------------------------------------------- GitHub signal

_GH_CACHE = {}


def _gh_json(url, params=None):
    import requests

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "jarvis-brain/0.1"}
    token = util.load_json(util.ROOT / "secrets.json", {}).get("github_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_repo_activity(full_name, weeks=12):
    """Commits + new issues per week for a repo (GitHub REST)."""
    since = (util.utcnow() - timedelta(weeks=weeks)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    page = 1
    while page <= 3:  # up to 300 events is plenty
        try:
            events = _gh_json(f"https://api.github.com/repos/{full_name}/events",
                              {"per_page": 100, "page": page})
        except Exception:
            break
        if not events:
            break
        out.extend(events)
        page += 1
        time.sleep(0.2)

    weekly = {}
    for ev in out:
        if ev.get("type") in ("PushEvent", "IssuesEvent", "PullRequestEvent"):
            w = (ev.get("created_at") or "")[:10]
            weekly[w] = weekly.get(w, 0) + 1
    return sorted(weekly.items())


def github_signal(symbol, weeks=12):
    """Z-score of recent GitHub activity vs the symbol's own 12-week norm.

    Returns (raw_activity, z) or (None, None) when unavailable.
    Persisted to SQLite so the agent can correlate with P&L later.
    """
    repos = GH_REPOS.get(symbol.upper())
    if not repos:
        return None, None
    total = 0
    ok = 0
    for repo in repos:
        series = fetch_repo_activity(repo, weeks)
        if series:
            vals = [v for _, v in series]
            total += sum(vals)
            ok += 1
    if not ok:
        util.log_event("GH", f"{symbol}: GitHub fetch failed (rate limit?)")
        return None, None

    import statistics

    hist = _GH_CACHE.get(symbol)
    if hist is None:
        hist = []
    hist.append(total)
    _GH_CACHE[symbol] = hist[-40:]
    z = None
    if len(_GH_CACHE[symbol]) >= 4:
        mu = statistics.mean(_GH_CACHE[symbol])
        sd = statistics.pstdev(_GH_CACHE[symbol]) or 1.0
        z = round((total - mu) / sd, 2)

    ts = util.iso()
    save_gh_signal(ts, symbol.upper(), total, z)
    return total, z
