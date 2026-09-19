import { useEffect, useState } from "react"
import { ExternalLink, GitBranch, Globe } from "lucide-react"

import { api } from "@/lib/api"
import type { NewsResponse } from "@/lib/types"

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return <span className="text-xs text-muted-foreground">collecting data…</span>
  const max = Math.max(...points, 1)
  return (
    <div className="flex h-8 items-end gap-0.5">
      {points.map((p, i) => (
        <div key={i} className="w-1.5 rounded-sm bg-primary/70" style={{ height: `${Math.max((p / max) * 100, 6)}%` }} />
      ))}
    </div>
  )
}

export default function News() {
  const [data, setData] = useState<NewsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.news().then(setData).catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
        Bridge offline: {error}
      </div>
    )
  }
  if (!data) return <p className="text-sm text-muted-foreground">Fetching news…</p>

  return (
    <div>
      <header className="mb-6">
        <h2 className="flex items-center gap-2 font-mono text-2xl font-bold tracking-widest text-primary">
          <Globe className="size-6" /> DAILY NEWS
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">Company news + open-source activity signal (updates every 5 min).</p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        {Object.entries(data).map(([sym, d]) => (
          <section key={sym} className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-mono text-lg font-bold">{sym}</h3>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <GitBranch className="size-3.5" /> GitHub events
                <Sparkline points={d.gh_trend.map((t) => t.raw)} />
              </div>
            </div>
            {d.news.length ? (
              <ul className="space-y-3">
                {d.news.map((n, i) => (
                  <li key={i} className="border-b border-border/40 pb-2 last:border-0">
                    <a href={n.link} target="_blank" rel="noreferrer"
                      className="group flex items-start justify-between gap-2 text-sm hover:text-primary">
                      <span>{n.title}</span>
                      <ExternalLink className="mt-0.5 size-3.5 shrink-0 opacity-40 group-hover:opacity-100" />
                    </a>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {n.publisher}{n.publisher && n.when ? " · " : ""}{n.when}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No recent headlines.</p>
            )}
          </section>
        ))}
      </div>
    </div>
  )
}
