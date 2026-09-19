import { useEffect, useState } from "react"
import { BookOpen, Bot, GraduationCap, Play, RefreshCw } from "lucide-react"

import { api } from "@/lib/api"
import type { AgentResponse } from "@/lib/types"
import { cn } from "@/lib/utils"
import { LiquidButton } from "@/components/ui/liquid-glass-button"

const STATUS_TONE: Record<string, string> = {
  adopted: "text-[var(--color-success)]",
  kept_incumbent: "text-[var(--color-warning)]",
  no_llm: "text-muted-foreground",
  rejected: "text-destructive",
  error: "text-destructive",
  skipped: "text-muted-foreground",
}

export default function Agent() {
  const [data, setData] = useState<AgentResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [reconciling, setReconciling] = useState(false)

  const load = async () => {
    try {
      setData(await api.agent())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  useEffect(() => {
    load()
  }, [])

  async function run() {
    setRunning(true)
    try {
      await api.evolve()
      await load()
    } finally {
      setRunning(false)
    }
  }

  async function reconcile() {
    setReconciling(true)
    try {
      await api.learnerRun()
      await load()
    } finally {
      setReconciling(false)
    }
  }

  const learning = data?.learning

  const results = data?.last_evolution?.results ?? {}
  const tone = (pnl: number | null | undefined) =>
    pnl == null ? "text-muted-foreground"
      : pnl > 0 ? "text-[var(--color-success)]" : "text-destructive"

  return (
    <div>
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="flex items-center gap-2 font-mono text-2xl font-bold tracking-widest text-primary">
            <Bot className="size-6" /> AGENT
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            The growth loop: learns from every trade → LLM proposes parameter changes → backtest decides → only winners adopted.
          </p>
        </div>
        <LiquidButton onClick={run} disabled={running}>
          <Play className="size-4" /> {running ? "Evolving…" : "Run evolution now"}
        </LiquidButton>
      </header>

      {/* ---------------- trade-learning panel ---------------- */}
      <section className="mb-6 rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            <GraduationCap className="size-4" /> Trade learner — every trade is a lesson
          </h3>
          <button
            onClick={reconcile}
            disabled={reconciling}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 font-mono text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw className={cn("size-3", reconciling && "animate-spin")} />
            {reconciling ? "Learning…" : "Reconcile + reflect now"}
          </button>
        </div>

        {learning && (learning.closed > 0 || learning.open > 0) ? (
          <>
            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
              {[
                { label: "closed", value: learning.closed },
                { label: "open", value: learning.open },
                { label: "hit rate", value: learning.hit_rate_pct != null ? `${learning.hit_rate_pct}%` : "—" },
                { label: "cumulative", value: `${learning.cumulative_pnl > 0 ? "+" : ""}${learning.cumulative_pnl.toFixed(2)}` },
                { label: "lessons", value: learning.lessons.length },
              ].map((s) => (
                <div key={s.label} className="rounded-md border border-border p-2.5 text-center">
                  <div className={cn("font-mono text-lg font-bold", s.label === "cumulative" && tone(learning.cumulative_pnl))}>
                    {s.value}
                  </div>
                  <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{s.label}</div>
                </div>
              ))}
            </div>
            {Object.keys(learning.by_exit_kind).length > 0 && (
              <div className="mb-4 flex flex-wrap gap-2 font-mono text-xs">
                {Object.entries(learning.by_exit_kind).map(([kind, v]) => (
                  <span key={kind} className="rounded-full border border-border px-2.5 py-0.5">
                    {kind.replace(/_/g, " ")}: <span className={tone(v.pnl)}>{v.pnl > 0 ? "+" : ""}{v.pnl.toFixed(2)}</span> ({v.n})
                  </span>
                ))}
              </div>
            )}
            <ul className="space-y-2">
              {learning.lessons.map((l, i) => (
                <li key={i} className="flex gap-2.5 rounded-md border border-border p-3 text-sm">
                  <BookOpen className="mt-0.5 size-4 shrink-0 text-primary/70" />
                  <div>
                    <span className="mr-2 rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] uppercase text-primary">{l.scope}</span>
                    {l.lesson}
                    <span className="ml-2 font-mono text-[10px] text-muted-foreground">{l.ts.slice(0, 16)} UTC</span>
                  </div>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            No trades captured yet — the ledger fills automatically as the cycle and manual trades execute. TP/SL exits reconcile from the broker every 10 minutes.
          </p>
        )}
      </section>

      {error && (
        <div className="mb-6 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Bridge offline: {error}
        </div>
      )}

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            Last evolution pass (now seeded with trade lessons)
          </h3>
          {data?.last_evolution ? (
            <>
              <p className="mb-3 font-mono text-xs text-muted-foreground">{data.last_evolution.at} UTC</p>
              <ul className="space-y-3">
                {Object.entries(results).map(([sym, r]) => (
                  <li key={sym} className="rounded-md border border-border p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-semibold">{sym}</span>
                      <span className={cn("font-mono text-xs uppercase", STATUS_TONE[r.status] ?? "text-foreground")}>
                        {r.status.replace(/_/g, " ")}
                      </span>
                    </div>
                    {r.challenger_return !== undefined && (
                      <p className="mt-1 font-mono text-xs text-muted-foreground">
                        challenger {r.challenger_return}% vs incumbent {r.incumbent_return}%
                      </p>
                    )}
                    {r.params && (
                      <p className="mt-1 font-mono text-xs text-[var(--color-success)]">
                        adopted: {JSON.stringify(r.params)}
                      </p>
                    )}
                    {r.why && <p className="mt-1 text-xs text-muted-foreground">{r.why}</p>}
                  </li>
                ))}
                {Object.keys(results).length === 0 && (
                  <li className="text-sm text-muted-foreground">No symbols processed yet.</li>
                )}
              </ul>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              No evolution run yet — add a Groq key (Connections page) and press "Run evolution now".
            </p>
          )}
        </div>

        <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            Recent trades (learning ledger)
          </h3>
          <div className="max-h-[28rem] space-y-2 overflow-y-auto">
            {data?.trades?.length ? data.trades.map((t) => (
              <div key={t.id} className="rounded-md border border-border p-3">
                <div className="flex items-center justify-between font-mono text-xs">
                  <span className="font-semibold">
                    {t.side.toUpperCase()} {t.qty} {t.symbol} @ {t.entry_price}
                  </span>
                  <span className={cn("uppercase", tone(t.pnl))}>
                    {t.closed_at
                      ? `${t.exit_kind?.replace(/_/g, " ")} · ${t.pnl != null ? (t.pnl > 0 ? "+" : "") + t.pnl.toFixed(2) : "—"}`
                      : "open"}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-2 font-mono text-[10px] text-muted-foreground">
                  {t.prob != null && <span>entry p={t.prob}</span>}
                  {t.sl_pct != null && <span>SL {t.sl_pct}%</span>}
                  {t.tp_pct != null && <span>TP {t.tp_pct}%</span>}
                  <span>{t.mode}</span>
                  <span>{t.opened_at.slice(0, 16)}</span>
                </div>
                {t.reason && <p className="mt-1 text-xs text-muted-foreground">{t.reason}</p>}
              </div>
            )) : (
              <p className="text-sm text-muted-foreground">No trades in the ledger yet.</p>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
