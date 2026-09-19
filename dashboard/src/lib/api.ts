import type {
  ActionResponse, AgentResponse, ChartResponse, ChatEntry, Compliance,
  ConnectionsResponse, CycleStatus, JournalResponse, LlmHealth, ManualOrderResponse,
  ModelsResponse, Mt5Status, NewsResponse, PlanResponse, PnlResponse,
  PositionsResponse, StatusResponse, TradesResponse,
} from "./types"

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = r.statusText
    try {
      const j = await r.json()
      detail = j.error ?? detail
    } catch {
      /* not json */
    }
    throw new Error(detail)
  }
  return r.json() as Promise<T>
}

export const api = {
  status: () =>
    fetch("/api/status").then(handle<StatusResponse>),

  ask: (text: string) =>
    fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then(handle<ActionResponse>),

  screen: () => fetch("/api/screen", { method: "POST" }).then(handle<unknown>),

  train: () => fetch("/api/train", { method: "POST" }).then(handle<unknown>),

  evolve: () => fetch("/api/evolve", { method: "POST" }).then(handle<unknown>),

  chats: () => fetch("/api/chats").then(handle<{ chats: ChatEntry[] }>),
  clearChats: () =>
    fetch("/api/chats/clear", { method: "POST" }).then(handle<{ ok: boolean }>),
  trades: () => fetch("/api/trades").then(handle<TradesResponse>),
  agent: () => fetch("/api/agent").then(handle<AgentResponse>),
  plan: () => fetch("/api/plan").then(handle<PlanResponse>),
  news: () => fetch("/api/news").then(handle<NewsResponse>),
  connections: () => fetch("/api/connections").then(handle<ConnectionsResponse>),
  models: () => fetch("/api/models").then(handle<ModelsResponse>),
  uploadCoinModel: (filename: string, data_b64: string) =>
    fetch("/api/models/coin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, data_b64 }),
    }).then(handle<{ ok: boolean; stored: string }>),
  deleteCoinModel: (name: string) =>
    fetch("/api/models/coin/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then(handle<{ ok: boolean }>),
  webhooks: () => fetch("/api/webhooks").then(handle<{ webhooks: { ts: string; source: string; payload: unknown }[] }>),
  llm: () => fetch("/api/llm").then(handle<LlmHealth>),
  pnl: (month?: string, day?: string) => {
    const q = new URLSearchParams()
    if (month) q.set("month", month)
    if (day) q.set("day", day)
    const s = q.toString()
    return fetch(`/api/pnl${s ? `?${s}` : ""}`).then(handle<PnlResponse>)
  },
  cycle: () => fetch("/api/cycle").then(handle<CycleStatus>),
  runCycle: () => fetch("/api/cycle/run", { method: "POST" }).then(handle<Record<string, unknown>>),
  learnerRun: () =>
    fetch("/api/learner/run", { method: "POST" }).then(handle<{ ok: boolean; new_lessons: number }>),
  mt5: () => fetch("/api/mt5").then(handle<Mt5Status>),
  positions: () => fetch("/api/positions").then(handle<PositionsResponse>),
  manualOrder: (side: "buy" | "sell", symbol: string) =>
    fetch("/api/manual/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ side, symbol }),
    }).then(handle<ManualOrderResponse>),
  chart: (symbol: string, tf: string) => {
    const q = new URLSearchParams({ symbol, tf })
    return fetch(`/api/chart?${q}`).then(handle<ChartResponse>)
  },
  journal: (month?: string) =>
    fetch(`/api/journal${month ? `?month=${month}` : ""}`).then(handle<JournalResponse>),
  saveMt5Creds: (login: string, password: string, server: string, test: boolean) =>
    fetch("/api/mt5/creds", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login, password, server, test }),
    }).then(handle<{ ok: boolean; connected?: boolean; error?: string; account?: Mt5Status["account"] }>),
}

export type { Compliance, StatusResponse }
