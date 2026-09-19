import { useEffect, useState } from "react"
import { BookOpen, ChevronLeft, ChevronRight, Flame, Moon, NotebookPen, Sun, TrendingDown, TrendingUp } from "lucide-react"

import { api } from "@/lib/api"
import type { JournalDay, JournalResponse } from "@/lib/types"
import { cn } from "@/lib/utils"
import { LiquidButton } from "@/components/ui/liquid-glass-button"

const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"]

const VERDICT_STYLE: Record<string, { badge: string; card: string; emoji: string; word: string }> = {
  great: { badge: "bg-emerald-500/15 text-emerald-500 border-emerald-500/40", card: "border-emerald-500/25", emoji: "🌱", word: "A green day" },
  down: { badge: "bg-red-500/10 text-red-400 border-red-500/40", card: "border-red-500/25", emoji: "🌧️", word: "A red day" },
  flat: { badge: "bg-amber-500/10 text-amber-500 border-amber-500/40", card: "border-amber-500/20", emoji: "⚖️", word: "Break-even" },
  quiet: { badge: "bg-sky-500/10 text-sky-500 border-sky-500/40", card: "border-sky-500/20", emoji: "🌙", word: "A quiet day" },
}

function DayCard({ day }: { day: JournalDay }) {
  const v = VERDICT_STYLE[day.verdict] ?? VERDICT_STYLE.quiet
  const [yr, mo, d] = day.date.split("-").map(Number)
  const date = new Date(Date.UTC(yr, mo - 1, d))
  const dayName = DAY_NAMES[date.getUTCDay()]
  const winRate = day.trades ? Math.round((day.wins / day.trades) * 100) : null
  return (
    <article className={cn("overflow-hidden rounded-xl border bg-card/70 backdrop-blur", v.card)}>
      <header className="flex items-center justify-between border-b border-border/60 px-5 py-3">
        <div>
          <div className="font-mono text-sm font-semibold text-foreground">
            {dayName} · {date.getUTCDate()} {MONTHS[date.getUTCMonth()]} {yr}
          </div>
          <div className="text-[11px] text-muted-foreground">
            {v.word} · mode {day.mode}
            {day.cycle && ` · cycle ${day.cycle.trigger} (${day.cycle.orders} orders)`}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn("rounded-full border px-2.5 py-0.5 text-[11px] font-medium", v.badge)}>
            {v.emoji} {day.realized >= 0 ? "+" : ""}${day.realized.toFixed(2)}
          </span>
        </div>
      </header>

      <div className="grid grid-cols-3 gap-2 px-5 py-3 text-center">
        <div className="rounded-lg bg-background/50 px-2 py-2">
          <div className="font-mono text-lg font-semibold">${day.end_equity.toLocaleString()}</div>
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">closing equity</div>
        </div>
        <div className="rounded-lg bg-background/50 px-2 py-2">
          <div className="font-mono text-lg font-semibold">{day.trades}</div>
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">trades</div>
        </div>
        <div className="rounded-lg bg-background/50 px-2 py-2">
          <div className={cn("font-mono text-lg font-semibold", day.realized >= 0 ? "text-emerald-500" : day.realized < 0 ? "text-red-400" : "")}>
            {day.realized >= 0 ? "+" : ""}{day.trades ? `${((day.realized / day.start_equity) * 100).toFixed(2)}%` : "0%"}
          </div>
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">day return</div>
        </div>
      </div>

      {day.trade_rows.length > 0 && (
        <div className="px-5 pb-3">
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            <NotebookPen className="size-3" /> The story, trade by trade
          </div>
          <div className="space-y-2">
            {day.trade_rows.map((t, i) => (
              <div key={i} className="rounded-lg border border-border/50 bg-background/40 p-2.5 text-xs">
                <div className="flex flex-wrap items-center gap-2 font-mono">
                  <span className="text-muted-foreground">{t.time}</span>
                  <span className={t.side === "buy" ? "font-semibold text-emerald-500" : "font-semibold text-red-400"}>
                    {t.side.toUpperCase()} {t.qty} {t.symbol}
                  </span>
                  <span>@ ${t.entry}{t.exit != null ? ` → $${t.exit}` : " → still open"}</span>
                  <span className="rounded bg-primary/10 px-1.5 text-primary">{t.strategy}</span>
                  {t.exit_kind && (
                    <span className="rounded border border-border px-1.5 text-[10px] text-muted-foreground">{t.exit_kind}</span>
                  )}
                  {t.pnl != null && (
                    <span className={cn("font-semibold", t.pnl >= 0 ? "text-emerald-500" : "text-red-400")}>
                      {t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}
                    </span>
                  )}
                </div>
                {t.reason && (
                  <p className="mt-1 text-[11px] leading-snug text-muted-foreground">“{t.reason}”</p>
                )}
              </div>
            ))}
          </div>
          {winRate != null && (
            <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
              {day.realized >= 0 ? <TrendingUp className="size-3.5 text-emerald-500" /> : <TrendingDown className="size-3.5 text-red-400" />}
              {day.wins}W / {day.losses}L ({winRate}% hit rate)
            </div>
          )}
        </div>
      )}

      {day.lessons.length > 0 && (
        <div className="border-t border-border/60 px-5 py-3">
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            <Flame className="size-3" /> What the agent learned
          </div>
          <ul className="space-y-1 text-[11px] leading-snug text-muted-foreground">
            {day.lessons.map((l, i) => (
              <li key={i} className="flex gap-1.5"><span className="text-primary">›</span>{l}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  )
}

export default function JournalPage() {
  const now = new Date()
  const [ym, setYm] = useState(`${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`)
  const [data, setData] = useState<JournalResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.journal(ym).then(setData).catch(() => setData(null)).finally(() => setLoading(false))
  }, [ym])

  const shiftMonth = (delta: number) => {
    const [y, m] = ym.split("-").map(Number)
    const d = new Date(Date.UTC(y, m - 1 + delta, 1))
    setYm(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`)
  }
  const [yy, mm] = ym.split("-").map(Number)
  const monthLabel = `${MONTHS[mm - 1]} ${yy}`

  return (
    <div>
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="flex items-center gap-2 font-mono text-2xl font-bold tracking-widest text-primary">
            <BookOpen className="size-6" /> DAILY JOURNAL
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">Every day's story — trades, reasons, results, lessons</p>
        </div>
        <div className="flex items-center gap-2">
          <LiquidButton size="icon" onClick={() => shiftMonth(-1)} aria-label="Previous month">
            <ChevronLeft className="size-4" />
          </LiquidButton>
          <span className="min-w-36 text-center font-mono text-sm text-muted-foreground">{monthLabel}</span>
          <LiquidButton size="icon" onClick={() => shiftMonth(1)} aria-label="Next month">
            <ChevronRight className="size-4" />
          </LiquidButton>
        </div>
      </header>

      {data && (
        <div className="mb-6 grid grid-cols-3 gap-4">
          <div className="rounded-lg border border-border bg-card/60 p-4 text-center backdrop-blur">
            <div className={cn("font-mono text-2xl font-bold", data.total >= 0 ? "text-emerald-500" : "text-red-400")}>
              {data.total >= 0 ? "+" : ""}${data.total.toFixed(2)}
            </div>
            <div className="mt-1 text-[10px] uppercase tracking-widest text-muted-foreground">month P&L</div>
          </div>
          <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/5 p-4 text-center backdrop-blur">
            <div className="font-mono text-2xl font-bold text-emerald-500">{data.green_days}</div>
            <div className="mt-1 flex items-center justify-center gap-1 text-[10px] uppercase tracking-widest text-muted-foreground">
              <Sun className="size-3" /> green days
            </div>
          </div>
          <div className="rounded-lg border border-red-500/25 bg-red-500/5 p-4 text-center backdrop-blur">
            <div className="font-mono text-2xl font-bold text-red-400">{data.red_days}</div>
            <div className="mt-1 flex items-center justify-center gap-1 text-[10px] uppercase tracking-widest text-muted-foreground">
              <Moon className="size-3" /> red days
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">opening the journal…</p>
      ) : data && data.days.length > 0 ? (
        <div className="space-y-4">
          {data.days.map((d) => <DayCard key={d.date} day={d} />)}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No days journalled for {monthLabel} yet.</p>
      )}
    </div>
  )
}
