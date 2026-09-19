import { useCallback, useEffect, useState } from "react"
import { MessageSquare, Trash2 } from "lucide-react"

import { api } from "@/lib/api"
import type { ChatEntry, TradesResponse } from "@/lib/types"
import { cn } from "@/lib/utils"
import { LiquidButton } from "@/components/ui/liquid-glass-button"

export default function Chats() {
  const [chats, setChats] = useState<ChatEntry[]>([])
  const [trades, setTrades] = useState<TradesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState("")

  const load = useCallback(async () => {
    try {
      const [c, t] = await Promise.all([api.chats(), api.trades()])
      setChats(c.chats)
      setTrades(t)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [load])

  async function clearAll() {
    await api.clearChats()
    load()
  }

  const shown = chats.filter(
    (c) => !filter || c.text.toLowerCase().includes(filter.toLowerCase()) || c.kind === filter,
  )

  return (
    <div>
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="flex items-center gap-2 font-mono text-2xl font-bold tracking-widest text-primary">
            <MessageSquare className="size-6" /> CHATS & TRADES
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Every conversation with JARVIS (all sessions, stored in SQLite) and every paper decision.
          </p>
        </div>
        <LiquidButton size="sm" variant="outline" onClick={clearAll}>
          <Trash2 className="size-4" /> Clear chats
        </LiquidButton>
      </header>

      {error && (
        <div className="mb-6 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Bridge offline: {error}
        </div>
      )}

      <section className="grid gap-6 lg:grid-cols-5">
        <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur lg:col-span-3">
          <div className="mb-3 flex items-center gap-2">
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="filter chats…"
              className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 font-mono text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <span className="font-mono text-xs text-muted-foreground">{shown.length} msgs</span>
          </div>
          <div className="max-h-[32rem] space-y-2 overflow-y-auto font-mono text-sm">
            {shown.map((c, i) => (
              <div key={i} className="flex gap-2">
                <span className="shrink-0 text-muted-foreground">{c.ts.slice(11, 19)}</span>
                <span className={cn(
                  c.kind === "you" && "text-foreground",
                  c.kind === "jarvis" && "text-primary",
                  c.kind === "system" && "text-muted-foreground",
                )}>
                  {c.kind === "you" ? "› " : c.kind === "jarvis" ? "JARVIS: " : "· "}
                  {c.text}
                  <span className="ml-1 text-[10px] opacity-40">[{c.page}]</span>
                </span>
              </div>
            ))}
            {!shown.length && (
              <p className="text-sm text-muted-foreground">
                No chats yet — use the voice orb (bottom-right) or ask something on Home.
              </p>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur lg:col-span-2">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            Trade history {trades ? `· ${trades.mode}` : ""}
          </h3>
          <div className="max-h-[32rem] space-y-2 overflow-y-auto font-mono text-xs">
            {trades?.decisions.length ? (
              trades.decisions.map((d, i) => (
                <div key={i} className="rounded-md border border-border/60 p-2">
                  <div className="flex justify-between">
                    <span className="font-semibold">{d.ts.slice(0, 16).replace("T", " ")}</span>
                    <span className={cn(
                      "uppercase",
                      d.action === "buy" ? "text-[var(--color-success)]" : d.action === "sell" ? "text-destructive" : "text-muted-foreground",
                    )}>
                      {d.action} {d.symbol}
                    </span>
                  </div>
                  <p className="mt-1 text-muted-foreground">
                    qty {d.qty} @ ${d.price} [{d.mode}]
                  </p>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">{d.reason}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">
                No trades yet. The brain trades only when a model passes the AUC edge gate + halal screen.
              </p>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
