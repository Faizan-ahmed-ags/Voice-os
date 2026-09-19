"""Halal (Shariah) compliance screening for US stocks.

Two layers:
1. Business-activity screen: whitelist of clearly-permissible companies.
2. Financial-ratio screen: AAOIFI-style debt/interest/cash thresholds.

Failing *either* layer excludes the symbol. Cached for 24h in memory.json.
"""
from . import util
from .store import get_memory, set_memory

CACHE_KEY = "halal_cache"
CACHE_HOURS = 24

# Whitelist: main business is permissible. (Not a fatwa — see README disclaimer.)
WHITELIST = {
    "MSFT": "Microsoft — software/cloud",
    "NVDA": "NVIDIA — semiconductors/AI hardware",
    "AAPL": "Apple — consumer hardware",
    "ADBE": "Adobe — software",
    "CRM": "Salesforce — cloud software",
    "NOW": "ServiceNow — cloud software",
    "INTU": "Intuit — financial software",
    "PANW": "Palo Alto Networks — cybersecurity",
    "AMD": "AMD — semiconductors",
    "AVGO": "Broadcom — semiconductors",
    "AMAT": "Applied Materials — semicap",
    "LRCX": "Lam Research — semicap",
    "KLAC": "KLA — semicap",
    "MU": "Micron — memory",
    "TXN": "Texas Instruments — semiconductors",
    "QCOM": "Qualcomm — semiconductors",
    "AMZN": "Amazon — e-commerce/cloud",
    "COST": "Costco — membership retail",
    "GOOGL": "Alphabet — search/cloud",
    "ISRG": "Intuitive Surgical — medical devices",
    "VRTX": "Vertex — biotech",
    "REGN": "Regeneron — biotech",
    "ANET": "Arista Networks — networking",
    "CDNS": "Cadence — EDA software",
    "SNPS": "Synopsys — EDA software",
    "TEAM": "Atlassian — software",
    "WDAY": "Workday — cloud software",
    "DDOG": "Datadog — cloud software",
    "ZS": "Zscaler — cybersecurity",
    "NET": "Cloudflare — internet infrastructure",
}

# Business-activity black-list keywords (company names/sectors to refuse outright).
BLACKLIST_KEYWORDS = (
    "bank", "insurance", "brewer", "distiller", "casino", "gaming", "resort",
    "tobacco", "defense", "aerospace", "adult", "pork", "lottery", "liquor",
)

# AAOIFI-style ratio thresholds (fractions of market cap / total assets).
MAX_DEBT_MCAP = 0.30
MAX_CASH_INTEREST_MCAP = 0.30
MAX_RECEIVABLES_MCAP = 0.33

# Seed fallback ratios so screening works offline / before first fetch.
SEED_RATIOS = {
    "MSFT": {"debt": 0.14, "cash_int": 0.20, "receivables": 0.11},
    "NVDA": {"debt": 0.05, "cash_int": 0.25, "receivables": 0.10},
}


def _fetch_ratios(symbol):
    """Pull market-cap-relative debt/interest-assets/receivables from yfinance."""
    try:
        import yfinance as yf

        t = yf.Ticker(symbol)
        info = t.info or {}
        bs = t.balance_sheet
        mc = info.get("marketCap") or 0
        if not mc:
            return None

        def total(key_names):
            try:
                row = bs.loc[[k for k in key_names if k in bs.index]].sum().iloc[0]
                return float(row)
            except Exception:
                return 0.0

        debt = total(["Total Debt", "Long Term Debt", "Current Debt"])
        cash = total(["Cash And Cash Equivalents", "Other Short Term Investments"])
        recv = total(["Accounts Receivable", "Net Accounts Receivable", "Receivables"])
        return {
            "debt": min(max(debt / mc, 0.0), 10.0),
            "cash_int": min(max(cash / mc, 0.0), 10.0),
            "receivables": min(max(recv / mc, 0.0), 10.0),
        }
    except Exception:
        return None


def screen_symbol(symbol):
    """Return dict(symbol, compliant, reason, ratios, checked_at)."""
    symbol = symbol.upper()
    cache = get_memory(CACHE_KEY, {}) or {}
    entry = cache.get(symbol)
    if entry and entry.get("checked_at"):
        age_h = (util.utcnow() - util.iso_to_dt(entry["checked_at"])).total_seconds() / 3600
        if age_h < CACHE_HOURS:
            return entry

    ratios = _fetch_ratios(symbol) or SEED_RATIOS.get(symbol)
    if symbol not in WHITELIST:
        result = {"symbol": symbol, "compliant": False,
                  "reason": "not on whitelist (unverified business activity)", "ratios": None}
    elif ratios is None:
        result = {"symbol": symbol, "compliant": False,
                  "reason": "could not fetch financial ratios", "ratios": None}
    else:
        if (ratios["debt"] <= MAX_DEBT_MCAP
                and ratios["cash_int"] <= MAX_CASH_INTEREST_MCAP
                and ratios["receivables"] <= MAX_RECEIVABLES_MCAP):
            reason = "whitelisted + ratios pass"
        else:
            reason = "ratios exceed AAOIFI-style thresholds"
        result = {"symbol": symbol, "compliant": reason == "whitelisted + ratios pass",
                  "reason": reason, "ratios": ratios}
    result["checked_at"] = util.iso()
    cache[symbol] = result
    set_memory(CACHE_KEY, cache)
    util.log_event("HALAL", f"{symbol}: {'PASS' if result['compliant'] else 'FAIL'} — {result['reason']}")
    return result


def screen_universe(symbols):
    return {s: screen_symbol(s) for s in symbols}
