import { useCallback, useEffect, useRef, useState } from "react"
import { Cpu, Trash2, Upload } from "lucide-react"

import { api } from "@/lib/api"
import type { ModelsResponse } from "@/lib/types"
import { cn } from "@/lib/utils"

const ARCHITECTURE = [
  ["Halal gate", "Every symbol must pass a whitelist screen AND AAOIFI-style ratios (debt ≤30%, cash+interest ≤30%, receivables ≤33% of market cap)."],
  ["Data feed", "5 years of daily candles via yfinance + a GitHub activity signal (commits/releases on related repos), z-scored."],
  ["Features", "16 engineered features: momentum (1/5/20d), RSI, MACD, Donchian position, volatility, volume z-score, GitHub z-score, moving-average structure."],
  ["Models", "Gradient-boosted classifier per symbol with purge-embargoed walk-forward CV. AUC < 0.53 → 'candidate': never allowed to place orders."],
  ["Strategy", "Model probability > threshold → buy at next open, with take-profit / stop-loss and position-size limits; costs modeled at 2bps."],
  ["Agent", "Weekly evolution: a Groq LLM proposes guardrail-bounded parameter changes, each is backtested out-of-sample, adopted only if it beats the champion without worsening drawdown >3pp."],
  ["Brokers", "Built-in SIM broker (zero keys) or Alpaca paper with keys. Real-money code does not exist in this repo."],
  ["Your coin model", "Drop your own model into the slot below — it runs as an advisory signal alongside the built-in models."],
]

export default function Brain() {
  const [data, setData] = useState<ModelsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(() => {
    api.models().then(setData).catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])
  useEffect(load, [load])

  const upload = useCallback(async (file: File) => {
    setUploading(true)
    setUploadMsg(null)
    try {
      const buf = await file.arrayBuffer()
      let binary = ""
      const bytes = new Uint8Array(buf)
      for (let i = 0; i < bytes.length; i += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
      }
      const res = await api.uploadCoinModel(file.name, btoa(binary))
      setUploadMsg(`Stored as ${res.stored}. It now runs as an advisory signal.`)
      load()
    } catch (e) {
      setUploadMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setUploading(false)
    }
  }, [load])

  return (
    <div>
      <header className="mb-6">
        <h2 className="flex items-center gap-2 font-mono text-2xl font-bold tracking-widest text-primary">
          <Cpu className="size-6" /> BRAIN
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">What JARVIS is, and what it currently knows.</p>
      </header>

      {error && (
        <div className="mb-6 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Bridge offline: {error}
        </div>
      )}

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">Architecture</h3>
          <ol className="space-y-3">
            {ARCHITECTURE.map(([t, d]) => (
              <li key={t}>
                <p className="text-sm font-semibold">{t}</p>
                <p className="text-xs leading-relaxed text-muted-foreground">{d}</p>
              </li>
            ))}
          </ol>
        </div>

        <div className="flex flex-col gap-6">
          <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
            <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
              Built-in models (registry)
            </h3>
            <table className="w-full font-mono text-xs">
              <thead><tr className="text-left text-muted-foreground">
                <th className="pb-2">symbol</th><th className="pb-2">status</th><th className="pb-2">AUC</th><th className="pb-2">trained to</th>
              </tr></thead>
              <tbody>
                {data && Object.entries(data.builtin).map(([sym, m]) => (
                  <tr key={sym} className="border-t border-border/50">
                    <td className="py-1.5 font-semibold">{sym}</td>
                    <td className={cn(m.status === "champion" ? "text-[var(--color-success)]" : "text-[var(--color-warning)]")}>{m.status}</td>
                    <td>{m.auc_mean.toFixed(3)}</td>
                    <td className="text-muted-foreground">{m.train_end}</td>
                  </tr>
                ))}
                {(!data || !Object.keys(data.builtin).length) && (
                  <tr><td colSpan={4} className="py-2 text-muted-foreground">No models trained yet — press "Train models" on Home.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="rounded-lg border border-border bg-card/60 p-5 backdrop-blur">
            <h3 className="mb-1 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
              Your coin model (slot)
            </h3>
            <p className="mb-3 text-xs text-muted-foreground">{data?.advisory_note ?? "advisory only — never places orders"}</p>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault(); setDragOver(false)
                const f = e.dataTransfer.files?.[0]
                if (f) upload(f)
              }}
              onClick={() => fileRef.current?.click()}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-center transition-colors",
                dragOver ? "border-primary bg-primary/10" : "border-border hover:border-primary/50",
              )}
            >
              <Upload className="size-6 text-muted-foreground" />
              <p className="text-sm">{uploading ? "Uploading…" : "Drop your model file here, or click to browse"}</p>
              <p className="font-mono text-[10px] text-muted-foreground">
                .joblib · .pkl · .onnx (predict / predict_proba) → data/custom_models/
              </p>
              <input
                ref={fileRef} type="file" className="hidden" accept=".joblib,.pkl,.pickle,.onnx"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f) }}
              />
            </div>
            {uploadMsg && <p className="mt-2 text-xs text-primary">{uploadMsg}</p>}
            <ul className="mt-3 space-y-2">
              {data && Object.values(data.models).map((m) => (
                <li key={m.name} className="flex items-center justify-between rounded-md border border-border/60 p-2 font-mono text-xs">
                  <div>
                    <p className="font-semibold">{m.file}</p>
                    <p className={cn("text-[10px]", m.error ? "text-destructive" : "text-muted-foreground")}>
                      {m.error ?? `${m.format} · loaded ${m.loaded_at} · features: ${m.feature_match}`}
                    </p>
                  </div>
                  <button
                    onClick={async () => { await api.deleteCoinModel(m.name); load() }}
                    className="rounded-md border border-border p-1.5 text-muted-foreground hover:text-destructive"
                    aria-label={`Remove ${m.name}`}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              ))}
              {data && !Object.keys(data.models).length && (
                <li className="text-xs text-muted-foreground">Slot empty — nothing uploaded yet.</li>
              )}
            </ul>
            <p className="mt-3 text-[10px] leading-relaxed text-muted-foreground">
              To trust custom signals for candidate pre-ranking, set <code>"custom_model_trusted": true</code> in config.json.
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}
