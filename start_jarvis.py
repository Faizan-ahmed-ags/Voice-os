"""One-command JARVIS console launcher.

  runtime\\python.exe start_jarvis.py

Ensures the dashboard is built, then serves UI + brain API on
http://127.0.0.1:8765 and opens your browser.
"""
import os
import subprocess
import sys
import time
import webbrowser

# Redirected stdout on Windows defaults to cp1252 and crashes on unicode banners.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dashboard", "dist", "index.html")
PORT = 8765
LLAMA_PORT = 8080


def find_llama_server():
    """Locate llama-server.exe: PATH, then the winget install dir."""
    exe = os.path.join(ROOT, ".venv", "Scripts", "llama-server.exe")
    if os.path.isfile(exe):
        return exe
    try:
        out = subprocess.run(["where.exe", "llama-server"], capture_output=True,
                             text=True, timeout=10)
        for line in out.stdout.splitlines():
            if line.strip():
                return line.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    winget = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                          "Microsoft", "WinGet", "Packages")
    if os.path.isdir(winget):
        for dirpath, _dirnames, filenames in os.walk(winget):
            if "llama-server.exe" in filenames:
                return os.path.join(dirpath, "llama-server.exe")
    return None


def find_gguf():
    """Newest .gguf in Downloads/Documents/data (or LOCAL_LLM_MODEL_PATH)."""
    from pathlib import Path
    root = Path(ROOT)
    env_path = root / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("LOCAL_LLM_MODEL_PATH="):
                    p = line.partition("=")[2].strip().strip('"')
                    if p and os.path.isfile(p):
                        return p
        except OSError:
            pass
    homes = [Path.home() / "Downloads", Path.home() / "Documents", root / "data"]
    best, best_mtime = None, -1.0
    for h in homes:
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


def llama_port_open():
    import socket
    try:
        with socket.create_connection(("127.0.0.1", LLAMA_PORT), timeout=0.8):
            return True
    except OSError:
        return False


def wait_llama(seconds=90):
    for _ in range(seconds):
        if llama_port_open():
            return True
        time.sleep(1)
    return False


def boot_local_llm():
    """Start llama-server with the Qwen brain on :8080 (best effort, never fatal)."""
    from brain.llm import env as llm_env
    if str(llm_env().get("LOCAL_LLM_ENABLED", "")).strip().lower() not in ("1", "true", "yes", "on"):
        return
    if llama_port_open():
        print("local LLM already up on :8080")
        return
    server = find_llama_server()
    model = find_gguf()
    if not server or not model:
        print("local LLM enabled but server/model not found — using Groq fallback if configured")
        return
    print(f"booting local brain: {os.path.basename(model)} on :{LLAMA_PORT} ...")
    log_dir = os.path.join(ROOT, ".freebuff")
    try:
        os.makedirs(log_dir, exist_ok=True)
        logf = open(os.path.join(log_dir, "llama-server.log"), "ab")
        subprocess.Popen(
            [server, "-m", model, "--port", str(LLAMA_PORT),
             "-c", "4096", "-t", "6", "--host", "127.0.0.1"],
            stdout=logf, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            cwd=os.path.dirname(server))
        if wait_llama(15):
            print("local brain online → http://127.0.0.1:8080")
        else:
            print("local brain still loading in background — JARVIS falls back to Groq until it answers")
    except OSError as e:
        print(f"could not start llama-server ({e}) — using Groq fallback")


def build_dashboard():
    if os.path.exists(DIST):
        return
    npm_cmd = _npm()
    print("dashboard not built yet — building now (first run only, ~1 min)...")
    subprocess.run([npm_cmd, "install", "--no-fund", "--no-audit"], cwd=os.path.join(ROOT, "dashboard"), shell=True)
    subprocess.run([npm_cmd, "run", "build"], cwd=os.path.join(ROOT, "dashboard"), shell=True)


def _npm():
    for cand in ("npm.cmd", "npm"):
        try:
            r = subprocess.run([cand, "--version"], capture_output=True, shell=True)
            if r.returncode == 0:
                return cand
            break
        except OSError:
            continue
    raise SystemExit("npm not found — install Node.js from https://nodejs.org")


def port_open():
    import socket

    with socket.create_connection(("127.0.0.1", PORT), timeout=1):
        return True


def wait_http():
    for _ in range(50):
        try:
            if port_open():
                return True
        except OSError:
            time.sleep(0.3)
    return False


def start_learner_loop():
    """Background thread: reconcile broker-side exits + reflect every 10 min.

    TP/SL fills happen at the broker even with this console closed; this loop
    pulls them into the trade ledger and turns them into lessons.
    """
    def loop():
        import time as _t
        from brain.learner import reconcile, reflect
        while True:
            try:
                rec = reconcile()
                n = reflect()
                if rec.get("matched") or n:
                    print(f"[learner] reconciled {rec.get('matched')} exits, "
                          f"{n} new lessons")
            except Exception as e:
                print(f"[learner] loop error: {e}")
            _t.sleep(600)

    import threading
    threading.Thread(target=loop, daemon=True).start()


def start_daily_loop():
    """Background thread: the daily learn→predict→trade cycle runs itself.

    MT5-connected: fires just after the US open (fills at open prices).
    Sim: fires after the US close. Once per day, tracked in memory.
    """
    def loop():
        import time as _t
        from brain.daily import schedule_loop
        import threading as _th
        stop = _th.Event()
        schedule_loop(stop)

    import threading
    threading.Thread(target=loop, daemon=True).start()
    print("daily cycle scheduled (runs itself once per day)")


def main():
    build_dashboard()
    boot_local_llm()
    start_learner_loop()
    start_daily_loop()
    import threading

    from brain.bridge import DualHandler
    from http.server import ThreadingHTTPServer

    # Bind with retries: a freshly-killed previous instance can leave the port
    # busy for a few seconds; also serves as the double-launch guard.
    srv = None
    for _ in range(15):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", PORT), DualHandler)
            break
        except OSError:
            if port_open():
                if os.environ.get("JARVIS_NO_BROWSER") != "1":
                    webbrowser.open(f"http://127.0.0.1:{PORT}")
                print(f"J.A.R.V.I.S. already running → http://127.0.0.1:{PORT}")
                return
            time.sleep(1)
    if srv is None:
        print(f"could not bind port {PORT} — is another JARVIS instance stuck?")
        sys.exit(1)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    if wait_http():
        if os.environ.get("JARVIS_NO_BROWSER") != "1":
            webbrowser.open(f"http://127.0.0.1:{PORT}")
        print(f"J.A.R.V.I.S. console → http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    else:
        print("server failed to start")
        sys.exit(1)
    try:
        while t.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down. Paper trades are saved in data/.")


if __name__ == "__main__":
    main()
