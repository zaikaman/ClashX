export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type TrustBadge = {
  label: string;
  tone: string;
  detail: string;
};

export type TrustMetrics = {
  trust_score: number;
  uptime_pct: number;
  failure_rate_pct: number;
  health: string;
  heartbeat_age_seconds: number;
  risk_grade: string;
  risk_score: number;
  summary: string;
  badges: TrustBadge[];
};

export type DriftMetrics = {
  status: string;
  score: number;
  summary: string;
  live_pnl_pct: number | null;
  benchmark_pnl_pct: number | null;
  return_gap_pct: number | null;
  live_drawdown_pct: number;
  benchmark_drawdown_pct: number | null;
  drawdown_gap_pct: number | null;
  benchmark_run_id: string | null;
  benchmark_completed_at: string | null;
};

export type StrategyVersionSummary = {
  id: string;
  bot_definition_id: string;
  version_number: number;
  change_kind: string;
  visibility_snapshot: string;
  name_snapshot: string;
  is_public_release: boolean;
  created_at: string;
  label: string;
};

export type PublishSnapshot = {
  id: string;
  bot_definition_id: string;
  strategy_version_id: string | null;
  runtime_id: string | null;
  visibility_snapshot: string;
  publish_state: string;
  summary_json: Record<string, unknown>;
  created_at: string;
};

export type StrategyPassport = {
  market_scope: string;
  strategy_type: string;
  authoring_mode: string;
  rules_version: number;
  current_version: number;
  release_count: number;
  public_since: string | null;
  last_published_at: string | null;
  latest_backtest_at: string | null;
  latest_backtest_run_id: string | null;
  version_history: StrategyVersionSummary[];
  publish_history: PublishSnapshot[];
};

export type CreatorSummary = {
  creator_id: string;
  wallet_address: string;
  display_name: string;
  public_bot_count: number;
  active_runtime_count: number;
  mirror_count: number;
  active_mirror_count: number;
  clone_count: number;
  average_trust_score: number;
  best_rank: number | null;
  reputation_score: number;
  reputation_label: string;
  summary: string;
  tags: string[];
};

export type CreatorBotSummary = {
  runtime_id: string;
  bot_definition_id: string;
  bot_name: string;
  strategy_type: string;
  rank: number | null;
  pnl_total: number;
  drawdown: number;
  trust_score: number;
  risk_grade: string;
  drift_status: string;
  captured_at: string | null;
};

export type CreatorProfile = CreatorSummary & {
  bots: CreatorBotSummary[];
};

export type MarketplaceCopyStats = {
  mirror_count: number;
  active_mirror_count: number;
  clone_count: number;
};

export type MarketplacePublishingSummary = {
  visibility: string;
  access_mode: string;
  publish_state: string;
  hero_headline: string;
  access_note: string;
  featured_collection_title: string | null;
  featured_rank: number;
  is_featured: boolean;
  invite_count: number;
};

export type MarketplaceCreatorSummary = CreatorSummary & {
  headline: string;
  bio: string;
  slug: string;
  featured_collection_title: string;
  follower_count: number;
  featured_bot_count: number;
  marketplace_reach_score: number;
};

export type MarketplaceDiscoveryRow = Omit<LeaderboardRow, "creator"> & {
  creator: MarketplaceCreatorSummary;
  copy_stats: MarketplaceCopyStats;
  publishing: MarketplacePublishingSummary;
};

export type FeaturedShelf = {
  collection_key: string;
  title: string;
  subtitle: string;
  bots: MarketplaceDiscoveryRow[];
};

export type MarketplaceOverviewDiscoveryRow = Pick<
  MarketplaceDiscoveryRow,
  "runtime_id" | "bot_definition_id" | "bot_name" | "strategy_type" | "rank" | "pnl_total" | "trust" | "creator" | "copy_stats" | "publishing"
>;

export type MarketplaceOverviewFeaturedShelf = {
  collection_key: string;
  title: string;
  subtitle: string;
  bots: MarketplaceOverviewDiscoveryRow[];
};

export type CreatorHighlight = MarketplaceCreatorSummary & {
  spotlight_bot: {
    runtime_id: string;
    bot_definition_id: string;
    bot_name: string;
    rank: number;
    trust_score: number;
    copy_stats: MarketplaceCopyStats;
  };
};

export type MarketplaceOverview = {
  discover: MarketplaceOverviewDiscoveryRow[];
  featured: MarketplaceOverviewFeaturedShelf[];
  creators: CreatorHighlight[];
};

export type MarketplaceCreatorProfile = MarketplaceCreatorSummary & {
  social_links_json: Record<string, unknown>;
  bots: MarketplaceDiscoveryRow[];
  featured_bots: MarketplaceDiscoveryRow[];
};

export type PublishingSettings = {
  bot_definition_id: string;
  visibility: string;
  access_mode: string;
  publish_state: string;
  hero_headline: string;
  access_note: string;
  featured_collection_title: string | null;
  featured_rank: number;
  is_featured: boolean;
  invite_wallet_addresses: string[];
  invite_count: number;
  creator_profile: {
    display_name: string;
    headline: string;
    bio: string;
    slug: string;
    featured_collection_title: string;
  };
};

export type LeaderboardRow = {
  runtime_id: string;
  bot_definition_id: string;
  bot_name: string;
  strategy_type: string;
  authoring_mode: string;
  rank: number;
  pnl_total: number;
  pnl_unrealized: number;
  win_streak: number;
  drawdown: number;
  captured_at: string;
  trust: TrustMetrics;
  drift: DriftMetrics;
  passport: StrategyPassport;
  creator: CreatorSummary;
};

export type RuntimeProfile = {
  runtime_id: string;
  bot_definition_id: string;
  bot_name: string;
  description: string;
  strategy_type: string;
  authoring_mode: string;
  status: string;
  mode: string;
  risk_policy_json: Record<string, unknown>;
  rank: number | null;
  pnl_total: number;
  pnl_unrealized: number;
  win_streak: number;
  drawdown: number;
  recent_events: Array<{
    id: string;
    event_type: string;
    decision_summary: string;
    status: string;
    created_at: string;
  }>;
  trust: TrustMetrics;
  drift: DriftMetrics;
  passport: StrategyPassport;
  creator: CreatorProfile;
};

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal });
  const payload = (await response.json()) as unknown;
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : undefined;
    throw new Error(detail ?? "Request failed");
  }
  return payload as T;
}

export function fetchLeaderboard(limit = 50, signal?: AbortSignal) {
  return fetchJson<LeaderboardRow[]>(`/api/bot-copy/leaderboard?limit=${limit}`, signal);
}

export function fetchRuntimeProfile(runtimeId: string, signal?: AbortSignal) {
  return fetchJson<RuntimeProfile>(`/api/bot-copy/leaderboard/${runtimeId}`, signal);
}

export function fetchCreatorProfile(creatorId: string, signal?: AbortSignal) {
  return fetchJson<CreatorProfile>(`/api/bot-copy/creators/${creatorId}`, signal);
}

export function fetchMarketplaceDiscover(
  limit = 24,
  options?: { strategyType?: string; creatorId?: string; signal?: AbortSignal },
) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (options?.strategyType) {
    params.set("strategy_type", options.strategyType);
  }
  if (options?.creatorId) {
    params.set("creator_id", options.creatorId);
  }
  return fetchJson<MarketplaceDiscoveryRow[]>(`/api/marketplace/discover?${params.toString()}`, options?.signal);
}

export function fetchMarketplaceOverview(
  options?: {
    discoverLimit?: number;
    featuredLimit?: number;
    creatorLimit?: number;
    signal?: AbortSignal;
  },
) {
  const params = new URLSearchParams({
    discover_limit: String(options?.discoverLimit ?? 36),
    featured_limit: String(options?.featuredLimit ?? 4),
    creator_limit: String(options?.creatorLimit ?? 6),
  });
  return fetchJson<MarketplaceOverview>(`/api/marketplace/overview?${params.toString()}`, options?.signal);
}

export function fetchFeaturedShelves(limit = 4, signal?: AbortSignal) {
  return fetchJson<FeaturedShelf[]>(`/api/marketplace/featured?limit=${limit}`, signal);
}

export function fetchCreatorHighlights(limit = 6, signal?: AbortSignal) {
  return fetchJson<CreatorHighlight[]>(`/api/marketplace/creators?limit=${limit}`, signal);
}

export function fetchMarketplaceCreatorProfile(creatorId: string, signal?: AbortSignal) {
  return fetchJson<MarketplaceCreatorProfile>(`/api/marketplace/creators/${creatorId}`, signal);
}

export async function fetchPublishingSettings(
  botId: string,
  walletAddress: string,
  headers: HeadersInit,
  signal?: AbortSignal,
) {
  const response = await fetch(
    `${API_BASE_URL}/api/marketplace/publishing/${botId}?wallet_address=${encodeURIComponent(walletAddress)}`,
    {
      cache: "no-store",
      headers,
      signal,
    },
  );
  const payload = (await response.json()) as unknown;
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : undefined;
    throw new Error(detail ?? "Request failed");
  }
  return payload as PublishingSettings;
}

export async function updatePublishingSettings(
  botId: string,
  headers: HeadersInit,
  payload: {
    wallet_address: string;
    visibility: string;
    hero_headline?: string;
    access_note?: string;
    is_featured: boolean;
    featured_collection_title?: string;
    featured_rank: number;
    invite_wallet_addresses: string[];
    creator_display_name?: string;
    creator_headline?: string;
    creator_bio?: string;
  },
) {
  const response = await fetch(`${API_BASE_URL}/api/marketplace/publishing/${botId}`, {
    method: "PATCH",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...Object.fromEntries(new Headers(headers).entries()),
    },
    body: JSON.stringify(payload),
  });
  const data = (await response.json()) as unknown;
  if (!response.ok) {
    const detail =
      typeof data === "object" && data !== null && "detail" in data && typeof data.detail === "string"
        ? data.detail
        : undefined;
    throw new Error(detail ?? "Request failed");
  }
  return data as PublishingSettings;
}

export function toneToClasses(tone: string) {
  switch (tone) {
    case "green":
      return "border-[#74b97f]/35 bg-[#74b97f]/12 text-[#b7efc0]";
    case "amber":
      return "border-[#dce85d]/35 bg-[#dce85d]/12 text-[#ecf4a8]";
    case "rose":
      return "border-[#ff7a90]/35 bg-[#ff7a90]/12 text-[#ffbec8]";
    default:
      return "border-white/10 bg-white/5 text-neutral-300";
  }
}

export function driftTone(status: string) {
  if (status === "aligned") {
    return "text-[#74b97f]";
  }
  if (status === "watch") {
    return "text-[#dce85d]";
  }
  if (status === "elevated") {
    return "text-[#ff8a9b]";
  }
  return "text-neutral-400";
}
