"""LLM brain selection: local llama.cpp first, Groq fallback.

Reads ROOT/.env (KEY=VALUE). Key vars:
  LOCAL_LLM_ENABLED=true|false
  LOCAL_LLM_BASE_URL=http://127.0.0.1:8080/v1
  LOCAL_LLM_MODEL=any-name (llama-server serves whatever model it loaded)
  LOCAL_LLM_MODEL_PATH=/path/to/model.gguf   (optional explicit path)
  GROQ_API_KEY / GROQ_BASE_URL               (fallback)

chat() never raises: on failure it falls back, and with no provider it
returns (None, "none").
"""
import json
import os
import time

from . import util

_ENV_CACHE = {"at": 0.0, "data": {}}


def env():
    """Parse ROOT/.env into a dict (cached 5s). Real env vars win."""
    now = time.time()
    if now - _ENV_CACHE["at"] > 5:
        data = {}
        p = util.ROOT / ".env"
        try:
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                data[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
        _ENV_CACHE["data"] = data
        _ENV_CACHE["at"] = now
    merged = dict(_ENV_CACHE["data"])
    for k in list(merged):
        if os.environ.get(k) is not None:
            merged[k] = os.environ[k]
    return merged


def set_env(key, value):
    """Persist a key into ROOT/.env and bust the cache. Returns True on success."""
    p = util.ROOT / ".env"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []
        out, found = [], False
        for line in lines:
            if line.strip().startswith(f"{key}="):
                out.append(f"{key}={value}")
                found = True
            else:
                out.append(line)
        if not found:
            out.append(f"{key}={value}")
        p.write_text("\n".join(out) + "\n", encoding="utf-8")
        _ENV_CACHE["at"] = 0
        return True
    except OSError as e:
        util.log_event("ENV", f"set_env {key} failed: {e}")
        return False


def _flag(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def local_enabled():
    e = env()
    return _flag(e.get("LOCAL_LLM_ENABLED", "false"))


def local_base():
    return env().get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")


def _post_chat(base_url, body, headers, timeout):
    import requests

    r = requests.post(f"{base_url}/chat/completions", headers=headers,
                      json=body, timeout=timeout)
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]["content"]
    return json.loads(msg) if body.get("response_format") else msg


def _post_chat_bytes(base_url, body, headers, timeout):
    """chat() but returns raw text content (for freeform Q&A)."""
    import requests

    r = requests.post(f"{base_url}/chat/completions", headers=headers,
                      json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _groq_key():
    k = (util.load_json(util.ROOT / "secrets.json", {}) or {}).get("groq_api_key")
    if k:
        return k
    return env().get("GROQ_API_KEY", "").strip() or None


def _normalize(out, json_mode):
    """_post_chat may return a str OR an already-parsed dict; unify."""
    if not json_mode:
        return out if isinstance(out, str) else json.dumps(out, default=str)
    if isinstance(out, dict):
        return out
    try:
        return json.loads(out)
    except (ValueError, TypeError):
        return None


def find_gguf():
    """Locate a .gguf model: explicit env path, then common dirs (newest wins)."""
    e = env()
    p = e.get("LOCAL_LLM_MODEL_PATH")
    if p and os.path.isfile(p):
        return p
    homes = [
        Path_home() / "Downloads",
        Path_home() / "Documents",
        util.ROOT / "data",
        _drive("D") / "AI" if _drive("D") else None,
        _drive("C") / "AI" if _drive("C") else None,
    ]
    best, best_mtime = None, -1.0
    for h in homes:
        if not h:
            continue
        try:
            if not h.exists():
                continue
            for f in h.glob("*.gguf"):
                m = f.stat().st_mtime
                if m > best_mtime:
                    best, best_mtime = f, m
        except OSError:
            continue
    return str(best) if best else None


def _drive(letter):
    d = Path_(f"{letter}:/")
    return d if d.exists() else None


def Path_home():
    from pathlib import Path
    return Path.home()


def Path_(s):
    from pathlib import Path
    return Path(s)


def local_up(timeout=2.0):
    """True when llama-server answers on its port."""
    if not local_enabled():
        return False
    try:
        import requests
        requests.get(f"{local_base()}/models", timeout=timeout)
        return True
    except Exception:
        return False


def chat(messages, json_mode=True, temperature=0.2, timeout=120):
    """Send a chat. Returns (parsed_json|text|None, provider_str).

    Provider order: local llama.cpp (if enabled+up) -> Groq (if key).
    json_mode=True parses the reply as JSON and returns None on parse failure.
    Appends Qwen3's soft '/no_think' switch to the system prompt for speed.
    """
    msgs = [dict(m) for m in messages]
    if msgs and msgs[0].get("role") == "system" and "/no_think" not in msgs[0]["content"]:
        msgs[0]["content"] = msgs[0]["content"] + " /no_think"

    if local_enabled() and local_up():
        body = {"messages": msgs, "temperature": temperature}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            out = _post_chat(local_base(), body, {}, timeout)
            return _normalize(out, json_mode), "local-llamacpp"
        except Exception as e:
            util.log_event("LLM", f"local call failed, falling back: {e}")

    key = _groq_key()
    if key:
        base = env().get("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
        model = env().get("GROQ_MODEL", "openai/gpt-oss-120b")
        body = {"model": model, "temperature": temperature,
                "messages": msgs}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        last_err = None
        for attempt in range(2):  # some networks flap TLS; one retry suffices
            try:
                out = _post_chat(base, body, {"Authorization": f"Bearer {key}"}, 60)
                return _normalize(out, json_mode), "groq"
            except Exception as e:
                last_err = e
                import time as _t
                _t.sleep(1.5)
        util.log_event("LLM", f"groq call failed ({model}): {last_err}")

    return None, "none"


def health():
    """Status dict for /api/llm and the Connections page."""
    e = env()
    enabled = local_enabled()
    up = local_up() if enabled else False
    groq = bool(_groq_key())
    active = "local-llamacpp" if up else ("groq" if groq else "none")
    secret_set = bool(e.get("TRADINGVIEW_WEBHOOK_SECRET")) and \
        e.get("TRADINGVIEW_WEBHOOK_SECRET") != "your_generated_secret"
    return {
        "enabled": enabled,
        "up": up,
        "base_url": local_base(),
        "model_file": find_gguf() if enabled else None,
        "groq_configured": groq,
        "active": active,
        "webhook_secret_set": secret_set,
        "obsidian_vault": e.get("OBSIDIAN_VAULT_PATH", ""),
        "note": ("local Qwen brain is live" if up else
                 ("local LLM enabled but server not up — using Groq" if groq and enabled else
                  ("Groq cloud brain active" if groq else
                   "no LLM available — agent muted"))),
    }
