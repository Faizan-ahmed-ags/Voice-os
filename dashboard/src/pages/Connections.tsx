import { useEffect, useState } from "react"
import { Check, Copy, Landmark, Network, Webhook, X } from "lucide-react"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { ConnectionsResponse, LlmHealth, Mt5Status, StatusResponse } from "@/lib/types"

declare global {
  interface Window {
    TradingView?: { widget: new (opts: Record<string, unknown>) => unknown }
  }
}

function Tile({ ok, title, children }: { ok: boolean | null; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card/60 p-4 backdrop-blur">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">{title}</h3>
        {ok === null ? (
          <span className="font-mono text-xs text-muted-foreground">—</span>
        ) : ok ? (
          <span className="flex items-center gap-1 font-mono text-xs text-[var(--color-success)]"><Check className="size-4" /> ok</span>
        ) : (
          <span className="flex items-center gap-1 font-mono text-xs text-[var(--color-warning)]"><X className="size-4" /> not set</span>
        )}
      </div>
      <div className="text-sm">{children}</div>
    </div>
  )
}

let tvScriptPromise: Promise<void> | null = null

function loadTvScript(): Promise<void> {
  if (window.TradingView) return Promise.resolve()
  if (!tvScriptPromise) {
    tvScriptPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script")
      s.src = "https://s3.tradingview.com/tv.js"
      s.async = true
      s.onload = () => resolve()
      s.onerror = () => reject(new Error("TradingView script failed to load (offline?)"))
      document.head.appendChild(s)
    })
  }
  return tvScriptPromise
}

function TVChart({ symbol, interval = "D" }: { symbol: string; interval?: string }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let cancelled = false
    loadTvScript()
      .then(() => {
        if (cancelled || !window.TradingView) return
        const el = document.getElementById(`tv_${symbol}`)
        if (!el) return
        el.innerHTML = ""
        new window.TradingView.widget({
          container_id: `tv_${symbol}`,
          symbol: `NASDAQ:${symbol}`,
          interval,
          theme: document.documentElement.classList.contains("light") ? "light" : "dark",
          style: "1",
          locale: "en",
          autosize: true,
          hide_side_toolbar: true,
          allow_symbol_change: false,
        })
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [symbol, interval])
  if (failed) {
    return (
      <div className="flex h-[420px] items-center justify-center text-sm text-muted-foreground">
        Chart unavailable (no internet, or tradingview.com blocked).
      </div>
    )
  }
  return <div id={`tv_${symbol}`} className="h-[420px] w-full" />
}

export default function Connections() {
  const [conn, setConn] = useState<ConnectionsResponse | null>(null)
  const [llm, setLlm] = useState<LlmHealth | null>(null)
  const [alerts, setAlerts] = useState<{ ts: string; source: string; payload: unknown }[]>([])
  const [copied, setCopied] = useState(false)
  const [mt5, setMt5] = useState<Mt5Status | null>(null)
  const [mt5Login, setMt5Login] = useState("")
  const [mt5Pass, setMt5Pass] = useState("")
  const [tf, setTf] = useState("1")
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [mt5Server, setMt5Server] = useState("")
  const [mt5Msg, setMt5Msg] = useState<string | null>(null)
  const [mt5Busy, setMt5Busy] = useState(false)

  useEffect(() => {
    const load = () => {
      api.connections().then(setConn).catch(() => {})
      api.llm().then(setLlm).catch(() => {})
      api.webhooks().then((r) => setAlerts(r.webhooks)).catch(() => {})
      api.mt5().then(setMt5).catch(() => {})
      api.status().then(setStatus).catch(() => {})
    }
    load()
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [])

  const saveMt5 = async (test: boolean) => {
    setMt5Busy(true)
    setMt5Msg(null)
    try {
      const r = await api.saveMt5Creds(mt5Login, mt5Pass, mt5Server, test)
      if (test) {
        setMt5Msg(r.connected ? `✓ connected: ${r.account?.name} @ ${r.account?.server} (${r.account?.trade_mode}, ${r.account?.currency} ${r.account?.equity})` : `✕ ${r.error}`)
      } else {
        setMt5Msg(r.ok ? "✓ saved — takes effect on next cycle or console restart" : "✕ save failed")
      }
      api.mt5().then(setMt5).catch(() => {})
    } catch (e) {
      setMt5Msg(`✕ ${e instanceof Error ? e.message : "failed"}`)
    } finally {
      setMt5Busy(false)
    }
  }

  const webhookUrl = conn?.webhook.url ?? "http://127.0.0.1:8765/api/webhook"

  return (
    <div>
      <header className="mb-6">
        <h2 className="flex items-center gap-2 font-mono text-2xl font-bold tracking-widest text-primary">
          <Network className="size-6" /> CONNECTIONS
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Brokers, keys, charting, and alert plumbing. Active broker: <b>{conn?.active_broker ?? "…"}</b>
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Tile ok={llm ? (llm.up ? true : llm.groq_configured ? null : false) : null} title="Local LLM (Qwen brain)">
          {llm ? (
            <div className="space-y-1 text-xs">
              <p className="font-mono text-[13px] text-foreground">{llm.note}</p>
              <p className="text-muted-foreground">endpoint: <code>{llm.base_url}</code></p>
              {llm.model_file && (
                <p className="text-muted-foreground">model: <code className="break-all">{llm.model_file.split(/[\\/]/).pop()}</code>. Auto-boots with the console; Groq is fallback.</p>
              )}
              {!llm.enabled && (
                <p className="text-muted-foreground">set LOCAL_LLM_ENABLED=true in .env, drop a .gguf in Downloads, restart the console.</p>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">checking…</p>
          )}
        </Tile>
        <Tile ok={conn ? conn.alpaca.configured : null} title="Alpaca">
          <p className="text-xs text-muted-foreground">{conn?.alpaca.how ?? "checking…"}</p>
          {conn?.alpaca.configured && (
            <p className="mt-1 font-mono text-xs">{conn.alpaca.paper ? "PAPER account" : "LIVE account"}</p>
          )}
        </Tile>
        <Tile ok={conn ? conn.groq.configured : null} title="Groq (agent brain)">
          <p className="text-xs text-muted-foreground">{conn?.groq.how ?? "checking…"}</p>
        </Tile>
        <Tile ok={mt5 ? (mt5.connected ? true : mt5.creds_set ? false : null) : null} title="MetaTrader 5">
          {mt5?.connected && mt5.account ? (
            <div className="space-y-1 text-xs">
              <p className="font-mono text-[13px] text-foreground">{mt5.account.name} · {mt5.account.trade_mode.toUpperCase()}</p>
              <p className="text-muted-foreground">{mt5.account.currency} {mt5.account.equity.toLocaleString()} · lev {mt5.account.leverage}× · {mt5.account.server}</p>
              {mt5.broker_symbols_sample.length > 0 && (
                <p className="text-[10px] text-muted-foreground">{mt5.broker_symbols_sample.length}+ broker symbols visible for halal screening</p>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              {mt5?.creds_set ? (mt5.error ?? "saved — restart console to attach") : "Paste your demo login below ↓"}
            </p>
          )}
        </Tile>
        <Tile ok={true} title="Webhook receiver">
          <div className="flex items-center gap-2">
            <code className="flex-1 truncate rounded bg-background px-2 py-1 font-mono text-xs">{webhookUrl}</code>
            <button
              onClick={async () => { await navigator.clipboard.writeText(webhookUrl); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
              className="rounded-md border border-border p-1.5 text-muted-foreground hover:text-foreground"
              aria-label="Copy webhook URL"
            >
              {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
            </button>
          </div>
          <p className="mt-2 text-[10px] text-muted-foreground">{conn?.webhook.note}</p>
        </Tile>
      </section>

      <section className="mt-6 rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
        <h3 className="mb-1 flex items-center gap-2 font-mono text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          <Landmark className="size-4" /> MT5 demo account
        </h3>
        <p className="mb-4 text-xs text-muted-foreground">
          From your broker's MT5: Tools → Options → or the login box on startup. Server name is exact
          (e.g. <code>MetaQuotes-Demo</code>). Credentials are stored in <code>.env</code> on this machine only.
          JARVIS refuses live accounts while demo mode is on.
        </p>
        <div className="grid gap-3 md:grid-cols-3">
          <label className="block">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-muted-foreground">login</span>
            <input value={mt5Login} onChange={(e) => setMt5Login(e.target.value)} placeholder="e.g. 51234567"
              className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm outline-none focus:ring-1 focus:ring-primary" />
          </label>
          <label className="block">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-muted-foreground">password</span>
            <input type="password" value={mt5Pass} onChange={(e) => setMt5Pass(e.target.value)} placeholder="••••••••"
              className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm outline-none focus:ring-1 focus:ring-primary" />
          </label>
          <label className="block">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-muted-foreground">server</span>
            <input value={mt5Server} onChange={(e) => setMt5Server(e.target.value)} placeholder="MetaQuotes-Demo"
              className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm outline-none focus:ring-1 focus:ring-primary" />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button onClick={() => saveMt5(true)} disabled={mt5Busy || !mt5Login || !mt5Pass || !mt5Server}
            className="rounded-md bg-primary px-4 py-2 font-mono text-xs font-semibold text-primary-foreground hover:brightness-110 disabled:opacity-40">
            {mt5Busy ? "connecting…" : "save & test connection"}
          </button>
          <button onClick={() => saveMt5(false)} disabled={mt5Busy || !mt5Login || !mt5Pass || !mt5Server}
            className="rounded-md border border-border px-4 py-2 font-mono text-xs hover:bg-accent disabled:opacity-40">
            save only
          </button>
          {mt5Msg && <span className={`font-mono text-xs ${mt5Msg.startsWith("✓") ? "text-emerald-400" : "text-red-400"}`}>{mt5Msg}</span>}
        </div>
        {!mt5?.package && (
          <p className="mt-3 text-xs text-amber-400">MetaTrader5 Python package missing — run: pip install MetaTrader5 (in .venv)</p>
        )}
        {!mt5?.connected && !mt5?.creds_set && conn && !conn.mt5.installed && (
          <ul className="mt-3 space-y-0.5 text-[10px] text-muted-foreground">
            {conn.mt5.guide.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        )}
      </section>

      <section className="mt-6">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          <Webhook className="size-4" /> Received alerts ({alerts.length})
        </h3>
        <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-border bg-card/60 p-4 font-mono text-xs backdrop-blur">
          {alerts.length ? (
            alerts.map((a, i) => (
              <div key={i} className="flex gap-2">
                <span className="text-muted-foreground">{a.ts.slice(11, 19)}</span>
                <span className="text-primary">{a.source}</span>
                <span className="truncate text-muted-foreground">{JSON.stringify(a.payload)}</span>
              </div>
            ))
          ) : (
            <span className="text-muted-foreground">
              No alerts yet. In TradingView create an alert → Notifications → Webhook URL → paste the URL above.
            </span>
          )}
        </div>
      </section>

      <section className="mt-6">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          TradingView charts
        </h3>
        <div className="mb-3 flex items-center gap-2">
          {["1", "5", "15", "60", "D"].map((v) => (
            <button
              key={v}
              onClick={() => setTf(v)}
              className={cn(
                "rounded-md px-2.5 py-1 font-mono text-xs transition-colors",
                tf === v
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              {v === "D" ? "1D" : `${v}m`}
            </button>
          ))}
          <span className="ml-auto font-mono text-xs text-muted-foreground">
            {status?.positions?.length
              ? `live: ${status.positions.map((p) => `${p.qty} ${p.symbol}`).join(', ')}`
              : "no open positions"}
          </span>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          {["MSFT", "NVDA"].map((s) => (
            <div key={s} className="overflow-hidden rounded-lg border border-border bg-card/60 backdrop-blur">
              <div className="border-b border-border px-4 py-2 font-mono text-sm">
                {s} · {tf === "D" ? "1D" : `${tf}m`}
              </div>
              <TVChart symbol={s} interval={tf} />
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
