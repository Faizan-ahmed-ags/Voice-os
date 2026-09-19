import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Activity, ArrowRight, ArrowDownCircle, ArrowUpCircle, Bot, Brain, CalendarDays, RefreshCw, ShieldCheck } from "lucide-react"

import { api } from "@/lib/api"
import type { CycleStatus, PositionsResponse, StatusResponse } from "@/lib/types"
import { cn } from "@/lib/utils"
import VoiceConsole, { useSessionLog } from "@/components/VoiceConsole"
import { LiquidButton } from "@/components/ui/liquid-glass-button"

function useStatus() {
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const refresh = async () => {
    try {
      setStatus(await api.status())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 15000)
    return () => clearInterval(t)
  }, [])
  return { status, error, refresh }
}

function StatCard({
  icon, label, value, sub, tone = "default",
}: {
  icon: React.ReactNode; label: string; value: string; sub?: string
  tone?: "default" | "good" | "warn" | "bad"
}) {
  const toneClass = {
    default: "text-foreground", good: "text-[var(--color-success)]",
    warn: "text-[var(--color-warning)]", bad: "text-destructive",
  }[tone]
  return (
    <div className="rounded-lg border border-border bg-card/60 p-4 backdrop-blur">
      <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
        {icon}{label}
      </div>
      <div className={cn("mt-2 font-mono text-2xl font-semibold", toneClass)}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  )
}

function useCycle() {
  const [cycle, setCycle] = useState<CycleStatus | null>(null)
  const refresh = () => api.cycle().then(setCycle).catch(() => {})
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 20000)
    return () => clearInterval(t)
  }, [])
  return { cycle, refresh }
}

function usePositions() {
  const [pos, setPos] = useState<PositionsResponse | null>(null)
  const refresh = () => api.positions().then(setPos).catch(() => {})
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 15000)
    return () => clearInterval(t)
  }, [])
  return { pos, refresh }
}

export default function Home() {
  const { status, error, refresh } = useStatus()
  const { cycle, refresh: refreshCycle } = useCycle()
  const { pos, refresh: refreshPos } = usePositions()
  const { log, add } = useSessionLog()
  const [working, setWorking] = useState<string | null>(null)

  async function runCycleNow() {
    setWorking("cycle")
    add({ at: new Date().toLocaleTimeString(), text: "running daily cycle (learn → predict → trade)…", kind: "system" })
    try {
      const res = (await api.runCycle()) as { ok?: boolean; orders?: string[]; learned_auc?: Record<string, number | null> }
      const aucs = Object.entries(res.learned_auc ?? {}).map(([s, a]) => `${s} ${a == null ? "✕" : `AUC ${a}`}`).join(", ")
      add({ at: new Date().toLocaleTimeString(), text: `cycle done — ${res.orders?.length ?? 0} orders (${aucs})`, kind: "jarvis" })
    } catch (e) {
      add({ at: new Date().toLocaleTimeString(), text: e instanceof Error ? e.message : String(e), kind: "system" })
    } finally {
      setWorking(null)
      refresh()
      refreshCycle()
    }
  }

  async function run(kind: "screen" | "train" | "evolve", label: string) {
    setWorking(kind)
    add({ at: new Date().toLocaleTimeString(), text: `${label}…`, kind: "system" })
    try {
      const fn = kind === "screen" ? api.screen : kind === "train" ? api.train : api.evolve
      const res = (await fn()) as { reply: string }
      add({ at: new Date().toLocaleTimeString(), text: res.reply, kind: "jarvis" })
    } catch (e) {
      add({ at: new Date().toLocaleTimeString(), text: e instanceof Error ? e.message : String(e), kind: "system" })
    } finally {
      setWorking(null)
      refresh()
    }
  }

  const paper = status ? !status.mode.includes("alpaca") || status.paper : true
  const recent = log.slice(-6).reverse()

  async function manual(side: "buy" | "sell") {
    setWorking(`manual-${side}`)
    add({ at: new Date().toLocaleTimeString(), text: `manual ${side} order (risk-gated, halal-checked)…`, kind: "system" })
    try {
      const res = await api.manualOrder(side, "MSFT")
      if (res.ok) {
        const px = res.price ? ` @ $${res.price}` : ""
        add({ at: new Date().toLocaleTimeString(), text: `${side.toUpperCase()} filled${px} — position is live on MT5`, kind: "jarvis" })
      } else {
        add({ at: new Date().toLocaleTimeString(), text: `order refused: ${res.error ?? "unknown"}`, kind: "system" })
      }
    } catch (e) {
      add({ at: new Date().toLocaleTimeString(), text: e instanceof Error ? e.message : String(e), kind: "system" })
    } finally {
      setWorking(null)
      refresh()
      refreshPos()
    }
  }

  return (
    <div>
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="font-mono text-2xl font-bold tracking-widest text-primary">HOME</h2>
          <p className="mt-1 text-sm text-muted-foreground">Live paper-trading status</p>
        </div>
        <span
          className={cn(
            "rounded-full border px-3 py-1 font-mono text-xs",
            paper
              ? "border-[var(--color-warning)]/40 bg-[var(--color-warning)]/10 text-[var(--color-warning)]"
              : "border-[var(--color-success)]/40 bg-[var(--color-success)]/10 text-[var(--color-success)]",
          )}
        >
          {status?.mode ?? "…"}
        </span>
      </header>

      {error && (
        <div className="mb-6 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Bridge offline: {error}. Start with <code>python -m brain.bridge</code>.
        </div>
      )}

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard icon={<Activity className="size-4" />} label="Equity"
          value={status ? `$${status.equity.toLocaleString()}` : "—"} sub="paper account" />
        <StatCard icon={<ShieldCheck className="size-4" />} label="Halal gate" value="active"
          sub="whitelist + AAOIFI ratios" tone="good" />
        <StatCard icon={<Brain className="size-4" />} label="Models"
          value={status ? `${Object.values(status.models).filter((m) => m.status === "champion").length}/${Object.keys(status.models).length || 0}` : "—"}
          sub="champions / total"
          tone={status && Object.values(status.models).some((m) => m.status === "champion") ? "good" : "warn"} />
        <StatCard icon={<Bot className="size-4" />} label="Evolution"
          value={status?.last_evolution ? "ran" : "idle"}
          sub={status?.last_evolution?.at ?? "no Groq key = muted"}
          tone={status?.last_evolution ? "good" : "default"} />
      </section>

      <section className="mt-6 rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            <CalendarDays className="size-4" /> Daily cycle — learn → predict → trade
          </h3>
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-muted-foreground">
              {cycle ? `${cycle.schedule} · broker ${cycle.broker} · risk ${cycle.risk.risk_per_trade_pct}%/day-cap −${cycle.risk.max_daily_loss_pct}%` : "loading schedule…"}
            </span>
            <LiquidButton size="sm" onClick={runCycleNow} disabled={working !== null || (cycle?.in_progress ?? false)}>
              <RefreshCw className={cn("size-4", working === "cycle" && "animate-spin")} />
              {working === "cycle" || cycle?.in_progress ? "running…" : "Run cycle now"}
            </LiquidButton>
          </div>
        </div>
        {cycle?.last_cycle ? (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 font-mono text-xs text-muted-foreground">
            <span>last run <b className="text-foreground">{cycle.last_cycle.ts.slice(11, 16)} UTC</b> ({cycle.last_cycle.trigger})</span>
            <span>scanned <b className="text-foreground">{cycle.last_cycle.symbols_scanned}</b></span>
            <span>orders <b className="text-foreground">{cycle.last_cycle.orders_placed}</b></span>
            {Object.entries(cycle.last_cycle.predictions ?? {}).slice(0, 4).map(([sym, p]) => {
              const pred = p as { action?: string; prob?: number | null }
              return (
                <span key={sym}>
                  {sym}: <b className={pred.action === "buy" ? "text-emerald-400" : pred.action === "skip" || pred.action === "blocked" ? "text-red-400" : "text-foreground"}>{pred.action ?? "?"}</b>
                  {pred.prob != null && ` (p=${pred.prob})`}
                </span>
              )
            })}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">No cycle yet — press “Run cycle now” or wait for {cycle?.schedule ?? "the schedule"}.</p>
        )}
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-5">
        <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur lg:col-span-3">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">Quick actions</h3>
          <div className="grid gap-2">
            <LiquidButton size="lg" onClick={() => run("screen", "Running halal compliance screen")} disabled={working !== null}>
              Screen halal universe
            </LiquidButton>
            <LiquidButton size="lg" onClick={() => run("train", "Training models (walk-forward CV)")} disabled={working !== null}>
              Train models
            </LiquidButton>
            <LiquidButton size="lg" onClick={() => run("evolve", "Evolution pass")} disabled={working !== null}>
              {working === "evolve" ? "Evolving…" : "Evolve strategies"}
            </LiquidButton>
          </div>
          <h3 className="mt-6 mb-2 text-sm font-semibold uppercase tracking-widest text-muted-foreground">Recent activity</h3>
          <div className="max-h-56 space-y-2 overflow-y-auto font-mono text-sm">
            {recent.map((e, i) => (
              <div key={i} className="flex gap-2">
                <span className="shrink-0 text-muted-foreground">{e.at}</span>
                <span className={cn(
                  e.kind === "you" && "text-foreground",
                  e.kind === "jarvis" && "text-primary",
                  e.kind === "system" && "text-muted-foreground",
                )}>
                  {e.kind === "you" ? "› " : e.kind === "jarvis" ? "JARVIS: " : "· "}{e.text}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-4 lg:col-span-2">
          <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
            <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">Live positions</h3>
            {pos && pos.positions.length > 0 ? (
              <ul className="space-y-3 font-mono text-sm">
                {pos.positions.map((p) => (
                  <li key={p.symbol} className="rounded-md border border-border/60 bg-background/40 p-3">
                    <div className="flex justify-between items-center">
                      <span className="font-semibold text-primary">{p.symbol}</span>
                      <span>{p.qty} @ ${p.entry ?? "?"}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                      <span className="rounded bg-primary/10 px-1.5 py-0.5 text-primary">{p.strategy}</span>
                      {p.opened_at && <span>since {p.opened_at.slice(0, 16).replace("T", " ")} UTC</span>}
                    </div>
                    {p.reason && <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{p.reason}</p>}
                  </li>
                ))}
              </ul>
            ) : status && status.positions.length > 0 ? (
              <ul className="space-y-2 font-mono text-sm">
                {status.positions.map((p) => (
                  <li key={p.symbol} className="flex justify-between">
                    <span>{p.symbol}</span><span>{p.qty} @ ${p.basis}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No open positions.</p>
            )}
          </div>
          <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
            <h3 className="mb-1 text-sm font-semibold uppercase tracking-widest text-muted-foreground">Manual order</h3>
            <p className="mb-3 text-[11px] text-muted-foreground">MSFT · same halal + risk gates as the agent (1% risk, −4.5% SL, +6% TP)</p>
            <div className="grid grid-cols-2 gap-2">
              <LiquidButton
                size="sm"
                className="border border-emerald-500/40 bg-emerald-500/15 text-emerald-500 hover:bg-emerald-500/25"
                onClick={() => manual("buy")}
                disabled={working !== null}
              >
                <ArrowUpCircle className="size-4" /> BUY
              </LiquidButton>
              <LiquidButton
                size="sm"
                className="border border-red-500/40 bg-red-500/15 text-red-500 hover:bg-red-500/25"
                onClick={() => manual("sell")}
                disabled={working !== null}
              >
                <ArrowDownCircle className="size-4" /> SELL
              </LiquidButton>
            </div>
            {working?.startsWith("manual-") && (
              <p className="mt-2 text-[11px] text-muted-foreground">routing order to MT5…</p>
            )}
          </div>
          <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-widest text-muted-foreground">Jump to</h3>
            <div className="grid gap-2 text-sm">
              <Link to="/agent" className="flex items-center justify-between rounded-md px-3 py-2 hover:bg-accent">
                Agent activity <ArrowRight className="size-4" />
              </Link>
              <Link to="/plan" className="flex items-center justify-between rounded-md px-3 py-2 hover:bg-accent">
                Trading plan & rules <ArrowRight className="size-4" />
              </Link>
              <Link to="/connections" className="flex items-center justify-between rounded-md px-3 py-2 hover:bg-accent">
                Broker connections <ArrowRight className="size-4" />
              </Link>
              <Link to="/calendar" className="flex items-center justify-between rounded-md px-3 py-2 hover:bg-accent">
                Daily P&L calendar <ArrowRight className="size-4" />
              </Link>
              <Link to="/chart" className="flex items-center justify-between rounded-md px-3 py-2 hover:bg-accent">
                Trade map (charts) <ArrowRight className="size-4" />
              </Link>
              <Link to="/journal" className="flex items-center justify-between rounded-md px-3 py-2 hover:bg-accent">
                Daily journal <ArrowRight className="size-4" />
              </Link>
            </div>
          </div>
          <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
            <VoiceConsole />
          </div>
        </div>
      </section>
    </div>
  )
}
