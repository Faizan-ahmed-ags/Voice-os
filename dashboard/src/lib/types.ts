export interface Compliance {
  symbol: string
  compliant: boolean
  reason: string
  ratios?: { debt: number; cash_int: number; receivables: number } | null
  checked_at?: string
}

export interface Position {
  symbol: string
  qty: number
  basis: number
}

export interface StatusResponse {
  mode: string
  paper: boolean
  equity: number
  positions: Position[]
  models: Record<
    string,
    { status: string; auc_mean: number; acc_mean: number; train_end: string }
  >
  last_decisions: {
    ts: string
    symbol: string
    action: string
    qty: number
    price: number
    mode: string
    reason: string
  }[]
  last_evolution: { at: string; results: Record<string, unknown> } | null
}

export interface ActionResponse {
  reply: string
  source: string
}

// ---------------- v2

export interface ChatEntry {
  ts: string
  kind: "you" | "jarvis" | "system"
  text: string
  page: string
}

export interface TradeRecord {
  ts: string
  symbol: string
  action: string
  qty: number
  price: number
  mode: string
  reason: string
}

export interface TradesResponse {
  decisions: TradeRecord[]
  equity: number
  mode: string
  positions: Record<string, { qty: number; basis?: number }>
}

export interface AgentResponse {
  last_evolution: {
    at: string
    results: Record<
      string,
      { status: string; why?: string; params?: Record<string, number>;
        challenger_return?: number; incumbent_return?: number }
    >
  } | null
  activity: string[]
  learning?: LearningStats
  trades?: TradeRow[]
}

export interface LearningStats {
  closed: number
  open: number
  wins: number
  losses: number
  hit_rate_pct: number | null
  cumulative_pnl: number
  by_exit_kind: Record<string, { n: number; pnl: number }>
  lessons: { ts: string; scope: string; lesson: string; evidence: string;
    weight: number }[]
}

export interface TradeRow {
  id: number
  opened_at: string
  symbol: string
  side: string
  qty: number
  entry_price: number
  ticket: number | null
  mode: string
  prob: number | null
  params: Record<string, number>
  reason: string
  sl_pct: number | null
  tp_pct: number | null
  closed_at: string | null
  exit_price: number | null
  pnl: number | null
  exit_kind: string | null
  reflected: number
}

export interface PlanResponse {
  universe: string[]
  symbols: {
    symbol: string
    halal: Compliance | null
    model: { status: string; auc: number } | null
    params: Record<string, number> | "defaults"
    backtest: { return_pct?: number; buy_hold_pct?: number; sharpe?: number;
      max_drawdown_pct?: number; sortino?: number; oos_days?: number;
      error?: string } | null
  }[]
  guardrails: Record<string, { min: number; max: number }>
  schedule: { daily_run_time: string; evolve: string; note: string }
  risk: { max_daily_loss_pct: number; starting_cash: number; paper_trading: boolean }
}

export interface NewsItem { title: string; when: string; link: string; publisher: string }
export interface NewsResponse {
  [symbol: string]: {
    news: NewsItem[]
    gh_trend: { ts: string; raw: number; z: number | null }[]
  }
}

export interface LlmHealth {
  enabled: boolean
  up: boolean
  base_url: string
  model_file: string | null
  groq_configured: boolean
  active: string
  webhook_secret_set: boolean
  obsidian_vault: string
  note: string
}

export interface ConnectionsResponse {
  alpaca: { configured: boolean; paper: boolean | null; how: string }
  groq: { configured: boolean; how: string }
  mt5: { installed: boolean; paths_found: string[]; python_package: boolean;
    bridge_wired: boolean; note: string; guide: string[] }
  tradingview: { configured: boolean; note: string }
  webhook: { url: string; method: string; note: string }
  active_broker: string
}

export interface CoinModelInfo {
  name: string
  file: string
  format: string
  error: string | null
  feature_match: string
  loaded_at: string
}

export interface ModelsResponse {
  dir: string
  trusted: boolean
  advisory_note: string
  models: Record<string, CoinModelInfo>
  builtin: Record<string, { status: string; auc_mean: number; train_end: string }>
}

// ---------------- v3: calendar, mt5, daily cycle

export interface PnlDay {
  date: string
  start_equity: number
  end_equity: number
  realized: number
  unrealized: number
  trades: number
  wins: number
  losses: number
  mode: string
}

export interface PnlResponse {
  month: string
  days: PnlDay[]
  total: number
  green_days: number
  red_days: number
  day: (PnlDay & { trades_detail: TradeRecord[] }) | null
  today_state: { date: string; start_equity: number; equity: number; pnl: number;
    pnl_pct: number; blocked: boolean; max_daily_loss_pct: number;
    risk_per_trade_pct: number }
}

export interface Mt5Status {
  package: boolean
  connected: boolean
  account: { login: number; name: string; server: string; currency: string;
    leverage: number; balance: number; equity: number; trade_mode: string;
    company: string } | null
  error: string | null
  mode_allowed: boolean
  creds_set: boolean
  broker_symbols_sample: string[]
}

export interface CycleStatus {
  in_progress: boolean
  schedule: string
  broker: string
  mt5: Mt5Status
  risk: { risk_per_trade_pct: number; max_daily_loss_pct: number }
  last_cycle: { ts: string; trigger: string; status: string; symbols_scanned: number;
    orders_placed: number; predictions: Record<string, unknown>; notes: string } | null
}

// ---------------- v6: positions, manual trading, chart, journal

export interface LivePosition {
  symbol: string
  qty: number
  strategy: string
  reason: string
  opened_at: string | null
  entry: number | null
}

export interface PositionsResponse {
  positions: LivePosition[]
  broker: string | null
}

export interface ManualOrderResponse {
  ok: boolean
  error?: string
  filled?: number
  filled_qty?: number
  price?: number
  ticket?: number | null
  net_closed?: { ticket: number; volume: number; price: number }[]
}

export interface ChartMarker {
  t: number
  ts?: number
  price: number
  kind: "entry" | "exit"
  side: string
  qty: number
  strategy: string
  pnl: number | null
  reason: string
  symbol?: string
}

export interface ChartResponse {
  symbol: string
  tf: string
  candles: { t: number; o: number; h: number; l: number; c: number }[]
  markers: ChartMarker[]
  error?: string
}

export interface JournalTradeRow {
  time: string
  symbol: string
  side: string
  qty: number
  entry: number
  exit: number | null
  pnl: number | null
  strategy: string
  exit_kind: string | null
  reason: string
}

export interface JournalDay {
  date: string
  start_equity: number
  end_equity: number
  realized: number
  unrealized: number
  trades: number
  wins: number
  losses: number
  mode: string
  verdict: "great" | "down" | "flat" | "quiet"
  trade_rows: JournalTradeRow[]
  cycle: { trigger: string; orders: number } | null
  lessons: string[]
}

export interface JournalResponse {
  month: string
  days: JournalDay[]
  total: number
  green_days: number
  red_days: number
}
