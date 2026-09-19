"""Daily news: per-symbol news from yfinance + GitHub activity trend."""
import time

from . import util
from .store import gh_signal_history

_CACHE = {"at": 0.0, "data": None}
TTL = 300  # 5 minutes


def _symbol_news(symbol, max_items=6):
    try:
        import yfinance as yf
        items = yf.Ticker(symbol).news or []
    except Exception:
        return []
    out = []
    for n in items[:max_items]:
        try:
            content = n.get("content") or n
            title = content.get("title") or n.get("title", "")
            if not title:
                continue
            pub = content.get("pubDate") or content.get("providerPublishTime")
            when = ""
            if pub:
                try:
                    when = pub if isinstance(pub, str) else time.strftime(
                        "%Y-%m-%d %H:%M", time.gmtime(int(pub)))
                except (ValueError, TypeError, OSError):
                    when = ""
            link = ""
            try:
                link = (content.get("clickThroughUrl") or {}).get("url") or \
                       (content.get("canonicalUrl") or {}).get("url") or ""
            except AttributeError:
                link = ""
            out.append({"title": title, "when": when, "link": link,
                        "publisher": ((content.get("provider") or {}).get("displayName")
                                      if isinstance(content.get("provider"), dict) else "")})
        except Exception:
            continue
    return out


def _gh_trend(symbol, days=14):
    hist = gh_signal_history(symbol, limit=days)
    return [{"ts": ts, "raw": raw, "z": z} for ts, raw, z in hist]


def daily_news(universe):
    now = time.time()
    if _CACHE["data"] and now - _CACHE["at"] < TTL:
        return _CACHE["data"]
    data = {s: {"news": _symbol_news(s), "gh_trend": _gh_trend(s)} for s in universe}
    _CACHE["data"] = data
    _CACHE["at"] = now
    return data
