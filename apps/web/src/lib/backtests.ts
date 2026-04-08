export type BacktestPriceCandle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type BacktestAssumptionConfig = {
  fee_bps: number;
  slippage_bps: number;
  funding_bps_per_interval: number;
};

export type BacktestTrade = {
  trade_id: string;
  symbol: string;
  side: "long" | "short";
  status: "open" | "closed";
  entry_time: string;
  exit_time: string | null;
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  notional_usd: number;
  leverage: number;
  gross_pnl_usd: number;
  fees_paid_usd: number;
  funding_pnl_usd: number;
  pnl_usd: number | null;
  pnl_pct: number | null;
  duration_seconds: number | null;
  close_reason: string | null;
  unrealized_pnl?: number;
  unrealized_pnl_pct?: number;
};

export type BacktestTriggerEvent = {
  timestamp: number;
  symbol: string;
  kind: string;
  title: string;
  detail: string;
};

export type BacktestResultSummary = {
  primary_symbol: string | null;
  symbols: string[];
  requested_symbols?: string[];
  skipped_symbols?: string[];
  interval: string;
  initial_capital_usd: number;
  ending_equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  gross_pnl_total: number;
  pnl_total: number;
  pnl_total_pct: number;
  max_drawdown_pct: number;
  win_rate: number;
  trade_count: number;
  winning_trades: number;
  losing_trades: number;
  avg_trade_duration_seconds: number;
  fees_paid_usd: number;
  funding_pnl_usd: number;
};

export type BacktestResult = {
  equity_curve: Array<{
    time: number;
    equity: number;
    realized_pnl: number;
    unrealized_pnl: number;
  }>;
  price_series: {
    primary_symbol: string | null;
    series_by_symbol: Record<string, BacktestPriceCandle[]>;
  };
  trades: BacktestTrade[];
  trigger_events: BacktestTriggerEvent[];
  summary: BacktestResultSummary;
  assumption_config?: BacktestAssumptionConfig;
  assumptions: string[];
  preflight_issues?: string[];
  requested_range?: {
    start_time: number;
    end_time: number;
  };
};

export type BacktestRunSummary = {
  id: string;
  bot_definition_id: string;
  bot_name_snapshot: string;
  market_scope_snapshot?: string | null;
  strategy_type_snapshot?: string | null;
  interval: string;
  start_time: number;
  end_time: number;
  initial_capital_usd: number;
  execution_model: string;
  pnl_total: number;
  pnl_total_pct: number;
  max_drawdown_pct: number;
  win_rate: number;
  trade_count: number;
  status: string;
  assumption_config_json?: BacktestAssumptionConfig;
  failure_reason?: string | null;
  created_at: string;
  completed_at: string | null;
  updated_at: string;
};

export type BacktestRunDetail = BacktestRunSummary & {
  user_id: string;
  wallet_address: string;
  rules_snapshot_json: Record<string, unknown>;
  result_json: BacktestResult;
};

export type BacktestRunRequestPayload = {
  wallet_address: string;
  bot_id: string;
  interval?: string;
  start_time: number;
  end_time: number;
  initial_capital_usd: number;
  assumptions?: BacktestAssumptionConfig;
};

export type BacktestsBootstrapPayload = {
  bots: Array<{
    id: string;
    name: string;
    description: string;
    strategy_type: string;
    market_scope: string;
    inferred_backtest_interval: string;
    updated_at: string;
  }>;
  runs: BacktestRunSummary[];
};
