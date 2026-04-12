export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type CopyTradingSummary = {
  active_follows: number;
  open_positions: number;
  copied_open_notional_usd: number;
  copied_unrealized_pnl_usd: number;
  copied_realized_pnl_usd_24h: number;
  copied_realized_pnl_usd_7d: number;
  readiness_status: string;
};

export type CopyTradingReadiness = {
  can_copy: boolean;
  authorization_status: string;
  blockers: string[];
};

export type CopyTradingAlert = {
  kind: string;
  title: string;
  detail: string;
  severity: string;
};

export type CopyTradingPosition = {
  relationship_id: string;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  mark_price: number;
  notional_usd: number;
  unrealized_pnl_usd: number;
  opened_at?: string | null;
  last_synced_at?: string | null;
};

export type CopyTradingFollow = {
  id: string;
  source_runtime_id: string;
  source_bot_definition_id: string;
  source_bot_name: string;
  source_rank?: number | null;
  source_drawdown_pct: number;
  source_trust_score: number;
  source_risk_grade?: string | null;
  source_health?: string | null;
  source_drift_status?: string | null;
  creator_display_name?: string | null;
  scale_bps: number;
  status: string;
  confirmed_at: string;
  updated_at: string;
  copied_open_notional_usd: number;
  copied_unrealized_pnl_usd: number;
  copied_position_count: number;
  positions: CopyTradingPosition[];
  last_execution_at?: string | null;
  last_execution_status?: string | null;
  last_execution_symbol?: string | null;
  max_notional_usd?: number | null;
};

export type CopyTradingActivity = {
  id?: string | null;
  relationship_id?: string | null;
  source_runtime_id?: string | null;
  source_event_id?: string | null;
  symbol?: string | null;
  side?: string | null;
  action_type?: string | null;
  copied_quantity: number;
  reference_price: number;
  notional_estimate_usd: number;
  status?: string | null;
  error_reason?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type CopyTradingDiscoverRow = {
  runtime_id?: string | null;
  bot_definition_id?: string | null;
  bot_name?: string | null;
  strategy_type?: string | null;
  rank?: number | null;
  drawdown: number;
  trust_score: number;
  creator_display_name?: string | null;
  creator_id?: string | null;
};

export type CopyTradingBasketSummary = {
  id?: string | null;
  name?: string | null;
  status?: string | null;
  member_count: number;
  target_notional_usd: number;
  current_notional_usd: number;
  health?: string | null;
  alert_count: number;
  aggregate_live_pnl_usd: number;
  aggregate_drawdown_pct: number;
  last_rebalanced_at?: string | null;
};

export type CopyTradingDashboard = {
  summary: CopyTradingSummary;
  readiness: CopyTradingReadiness;
  alerts: CopyTradingAlert[];
  follows: CopyTradingFollow[];
  positions: CopyTradingPosition[];
  activity: CopyTradingActivity[];
  discover: CopyTradingDiscoverRow[];
  baskets_summary: CopyTradingBasketSummary[];
};
