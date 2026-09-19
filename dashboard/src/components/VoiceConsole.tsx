import { useCallback, useEffect, useState } from "react"
import { Mic, MicOff } from "lucide-react"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import { LiquidButton } from "@/components/ui/liquid-glass-button"

type Kind = "you" | "jarvis" | "system"
export type LogEntry = { at: string; text: string; kind: Kind }

const LOG_KEY = "jarvis_session_log"

export function loadSessionLog(): LogEntry[] {
  try {
    return JSON.parse(localStorage.getItem(LOG_KEY) ?? "[]") as LogEntry[]
  } catch {
    return []
  }
}

export function appendSessionLog(e: LogEntry) {
  try {
    const log = loadSessionLog()
    log.push(e)
    localStorage.setItem(LOG_KEY, JSON.stringify(log.slice(-300)))
  } catch {
    /* storage full/unavailable */
  }
}

export function useSessionLog() {
  const [log, setLog] = useState<LogEntry[]>(() =>
    loadSessionLog().length
      ? loadSessionLog()
      : [{ at: new Date().toLocaleTimeString(), text: "J.A.R.V.I.S. online. Paper mode. All systems nominal.", kind: "jarvis" }],
  )
  const add = useCallback((e: LogEntry) => {
    appendSessionLog(e)
    setLog((l) => [...l.slice(-300), e])
  }, [])
  const clear = useCallback(() => {
    localStorage.removeItem(LOG_KEY)
    setLog([{ at: new Date().toLocaleTimeString(), text: "Log cleared.", kind: "system" }])
  }, [])
  return { log, add, clear }
}

export default function VoiceConsole({ variant = "panel" }: { variant?: "panel" | "floating" }) {
  const [listening, setListening] = useState(false)
  const [supported, setSupported] = useState(true)
  const [busy, setBusy] = useState(false)
  const [recRef] = useState<{ current: any }>({ current: null })
  const { add } = useSessionLog()

  useEffect(() => {
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition
    setSupported(Boolean(SR))
  }, [])

  const ask = useCallback(
    async (command: string) => {
      setBusy(true)
      try {
        const res = await api.ask(command)
        add({ at: new Date().toLocaleTimeString(), text: res.reply, kind: "jarvis" })
        try {
          const u = new SpeechSynthesisUtterance(res.reply)
          u.rate = 1.05
          speechSynthesis.speak(u)
        } catch {
          /* no TTS */
        }
      } catch (e) {
        add({ at: new Date().toLocaleTimeString(), text: e instanceof Error ? e.message : String(e), kind: "system" })
      } finally {
        setBusy(false)
      }
    },
    [add],
  )

  const toggle = () => {
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition
    if (!SR) return
    if (listening) {
      recRef.current?.stop()
      setListening(false)
      return
    }
    const rec = new SR()
    rec.lang = "en-US"
    rec.interimResults = false
    rec.maxAlternatives = 1
    rec.onresult = (ev: any) => {
      const said = ev.results[0][0].transcript
      add({ at: new Date().toLocaleTimeString(), text: said, kind: "you" })
      void ask(said)
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recRef.current = rec
    rec.start()
    setListening(true)
  }

  if (variant === "floating") {
    return (
      <div className="fixed right-5 bottom-5 z-50 flex flex-col items-center gap-2">
        {busy && (
          <span className="rounded-full border border-border bg-card/90 px-3 py-1 text-xs text-muted-foreground backdrop-blur">
            thinking…
          </span>
        )}
        <LiquidButton
          onClick={toggle}
          disabled={!supported || busy}
          className={cn(
            "size-14 rounded-full px-0",
            listening && "ring-2 ring-primary ring-offset-2 ring-offset-background",
          )}
          aria-label="Toggle voice"
          title={supported ? "Tap and speak" : "Voice needs Chrome/Edge"}
        >
          {listening ? <Mic className="size-6 animate-pulse" /> : <MicOff className="size-6 opacity-70" />}
        </LiquidButton>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-3">
      <LiquidButton
        onClick={toggle}
        disabled={!supported || busy}
        className={cn(
          "aspect-square rounded-full px-0",
          listening && "ring-2 ring-primary ring-offset-2 ring-offset-background",
        )}
        aria-label="Toggle voice"
      >
        {listening ? <Mic className="size-6 animate-pulse" /> : <MicOff className="size-6 opacity-60" />}
      </LiquidButton>
      <div className="text-sm text-muted-foreground">
        {supported
          ? listening
            ? "Listening…"
            : busy
              ? "J.A.R.V.I.S. is thinking…"
              : "Tap the orb and speak a command"
          : "Voice needs Chrome or Edge (Web Speech API)"}
      </div>
    </div>
  )
}
