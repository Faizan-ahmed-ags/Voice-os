import { useEffect, useState } from "react"
import { CalendarClock, ShieldCheck } from "lucide-react"

import { api } from "@/lib/api"
import type { PlanResponse } from "@/lib/types"
import { cn } from "@/lib/utils"

export default function Plan() {
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.plan().then(setPlan).catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
        Bridge offline: {error}
      </div>
    )
  }
  if (!plan) return <p className="text-sm text-muted-foreground">Loading plan…</p>

  return (
    <div>
      <header className="mb-6">
        <h2 className="flex items-center gap-2 font-mono text-2xl font-bold tracking-widest text-primary">
          <CalendarClock className="size-6" /> PLAN
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">What JARVIS trades, under which rules, and when.</p>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        {plan.symbols.map((s) => (
          <div key={s.symbol} className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
            <div className="flex items-center justify-between">
              <span className="font-mono text-lg font-bold">{s.symbol}</span>
              {s.halal && (
                <span className={cn(
                  "flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-mono",
                  s.halal.compliant
                    ? "bg-[var(--color-success)]/10 text-[var(--color-success)]"
                    : "bg-destructive/10 text-destructive",
                )}>
                  <ShieldCheck className="size-3" /> {s.halal.compliant ? "HALAL" : "FAIL"}
                </span>
              )}
            </div>
            <dl className="mt-3 space-y-1 font-mono text-xs text-muted-foreground">
              <div className="flex justify-between"><dt>model</dt>
                <dd>{s.model ? `${s.model.status} · AUC ${s.model.auc?.toFixed(2)}` : "—"}</dd></div>
              <div className="flex justify-between"><dt>params</dt>
                <dd className="text-right">{typeof s.params === "string" ? s.params : JSON.stringify(s.params)}</dd></div>
              {s.backtest && !s.backtest.error && (
                <>
                  <div className="flex justify-between"><dt>backtest</dt>
                    <dd className={cn((s.backtest.return_pct ?? 0) > 0 ? "text-[var(--color-success)]" : "text-destructive")}>
                      {s.backtest.return_pct?.toFixed(2)}% vs B&H {s.backtest.buy_hold_pct?.toFixed(1)}%
                    </dd></div>
                  <div className="flex justify-between"><dt>sharpe / maxDD</dt>
                    <dd>{s.backtest.sharpe?.toFixed(2)} / {s.backtest.max_drawdown_pct?.toFixed(1)}%</dd></div>
                  <div className="flex justify-between"><dt>out-of-sample</dt>
                    <dd>{s.backtest.oos_days} days</dd></div>
                </>
              )}
            </dl>
            {s.halal?.ratios && (
              <p className="mt-2 text-[10px] text-muted-foreground">
                ratios: debt {(s.halal.ratios.debt * 100).toFixed(1)}% · cash {(s.halal.ratios.cash_int * 100).toFixed(1)}% · recv {(s.halal.ratios.receivables * 100).toFixed(1)}%
              </p>
            )}
          </div>
        ))}
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            Guardrails (agent may never exceed these)
          </h3>
          <table className="w-full font-mono text-xs">
            <thead><tr className="text-left text-muted-foreground">
              <th className="pb-2">param</th><th className="pb-2">min</th><th className="pb-2">max</th>
            </tr></thead>
            <tbody>
              {Object.entries(plan.guardrails).map(([k, v]) => (
                <tr key={k} className="border-t border-border/50">
                  <td className="py-1.5">{k}</td><td>{v.min}</td><td>{v.max}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-4 space-y-1 font-mono text-xs text-muted-foreground">
            <p>daily kill-switch: pause below −{plan.risk.max_daily_loss_pct}% day P&L</p>
            <p>starting cash: ${plan.risk.starting_cash.toLocaleString()} · paper: {String(plan.risk.paper_trading)}</p>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">Schedule</h3>
          <dl className="space-y-2 font-mono text-sm">
            <div className="flex justify-between"><dt className="text-muted-foreground">daily run-once</dt><dd>{plan.schedule.daily_run_time} UTC</dd></div>
            <div className="flex justify-between"><dt className="text-muted-foreground">evolution</dt><dd>{plan.schedule.evolve}</dd></div>
          </dl>
          <p className="mt-3 text-xs text-muted-foreground">{plan.schedule.note}</p>
        </div>
      </section>
    </div>
  )
}
