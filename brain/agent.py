"""The 'grows on its own' loop: Groq LLM reviews, proposes, backtests, adopts.

Every proposal is validated against hard guardrails, then backtested
out-of-sample. A proposal becomes champion only if it beats the incumbent
on return AND doesn't increase max drawdown beyond limits. Fully audited.
"""
import json
import re

from . import util
from .strategy import backtest, DEFAULTS

BOUNDS = {
    "threshold": (0.51, 0.75),
    "take_profit": (0.02, 0.20),
    "stop_loss": (0.015, 0.12),
    "max_position_frac": (0.10, 0.50),
}
GUARDRAILS = (
    "Guardrails: max_drawdown must not increase by more than 3 percentage "
    "points vs incumbent; return must be strictly higher; threshold >= 0.51 "
    "(only trade strong edges); stop_loss <= 0.12 (cap single-trade loss)."
)


def _llm_chat(messages, temperature=0.2):
    """Local llama.cpp brain first, Groq fallback. Returns dict or None."""
    from . import llm
    reply, _provider = llm.chat(messages, json_mode=True, temperature=temperature)
    return reply if isinstance(reply, dict) else None


def _validate(params):
    """Clamp proposal into hard bounds; reject structurally broken ones."""
    out = {}
    for k, (lo, hi) in BOUNDS.items():
        v = params.get(k)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if math_isnan(v) or v <= 0:
            continue
        out[k] = min(max(v, lo), hi)
    return out


def math_isnan(x):
    return x != x


def review_and_evolve(cfg, symbols):
    """Weekly-style evolution pass. Returns summary dict for CLI display."""
    memory = util.load_json(util.DATA_DIR / "sim_state.json", {}) or {}
    results = {}
    for sym in symbols:
        try:
            incumbent_params = (util.load_json(util.DATA_DIR / "champion_params.json", {}) or {}).get(sym, {})
            incumbent = backtest(sym, params=incumbent_params or None)
            if not incumbent.get("ok"):
                results[sym] = {"status": "skipped", "why": incumbent.get("error")}
                continue

            # Lessons from real trades steer the proposal — the agent now
            # learns from the ledger, not just from backtests.
            lessons_ctx = ""
            try:
                from .learner import stats
                st = stats()
                lessons = [l["lesson"] for l in (st.get("lessons") or [])
                           if l.get("scope") in (sym, "*")][:6]
                if lessons:
                    lessons_ctx = ("\nLessons from recent real trades (respect these):\n- "
                                   + "\n- ".join(lessons))
                if st.get("closed"):
                    lessons_ctx += (f"\nLive ledger so far: {st['closed']} closed trades, "
                                    f"hit-rate {st.get('hit_rate_pct')}%, "
                                    f"cumulative {st.get('cumulative_pnl'):+.2f}.")
            except Exception:
                pass

            prompt = [
                {"role": "system", "content":
                    "You are JARVIS, a cautious self-improving trading-agent. "
                    "You may ONLY propose values for keys: "
                    f"{sorted(BOUNDS)} from within these bounds: {BOUNDS}. "
                    + GUARDRAILS
                    + " Respond ONLY with JSON: {\"reasoning\": str, "
                      "\"params\": {...}}"},
                {"role": "user", "content":
                    f"Symbol {sym}. Incumbent params {incumbent_params or 'defaults'}. "
                    f"OOS backtest of incumbent: {json.dumps(incumbent, default=str)}. "
                    "Current regime: rates high, AI capex cycle. Propose ONE improved "
                    "parameter set. Change at most 2 parameters. Be conservative."
                    + lessons_ctx},
            ]
            reply = _llm_chat(prompt)
            if not reply:
                results[sym] = {"status": "no_llm",
                                "why": "no LLM brain available (local down + no Groq key)"}
                continue

            proposal = _validate(reply.get("params", {}))
            util.log_event("AGENT", f"{sym}: proposed {json.dumps(proposal)} — {reply.get('reasoning', '')[:120]}")
            if not proposal:
                results[sym] = {"status": "rejected", "why": "proposal empty/out-of-bounds"}
                continue

            challenger = backtest(sym, params=proposal)
            better = (challenger.get("ok") and challenger["return_pct"] > incumbent["return_pct"]
                      and challenger["max_drawdown_pct"] <= incumbent["max_drawdown_pct"] + 3.0)
            if better:
                champs = util.load_json(util.DATA_DIR / "champion_params.json", {}) or {}
                champs[sym] = proposal
                util.save_json(util.DATA_DIR / "champion_params.json", champs)
                util.log_event("AGENT", f"{sym}: ADOPTED {json.dumps(proposal)} "
                                       f"({challenger['return_pct']}% vs {incumbent['return_pct']}%)")
                results[sym] = {"status": "adopted", "params": proposal,
                                "challenger": challenger, "incumbent": incumbent}
            else:
                results[sym] = {"status": "kept_incumbent",
                                "challenger_return": challenger.get("return_pct"),
                                "incumbent_return": incumbent["return_pct"]}
        except Exception as e:
            results[sym] = {"status": "error", "why": str(e)}
    set_memory_wrap("last_evolution", {"at": util.iso(), "results": results})
    try:
        from .memory import evolution_note
        evolution_note(results)
    except Exception:
        pass
    return results


def set_memory_wrap(key, value):
    from .store import set_memory
    set_memory(key, value)
