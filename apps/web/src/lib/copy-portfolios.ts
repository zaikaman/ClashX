export type PortfolioRiskPolicy = {
  max_drawdown_pct: number;
  max_member_drawdown_pct: number;
  min_trust_score: number;
  max_active_members: number;
  auto_pause_on_source_stale: boolean;
  kill_switch_on_breach: boolean;
};

export type PortfolioBasketMember = {
  id: string;
  source_runtime_id: string;
  source_bot_definition_id: string;
  source_bot_name: string;
  target_weight_pct: number;
  target_notional_usd: number;
  max_scale_bps: number;
  target_scale_bps: number;
  latest_scale_bps: number;
  status: string;
  relationship_id?: string | null;
  relationship_status?: string | null;
  trust_score: number;
  risk_grade: string;
  drift_status: string;
  member_live_pnl_pct: number;
  member_drawdown_pct: number;
  scale_drift_pct: number;
  last_rebalanced_at?: string | null;
};

export type PortfolioHealth = {
  health: string;
  total_target_notional_usd: number;
  current_total_notional_usd: number;
  aggregate_live_pnl_usd: number;
  aggregate_drawdown_pct: number;
  risk_budget_used_pct: number;
  should_kill_switch: boolean;
  needs_rebalance: boolean;
  alert_count: number;
  alerts: string[];
};

export type PortfolioRebalanceEvent = {
  id: string;
  trigger: string;
  status: string;
  summary_json: Record<string, unknown>;
  created_at: string;
};

export type PortfolioBasket = {
  id: string;
  owner_user_id: string;
  wallet_address: string;
  name: string;
  description: string;
  status: string;
  rebalance_mode: string;
  rebalance_interval_minutes: number;
  drift_threshold_pct: number;
  target_notional_usd: number;
  current_notional_usd: number;
  kill_switch_reason?: string | null;
  last_rebalanced_at?: string | null;
  created_at: string;
  updated_at: string;
  risk_policy: PortfolioRiskPolicy;
  members: PortfolioBasketMember[];
  health: PortfolioHealth;
  rebalance_history: PortfolioRebalanceEvent[];
};

export type PortfolioDraftMember = {
  source_runtime_id: string;
  source_bot_name: string;
  target_weight_pct: number;
  max_scale_bps: number;
};

export type PortfolioDraft = {
  name: string;
  description: string;
  rebalance_mode: string;
  rebalance_interval_minutes: number;
  drift_threshold_pct: number;
  target_notional_usd: number;
  activate_on_create: boolean;
  risk_policy: PortfolioRiskPolicy;
  members: PortfolioDraftMember[];
};

export const defaultPortfolioRiskPolicy: PortfolioRiskPolicy = {
  max_drawdown_pct: 18,
  max_member_drawdown_pct: 22,
  min_trust_score: 55,
  max_active_members: 5,
  auto_pause_on_source_stale: true,
  kill_switch_on_breach: true,
};

export function createEmptyPortfolioDraft(): PortfolioDraft {
  return {
    name: "",
    description: "",
    rebalance_mode: "drift",
    rebalance_interval_minutes: 60,
    drift_threshold_pct: 6,
    target_notional_usd: 1_000,
    activate_on_create: true,
    risk_policy: { ...defaultPortfolioRiskPolicy },
    members: [],
  };
}

export function draftFromPortfolio(portfolio: PortfolioBasket): PortfolioDraft {
  return {
    name: portfolio.name,
    description: portfolio.description,
    rebalance_mode: portfolio.rebalance_mode,
    rebalance_interval_minutes: portfolio.rebalance_interval_minutes,
    drift_threshold_pct: portfolio.drift_threshold_pct,
    target_notional_usd: portfolio.target_notional_usd,
    activate_on_create: portfolio.status === "active",
    risk_policy: { ...portfolio.risk_policy },
    members: portfolio.members.map((member) => ({
      source_runtime_id: member.source_runtime_id,
      source_bot_name: member.source_bot_name,
      target_weight_pct: member.target_weight_pct,
      max_scale_bps: member.max_scale_bps,
    })),
  };
}
