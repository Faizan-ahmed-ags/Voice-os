import { useEffect, useMemo, useRef, useState } from "react"
import { LineChart, RefreshCw } from "lucide-react"

import { api } from "@/lib/api"
import type { ChartMarker, ChartResponse } from "@/lib/types"
import { useTheme } from "@/lib/useTheme"
import { cn } from "@/lib/utils"
import { LiquidButton } from "@/components/ui/liquid-glass-button"

const SYMBOLS = ["MSFT", "NVDA"]
const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1D"] as const
type Tf = (typeof TIMEFRAMES)[number]

const TF_SECONDS: Record<Tf, number> = {
  "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1D": 86400,
}

function MarkerTooltip({ m }: { m: ChartMarker }) {
  return (
    <div className="max-w-xs rounded-md border border-border bg-popover p-2 text-[11px] leading-snug shadow-lg">
      <div className="font-semibold">
        <span className={m.side === "buy" ? "text-emerald-500" : "text-red-500"}>
          {m.kind === "entry" ? m.side.toUpperCase() : "EXIT"}
        </span>{" "}
        {m.qty} {m.symbol ?? ""} @ ${m.price}
      </div>
      <div className="text-muted-foreground">
        {m.strategy} · {new Date((m.ts ?? m.t) * 1000).toLocaleString()}
      </div>
      {m.pnl != null && (
        <div className={m.pnl >= 0 ? "text-emerald-500" : "text-red-500"}>
          P&L ${m.pnl}
        </div>
      )}
      {m.reason && <div className="mt-1 text-muted-foreground">{m.reason}</div>}
    </div>
  )
}

export default function ChartPage() {
  const [symbol, setSymbol] = useState("MSFT")
  const [tf, setTf] = useState<Tf>("1D")
  const [data, setData] = useState<ChartResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const { theme } = useTheme()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ m: ChartMarker; x: number; y: number } | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      setData(await api.chart(symbol, tf))
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, tf])

  const colors = useMemo(
    () =>
      theme === "dark"
        ? { bg: "#0b0e14", grid: "#1c2333", text: "#8b93a7", up: "#22c55e", down: "#ef4444", buy: "#34d399", sell: "#f87171" }
        : { bg: "#ffffff", grid: "#e5e7eb", text: "#6b7280", up: "#16a34a", down: "#dc2626", buy: "#059669", sell: "#dc2626" },
    [theme],
  )

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap || !data || data.candles.length === 0) return
    const dpr = window.devicePixelRatio || 1
    const W = wrap.clientWidth
    const H = 460
    canvas.width = W * dpr
    canvas.height = H * dpr
    canvas.style.width = `${W}px`
    canvas.style.height = `${H}px`
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    const cs = data.candles
    const padR = 58
    const padT = 14
    const padB = 26
    const step = TF_SECONDS[tf]
    const span = Math.max(cs[cs.length - 1].t - cs[0].t, step)
    let lo = Infinity
    let hi = -Infinity
    for (const c of cs) {
      lo = Math.min(lo, c.l)
      hi = Math.max(hi, c.h)
    }
    for (const m of data.markers) {
      lo = Math.min(lo, m.price)
      hi = Math.max(hi, m.price)
    }
    const pad = (hi - lo) * 0.06 || 1
    lo -= pad
    hi += pad
    const x = (t: number) => 8 + ((t - cs[0].t) / span) * (W - padR - 8)
    const y = (p: number) => padT + (1 - (p - lo) / (hi - lo)) * (H - padT - padB)

    ctx.fillStyle = colors.bg
    ctx.fillRect(0, 0, W, H)

    // horizontal grid + price axis
    ctx.strokeStyle = colors.grid
    ctx.fillStyle = colors.text
    ctx.font = "10px ui-monospace, monospace"
    ctx.lineWidth = 1
    for (let i = 0; i <= 5; i++) {
      const p = lo + ((hi - lo) * i) / 5
      const yy = Math.round(y(p)) + 0.5
      ctx.beginPath()
      ctx.moveTo(0, yy)
      ctx.lineTo(W - padR, yy)
      ctx.stroke()
      ctx.fillText(p.toFixed(2), W - padR + 6, yy + 3)
    }
    // vertical grid + time axis
    const nT = 6
    for (let i = 0; i <= nT; i++) {
      const t = cs[0].t + (span * i) / nT
      const xx = Math.round(x(t)) + 0.5
      ctx.beginPath()
      ctx.moveTo(xx, padT)
      ctx.lineTo(xx, H - padB)
      ctx.stroke()
      const d = new Date(t * 1000)
      const label =
        tf === "1D"
          ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
          : d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
      ctx.fillText(label, xx + 3, H - 8)
    }

    // candles
    const bw = Math.max(1.5, ((W - padR) / cs.length) * 0.6)
    for (const c of cs) {
      const xx = x(c.t)
      const up = c.c >= c.o
      ctx.strokeStyle = up ? colors.up : colors.down
      ctx.fillStyle = up ? colors.up : colors.down
      ctx.beginPath()
      ctx.moveTo(xx, y(c.h))
      ctx.lineTo(xx, y(c.l))
      ctx.stroke()
      const yo = y(c.o)
      const yc = y(c.c)
      const top = Math.min(yo, yc)
      const h = Math.max(Math.abs(yc - yo), 1)
      ctx.fillRect(xx - bw / 2, top, bw, h)
    }

    // trade markers
    for (const m of data.markers) {
      const xx = x(m.t)
      const yy = y(m.price)
      const isBuy = m.side === "buy"
      ctx.fillStyle = m.kind === "exit" ? (m.pnl != null && m.pnl < 0 ? colors.sell : colors.buy) : isBuy ? colors.buy : colors.sell
      ctx.beginPath()
      const r = 5
      if (m.kind === "entry") {
        if (isBuy) {
          ctx.moveTo(xx, yy - r - 3)
          ctx.lineTo(xx + r, yy + r - 3)
          ctx.lineTo(xx - r, yy + r - 3)
        } else {
          ctx.moveTo(xx, yy + r + 3)
          ctx.lineTo(xx + r, yy - r + 3)
          ctx.lineTo(xx - r, yy - r + 3)
        }
      } else {
        ctx.arc(xx, yy, r, 0, Math.PI * 2)
      }
      ctx.closePath()
      ctx.fill()
      ctx.strokeStyle = colors.bg
      ctx.lineWidth = 1
      ctx.stroke()
    }
  }, [data, colors, tf])

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!data || data.markers.length === 0 || !canvasRef.current || !wrapRef.current) {
      setHover(null)
      return
    }
    const rect = canvasRef.current.getBoundingClientRect()
    const cs = data.candles
    if (cs.length < 2) return setHover(null)
    const step = TF_SECONDS[tf]
    const span = Math.max(cs[cs.length - 1].t - cs[0].t, step)
    const W = rect.width - 58
    const t = cs[0].t + ((e.clientX - rect.left - 8) / W) * span
    let best: ChartMarker | null = null
    let bestD = Infinity
    for (const m of data.markers) {
      const d = Math.abs(m.t - t)
      if (d < bestD) {
        bestD = d
        best = m
      }
    }
    const tol = span / Math.max(cs.length, 1) * 3
    if (best && bestD <= tol) {
      setHover({ m: best, x: e.clientX - rect.left, y: e.clientY - rect.top })
    } else {
      setHover(null)
    }
  }

  return (
    <div>
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h2 className="flex items-center gap-2 font-mono text-2xl font-bold tracking-widest text-primary">
            <LineChart className="size-6" /> TRADE MAP
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Every trade JARVIS took, drawn on the chart — entries ▲/▼, exits ●
          </p>
        </div>
        <LiquidButton size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={cn("size-4", loading && "animate-spin")} /> Refresh
        </LiquidButton>
      </header>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {SYMBOLS.map((s) => (
          <button
            key={s}
            onClick={() => setSymbol(s)}
            className={cn(
              "rounded-md border px-3 py-1.5 font-mono text-sm transition-colors",
              s === symbol
                ? "border-primary/50 bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:bg-accent",
            )}
          >
            {s}
          </button>
        ))}
        <span className="mx-2 h-5 w-px bg-border" />
        {TIMEFRAMES.map((t) => (
          <button
            key={t}
            onClick={() => setTf(t)}
            className={cn(
              "rounded-md border px-2.5 py-1.5 font-mono text-xs transition-colors",
              t === tf
                ? "border-primary/50 bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:bg-accent",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      <div
        ref={wrapRef}
        className="relative overflow-hidden rounded-lg border border-border bg-card/60 backdrop-blur"
      >
        {data && data.markers.length > 0 && (
          <div className="flex flex-wrap gap-3 px-4 pt-3 text-[11px] text-muted-foreground">
            <span className="text-emerald-500">▲ buy entry</span>
            <span className="text-red-500">▼ sell entry</span>
            <span className="text-emerald-500">● winning exit</span>
            <span className="text-red-500">● losing exit</span>
            <span>hover a marker for the trade's story</span>
          </div>
        )}
        <canvas
          ref={canvasRef}
          className="block w-full"
          onMouseMove={onMouseMove}
          onMouseLeave={() => setHover(null)}
        />
        {hover && (
          <div
            className="pointer-events-none absolute z-10"
            style={{ left: Math.min(hover.x + 12, (wrapRef.current?.clientWidth ?? 800) - 300), top: hover.y + 12 }}
          >
            <MarkerTooltip m={{ ...hover.m, symbol }} />
          </div>
        )}
        {(!data || data.candles.length === 0) && !loading && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
            {data?.error ?? "no chart data (terminal offline?)"}
          </div>
        )}
      </div>

      {data && data.markers.length > 0 && (
        <div className="mt-4 rounded-lg border border-border bg-card/60 p-4 backdrop-blur">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Trades on this chart ({data.markers.filter((m) => m.kind === "entry").length})
          </h3>
          <div className="space-y-1.5 font-mono text-xs">
            {data.markers
              .filter((m) => m.kind === "entry")
              .slice(0, 12)
              .map((m, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <span className={m.side === "buy" ? "text-emerald-500" : "text-red-500"}>
                    {m.side.toUpperCase()} {m.qty}
                  </span>
                  <span>@ ${m.price}</span>
                  <span className="rounded bg-primary/10 px-1.5 text-primary">{m.strategy}</span>
                  {m.pnl != null && (
                    <span className={m.pnl >= 0 ? "text-emerald-500" : "text-red-500"}>
                      ${m.pnl}
                    </span>
                  )}
                  <span className="text-muted-foreground">{m.reason}</span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
