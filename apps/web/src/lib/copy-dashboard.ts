export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const COPY_DASHBOARD_CACHE_TTL_MS = 60_000;
const COPY_DASHBOARD_CACHE_PREFIX = "clashx.copy-dashboard:";

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

type CopyTradingDashboardCacheEntry = {
  cachedAt: number;
  dashboard: CopyTradingDashboard;
};

const copyDashboardCache = new Map<string, CopyTradingDashboardCacheEntry>();

function normalizeWalletAddress(walletAddress: string) {
  return walletAddress.trim().toLowerCase();
}

function cacheKey(walletAddress: string) {
  return `${COPY_DASHBOARD_CACHE_PREFIX}${normalizeWalletAddress(walletAddress)}`;
}

function isFreshCacheEntry(entry: CopyTradingDashboardCacheEntry | null) {
  return Boolean(entry && Date.now() - entry.cachedAt < COPY_DASHBOARD_CACHE_TTL_MS);
}

function isDashboardCacheEntry(value: unknown): value is CopyTradingDashboardCacheEntry {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<CopyTradingDashboardCacheEntry>;
  return typeof candidate.cachedAt === "number" && typeof candidate.dashboard === "object" && candidate.dashboard !== null;
}

export function readCachedCopyTradingDashboard(walletAddress: string) {
  const normalizedWalletAddress = normalizeWalletAddress(walletAddress);
  if (!normalizedWalletAddress) {
    return null;
  }

  const memoryEntry = copyDashboardCache.get(normalizedWalletAddress) ?? null;
  if (isFreshCacheEntry(memoryEntry)) {
    return memoryEntry?.dashboard ?? null;
  }

  if (typeof window === "undefined") {
    return null;
  }

  try {
    const rawValue = window.sessionStorage.getItem(cacheKey(normalizedWalletAddress));
    if (!rawValue) {
      return null;
    }

    const parsed = JSON.parse(rawValue) as unknown;
    if (!isDashboardCacheEntry(parsed)) {
      window.sessionStorage.removeItem(cacheKey(normalizedWalletAddress));
      copyDashboardCache.delete(normalizedWalletAddress);
      return null;
    }

    if (!isFreshCacheEntry(parsed)) {
      window.sessionStorage.removeItem(cacheKey(normalizedWalletAddress));
      copyDashboardCache.delete(normalizedWalletAddress);
      return null;
    }

    copyDashboardCache.set(normalizedWalletAddress, parsed);
    return parsed.dashboard;
  } catch {
    copyDashboardCache.delete(normalizedWalletAddress);
    return null;
  }
}

export function writeCachedCopyTradingDashboard(
  walletAddress: string,
  dashboard: CopyTradingDashboard,
) {
  const normalizedWalletAddress = normalizeWalletAddress(walletAddress);
  if (!normalizedWalletAddress) {
    return;
  }

  const nextEntry: CopyTradingDashboardCacheEntry = {
    cachedAt: Date.now(),
    dashboard,
  };

  copyDashboardCache.set(normalizedWalletAddress, nextEntry);

  if (typeof window === "undefined") {
    return;
  }

  try {
    window.sessionStorage.setItem(cacheKey(normalizedWalletAddress), JSON.stringify(nextEntry));
  } catch {
    // Ignore session storage quota and privacy mode failures.
  }
}
