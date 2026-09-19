import { useEffect, useMemo, useState } from "react"

import { api } from "@/lib/api"
import type { PnlResponse } from "@/lib/types"

const MODE_BADGE: Record<string, string> = {
  "mt5-demo": "MT5",
  sim: "SIM",
  seed: "SEED",
}

function monthLabel(m: string) {
  const [y, mo] = m.split("-").map(Number)
  return new Date(y, mo - 1, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" })
}

function shiftMonth(m: string, delta: number) {
  const [y, mo] = m.split("-").map(Number)
  const d = new Date(y, mo - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
}

export default function CalendarPage() {
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7))
  const [data, setData] = useState<PnlResponse | null>(null)
  const [selDay, setSelDay] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.pnl(month, selDay ?? undefined).then((d) => {
      setData(d)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [month, selDay])

  const grid = useMemo(() => {
    const [y, mo] = month.split("-").map(Number)
    const first = new Date(y, mo - 1, 1)
    const daysInMonth = new Date(y, mo, 0).getDate()
    const lead = first.getDay()
    const cells: (number | null)[] = Array(lead).fill(null)
    for (let d = 1; d <= daysInMonth; d++) cells.push(d)
    while (cells.length % 7 !== 0) cells.push(null)
    return cells
  }, [month])

  const dayMap = useMemo(() => {
    const m: Record<string, PnlResponse["days"][number]> = {}
    for (const d of data?.days ?? []) m[d.date] = d
    return m
  }, [data])

  const sel = data?.day ?? null

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-mono text-2xl font-bold tracking-[0.2em] text-primary">
          CALENDAR
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Daily profit &amp; loss — every day JARVIS trades gets a cell. Green grows, red bleeds.
        </p>
      </header>

      {/* today guard strip */}
      {data?.today_state && (
        <div className={`flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border px-4 py-3 font-mono text-sm ${
          data.today_state.blocked
            ? "border-red-900/60 bg-red-950/30 text-red-300"
            : "border-border bg-card text-muted-foreground"
        }`}>
          <span>TODAY {data.today_state.pnl >= 0 ? "🟢" : "🔴"} <b className="text-foreground">{data.today_state.pnl >= 0 ? "+" : ""}{data.today_state.pnl.toFixed(2)}</b> ({data.today_state.pnl_pct.toFixed(2)}%)</span>
          <span>equity <b className="text-foreground">{data.today_state.equity.toLocaleString()}</b></span>
          <span>daily cap −{data.today_state.max_daily_loss_pct}%</span>
          <span>risk/trade {data.today_state.risk_per_trade_pct}%</span>
          {data.today_state.blocked && <span className="font-bold text-red-400">⛔ CIRCUIT BREAKER — TRADING HALTED TODAY</span>}
        </div>
      )}

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-4 flex items-center justify-between">
          <div className="font-mono text-lg font-semibold tracking-widest">{monthLabel(month).toUpperCase()}</div>
          <div className="flex items-center gap-2">
            <button onClick={() => setMonth(shiftMonth(month, -1))}
              className="rounded border border-border px-3 py-1 font-mono text-sm hover:bg-accent">‹ prev</button>
            <button onClick={() => setMonth(new Date().toISOString().slice(0, 7))}
              className="rounded border border-border px-3 py-1 font-mono text-xs hover:bg-accent">today</button>
            <button onClick={() => setMonth(shiftMonth(month, 1))}
              className="rounded border border-border px-3 py-1 font-mono text-sm hover:bg-accent">next ›</button>
          </div>
        </div>

        <div className="grid grid-cols-7 gap-1.5">
          {["sun", "mon", "tue", "wed", "thu", "fri", "sat"].map((d) => (
            <div key={d} className="pb-1 text-center font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{d}</div>
          ))}
          {grid.map((d, i) => {
            if (d === null) return <div key={`e${i}`} />
            const dateStr = `${month}-${String(d).padStart(2, "0")}`
            const rec = dayMap[dateStr]
            const pos = rec && rec.realized > 0
            const neg = rec && rec.realized < 0
            return (
              <button key={dateStr}
                onClick={() => setSelDay(rec ? dateStr : null)}
                className={`relative flex h-20 flex-col justify-between rounded border p-1.5 text-left transition-colors ${
                  rec ? (selDay === dateStr ? "ring-1 ring-primary" : "cursor-pointer hover:brightness-125") : "cursor-default"
                } ${pos ? "border-emerald-900/60 bg-emerald-950/40" : neg ? "border-red-900/60 bg-red-950/40" : "border-border/60 bg-background/40"}`}>
                <span className="font-mono text-[11px] text-muted-foreground">{d}</span>
                {rec && (
                  <span className="flex flex-col gap-0.5">
                    <span className={`font-mono text-sm font-bold leading-none ${pos ? "text-emerald-400" : neg ? "text-red-400" : "text-muted-foreground"}`}>
                      {pos ? "+" : ""}{rec.realized.toFixed(0)}
                    </span>
                    <span className="font-mono text-[9px] text-muted-foreground">
                      {rec.trades}t {MODE_BADGE[rec.mode] ?? rec.mode.toUpperCase()}
                    </span>
                  </span>
                )}
              </button>
            )
          })}
        </div>

        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-t border-border pt-3 font-mono text-sm">
          <span>month total <b className={data && data.total >= 0 ? "text-emerald-400" : "text-red-400"}>{data ? `${data.total >= 0 ? "+" : ""}${data.total.toFixed(2)}` : "—"}</b></span>
          <span className="text-emerald-400">{data?.green_days ?? 0} green</span>
          <span className="text-red-400">{data?.red_days ?? 0} red</span>
          {loading && <span className="text-muted-foreground">loading…</span>}
        </div>
      </div>

      {sel && (
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="font-mono font-semibold tracking-widest">{sel.date} — TRADES</div>
            <button onClick={() => setSelDay(null)} className="font-mono text-xs text-muted-foreground hover:text-foreground">close ✕</button>
          </div>
          <div className="mb-3 grid grid-cols-2 gap-3 font-mono text-xs text-muted-foreground sm:grid-cols-4">
            <span>start <b className="text-foreground">{sel.start_equity.toLocaleString()}</b></span>
            <span>end <b className="text-foreground">{sel.end_equity.toLocaleString()}</b></span>
            <span>realized <b className={sel.realized >= 0 ? "text-emerald-400" : "text-red-400"}>{sel.realized >= 0 ? "+" : ""}{sel.realized.toFixed(2)}</b></span>
            <span>W/L <b className="text-foreground">{sel.wins}/{sel.losses}</b></span>
          </div>
          {sel.trades_detail?.length ? (
            <div className="space-y-1.5">
              {sel.trades_detail.map((t, i) => (
                <div key={i} className="flex items-center gap-3 rounded border border-border/60 px-3 py-1.5 font-mono text-xs">
                  <span className="text-muted-foreground">{t.ts.slice(11, 19)}</span>
                  <span className={`font-bold ${t.action === "BUY" ? "text-emerald-400" : "text-red-400"}`}>{t.action}</span>
                  <span>{t.symbol}</span>
                  <span className="text-muted-foreground">{t.qty} @ {t.price}</span>
                  <span className="ml-auto text-muted-foreground">{t.mode}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No individual trades recorded for this day.</p>
          )}
        </div>
      )}
    </div>
  )
}
