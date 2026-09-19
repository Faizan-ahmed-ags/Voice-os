# JARVIS — self-growing, halal, paper-trading agent for US stocks

A Python "brain" that lives alongside the JARVIS Voice app in this repo.
It screens stocks for halal (Shariah) compliance, learns price + GitHub
signals with an ML model, paper-trades them through a broker, and improves
its own strategy parameters over time via an LLM agent with hard guardrails.

## What it does

1. **Halal screen** — whitelist + AAOIFI-style financial ratios
   (debt/mcap ≤ 30%, cash+interest/mcap ≤ 30%, receivables/mcap ≤ 33%).
   Failing either layer blocks the symbol from trading.
2. **Data** — daily candles (yfinance) + GitHub developer-activity signal
   (commits/issues/PRs per week across curated repos, z-scored).
3. **Model** — HistGradientBoosting classifier, walk-forward CV with a
   10-day embargo (no leakage), AUC-gated champion/candidate status.
4. **Strategy** — probability ≥ threshold → buy 30% of equity; exit when
   edge gone (p < 0.50); take-profit/stop-loss enforced in backtest.
5. **Brokers** — built-in SIM broker (no keys, default) or Alpaca **paper**
   when API keys exist. Real-money trading is deliberately not implemented.
6. **Growth loop** — Groq LLM proposes parameter changes within hard bounds;
   each proposal is backtested out-of-sample and adopted only if return is
   higher without worsening drawdown > 3pp. Everything is logged to
   `data/agent_activity.log` and SQLite.

## Setup

```bash
runtime/python.exe -m venv .venv                 # Windows; or python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m brain.main init-secrets  # creates secrets.json (optional keys)
```

Fill `secrets.json` (all optional):
- `groq_api_key` — enables the self-evolution agent (you already have Groq)
- `alpaca_key_id` / `alpaca_secret_key` — enables Alpaca **paper** trading
- `github_token` — higher GitHub API rate limits

## Commands

```bash
python -m brain.main screen     # halal compliance of the universe
python -m brain.main train      # train models, walk-forward AUC gate
python -m brain.main backtest   # honest out-of-sample results (60/40 split)
python -m brain.main run-once   # one trading decision cycle (uses SIM by default)
python -m brain.main status     # equity, positions, decisions, champions
python -m brain.main evolve     # LLM proposes, backtest disposes
python -m brain.main daemon     # daily 21:45 UTC run + weekly evolution
```

## Design decisions

- **SIM first**: works with zero API keys and zero financial risk.
- **Purge/embargo CV** avoids leaking the 5-day label horizon across splits.
- **Champion–challenger**: the LLM can only mutate 4 bounded policy numbers;
   it cannot touch order logic, halal rules, or risk limits.
- **Universe**: MSFT + NVDA by default (`config.json` to extend). Edit
  `brain/halal.py` whitelist if you add symbols — every symbol needs both
  whitelist entry and passing ratios.

## Not financial advice

Educational software. Backtests overstate live results. Halal screening is
best-effort quantitative — not a fatwa; consult a qualified scholar for
religious rulings. Paper results do not guarantee future performance.
