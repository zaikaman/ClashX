"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

import { BotPerformancePanel } from "@/components/bots/bot-performance-panel";
import { RuntimeFailurePanel } from "@/components/bots/runtime-failure-panel";
import { RuntimeHealthCard } from "@/components/bots/runtime-health-card";
import {
  DEFAULT_RUNTIME_POLICY,
  type RuntimePolicyDraft,
  runtimePolicyDraftFromPolicy,
  runtimePolicyDraftToPayload,
} from "@/components/bots/runtime-policy";
import { useClashxAuth } from "@/lib/clashx-auth";
import type { BotPerformance } from "@/lib/bot-performance";
import type { PublishingSettings } from "@/lib/public-bots";
import type { RuntimeOverview } from "@/lib/runtime-overview";

const AdvancedSettingsPanel = dynamic(
  () => import("@/components/bots/advanced-settings-panel").then((module) => module.AdvancedSettingsPanel),
  {
    loading: () => (
      <DeferredPanelPlaceholder
        eyebrow="Advanced settings"
        title="Loading runtime policy"
        body="Risk controls and execution settings are loading in the background."
      />
    ),
  },
);

const BotPublishingPanel = dynamic(
  () => import("@/components/bots/bot-publishing-panel").then((module) => module.BotPublishingPanel),
  {
    loading: () => (
      <DeferredPanelPlaceholder
        eyebrow="Publishing"
        title="Loading publishing controls"
        body="Marketplace settings are loading in the background."
      />
    ),
  },
);

const RuntimeControls = dynamic(
  () => import("@/components/bots/runtime-controls").then((module) => module.RuntimeControls),
  {
    loading: () => (
      <DeferredPanelPlaceholder
        eyebrow="Runtime controls"
        title="Loading live controls"
        body="Deploy, pause, and stop actions are loading in the background."
      />
    ),
  },
);

const ExecutionLog = dynamic(
  () => import("@/components/bots/execution-log").then((module) => module.ExecutionLog),
  {
    loading: () => (
      <DeferredPanelPlaceholder
        eyebrow="Activity stream"
        title="Loading recent activity"
        body="Recent runtime decisions are loading on demand."
      />
    ),
  },
);

type BotDefinition = {
  id: string;
  name: string;
  description: string;
  wallet_address: string;
  visibility: string;
  authoring_mode: string;
  strategy_type: string;
  market_scope: string;
  rules_json: Record<string, unknown>;
  updated_at: string;
};

type BotExecutionEvent = {
  id: string;
  runtime_id: string;
  event_type: string;
  decision_summary: string;
  action_type?: string | null;
  symbol?: string | null;
  leverage?: number | null;
  size_usd?: number | null;
  status: string;
  error_reason?: string | null;
  outcome_summary: string;
  created_at: string;
};

type RuntimeRiskStateResponse = {
  runtime_id: string;
  risk_policy_json: Record<string, unknown>;
  runtime_state: Record<string, unknown>;
  updated_at: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const EVENTS_PAGE_SIZE = 40;
const REFRESH_INTERVAL_MS = 60000;

async function unwrapResponse<T>(response: Response, fallback: string): Promise<T> {
  const payload = (await response.json()) as unknown;
  if (!response.ok) {
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = payload.detail;
      throw new Error(typeof detail === "string" && detail.length > 0 ? detail : fallback);
    }
    throw new Error(fallback);
  }
  return payload as T;
}

function normalizeAllowedSymbol(value: unknown): string {
  return String(value ?? "").trim().toUpperCase().replace("-PERP", "");
}

function inferAllowedSymbolsFromBot(bot: BotDefinition): string {
  const selectedSymbols = Array.isArray(bot.rules_json.selected_market_symbols)
    ? bot.rules_json.selected_market_symbols
        .map((value) => normalizeAllowedSymbol(value))
        .filter(Boolean)
    : [];

  if (selectedSymbols.length > 0) {
    return Array.from(new Set(selectedSymbols)).join(",");
  }

  const explicitSymbols = new Set<string>();
  const appendSymbol = (value: unknown) => {
    const symbol = normalizeAllowedSymbol(value);
    if (!symbol || symbol === "__BOT_MARKET_UNIVERSE__") {
      return;
    }
    explicitSymbols.add(symbol);
  };

  const conditions = Array.isArray(bot.rules_json.conditions) ? bot.rules_json.conditions : [];
  for (const row of conditions) {
    if (row && typeof row === "object" && "symbol" in row) {
      appendSymbol(row.symbol);
    }
  }

  const actions = Array.isArray(bot.rules_json.actions) ? bot.rules_json.actions : [];
  for (const row of actions) {
    if (row && typeof row === "object" && "symbol" in row) {
      appendSymbol(row.symbol);
    }
  }

  const graph = typeof bot.rules_json.graph === "object" && bot.rules_json.graph !== null ? bot.rules_json.graph : null;
  const nodes = graph && Array.isArray((graph as { nodes?: unknown[] }).nodes) ? (graph as { nodes: unknown[] }).nodes : [];
  for (const node of nodes) {
    if (!node || typeof node !== "object") {
      continue;
    }
    const config = "config" in node ? node.config : null;
    if (config && typeof config === "object" && "symbol" in config) {
      appendSymbol(config.symbol);
    }
  }

  return Array.from(explicitSymbols).join(",");
}

function DeferredPanelPlaceholder({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <article className="grid gap-3 rounded-[1.8rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-5">
      <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">{eyebrow}</span>
      <h3 className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">{title}</h3>
      <p className="text-sm leading-7 text-neutral-400">{body}</p>
    </article>
  );
}

export default function BotDetailPage({ params: paramsPromise }: { params: Promise<{ botId: string }> }) {
  const params = use(paramsPromise);
  const { authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();

  const [bot, setBot] = useState<BotDefinition | null>(null);
  const [events, setEvents] = useState<BotExecutionEvent[]>([]);
  const [runtimeOverview, setRuntimeOverview] = useState<RuntimeOverview | null>(null);
  const [performance, setPerformance] = useState<BotPerformance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [primaryLoading, setPrimaryLoading] = useState(false);
  const [activityLoading, setActivityLoading] = useState(false);
  const [runtimeRefreshToken, setRuntimeRefreshToken] = useState(0);
  const [activityRefreshToken, setActivityRefreshToken] = useState(0);
  const [activeTab, setActiveTab] = useState<"overview" | "operate" | "activity">("overview");
  const [runtimePolicy, setRuntimePolicy] = useState<RuntimePolicyDraft>(DEFAULT_RUNTIME_POLICY);
  const [runtimePolicyStatus, setRuntimePolicyStatus] = useState<"idle" | "loading" | "saving">("idle");
  const [runtimePolicyError, setRuntimePolicyError] = useState<string | null>(null);
  const [runtimePolicyRuntimeId, setRuntimePolicyRuntimeId] = useState<string | null>(null);
  const [pageVisible, setPageVisible] = useState(
    typeof document === "undefined" ? true : document.visibilityState === "visible",
  );

  const sessionActive = authenticated && Boolean(walletAddress);
  const activeRuntimeId = runtimeOverview?.health.runtime_id ?? null;

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }

    const syncVisibility = () => {
      setPageVisible(document.visibilityState === "visible");
    };

    syncVisibility();
    document.addEventListener("visibilitychange", syncVisibility);
    window.addEventListener("focus", syncVisibility);
    return () => {
      document.removeEventListener("visibilitychange", syncVisibility);
      window.removeEventListener("focus", syncVisibility);
    };
  }, []);

  useEffect(() => {
    if (!sessionActive || !walletAddress) {
      setBot(null);
      setEvents([]);
      setRuntimeOverview(null);
      setPerformance(null);
      setError(null);
      setEventsError(null);
      setPrimaryLoading(false);
      setActivityLoading(false);
      setRuntimeRefreshToken(0);
      setActivityRefreshToken(0);
      setRuntimePolicy(DEFAULT_RUNTIME_POLICY);
      setRuntimePolicyStatus("idle");
      setRuntimePolicyError(null);
      setRuntimePolicyRuntimeId(null);
      return;
    }

    const resolvedWallet = walletAddress;
    const controller = new AbortController();

    async function loadPrimary() {
      setPrimaryLoading(true);
      setActivityLoading(false);
      setBot(null);
      setEvents([]);
      setRuntimeOverview(null);
      setPerformance(null);
      setError(null);
      setEventsError(null);
      setRuntimeRefreshToken(0);
      setActivityRefreshToken(0);
      setRuntimePolicy(DEFAULT_RUNTIME_POLICY);
      setRuntimePolicyStatus("idle");
      setRuntimePolicyError(null);
      setRuntimePolicyRuntimeId(null);

      try {
        const headers = await getAuthHeaders();
        const walletQuery = encodeURIComponent(resolvedWallet);
        const [botResponse, overviewResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/bots/${params.botId}?wallet_address=${walletQuery}`, {
            cache: "no-store",
            headers,
            signal: controller.signal,
          }),
          fetch(
            `${API_BASE_URL}/api/bots/${params.botId}/runtime-overview?wallet_address=${walletQuery}&include_performance=true&performance_mode=full`,
            {
              headers,
              signal: controller.signal,
            },
          ),
        ]);

        const [nextBot, nextOverview] = await Promise.all([
          unwrapResponse<BotDefinition>(botResponse, "Could not load bot"),
          unwrapResponse<RuntimeOverview>(overviewResponse, "Could not load runtime overview"),
        ]);

        if (controller.signal.aborted) {
          return;
        }

        setBot(nextBot);
        setRuntimeOverview(nextOverview);
        setPerformance(nextOverview.performance ?? null);
        if (!nextOverview.health.runtime_id) {
          setRuntimePolicy({
            ...DEFAULT_RUNTIME_POLICY,
            allowedSymbols: inferAllowedSymbolsFromBot(nextBot),
          });
        }
        setError(null);
      } catch (loadError) {
        if (controller.signal.aborted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Could not load bot runtime");
      } finally {
        if (!controller.signal.aborted) {
          setPrimaryLoading(false);
        }
      }
    }

    void loadPrimary();
    return () => controller.abort();
  }, [authenticated, walletAddress, params.botId, sessionActive, getAuthHeaders]);

  useEffect(() => {
    if (!sessionActive || !walletAddress || runtimeRefreshToken === 0) {
      return;
    }

    const resolvedWallet = walletAddress;
    const controller = new AbortController();

    async function refreshOverview() {
      try {
        const headers = await getAuthHeaders();
        const walletQuery = encodeURIComponent(resolvedWallet);
        const overviewResponse = await fetch(
          `${API_BASE_URL}/api/bots/${params.botId}/runtime-overview?wallet_address=${walletQuery}&include_performance=true&performance_mode=fast`,
          {
            headers,
            signal: controller.signal,
          },
        );
        const nextOverview = await unwrapResponse<RuntimeOverview>(
          overviewResponse,
          "Could not refresh runtime overview",
        );

        if (controller.signal.aborted) {
          return;
        }

        setRuntimeOverview(nextOverview);
        setPerformance(nextOverview.performance ?? null);
      } catch (loadError) {
        if (controller.signal.aborted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Could not refresh runtime overview");
      }
    }

    void refreshOverview();
    return () => controller.abort();
  }, [getAuthHeaders, params.botId, runtimeRefreshToken, sessionActive, walletAddress]);

  useEffect(() => {
    if (primaryLoading || !sessionActive || !walletAddress) {
      return;
    }

    if (activeTab === "activity" && activityRefreshToken === 0) {
      setActivityRefreshToken(1);
    }
  }, [activeTab, activityRefreshToken, primaryLoading, sessionActive, walletAddress]);

  useEffect(() => {
    if (!sessionActive || !walletAddress || activeTab !== "activity" || activityRefreshToken === 0) {
      return;
    }

    const resolvedWallet = walletAddress;
    const controller = new AbortController();

    async function loadActivity() {
      setActivityLoading(true);
      try {
        const headers = await getAuthHeaders();
        const walletQuery = encodeURIComponent(resolvedWallet);
        const response = await fetch(
          `${API_BASE_URL}/api/bots/${params.botId}/events?wallet_address=${walletQuery}&limit=${EVENTS_PAGE_SIZE}`,
          {
            headers,
            signal: controller.signal,
          },
        );
        const nextEvents = await unwrapResponse<BotExecutionEvent[]>(response, "Could not load activity stream");

        if (controller.signal.aborted) {
          return;
        }

        setEvents(nextEvents);
        setEventsError(null);
      } catch (loadError) {
        if (controller.signal.aborted) {
          return;
        }
        setEventsError(loadError instanceof Error ? loadError.message : "Could not load activity stream");
      } finally {
        if (!controller.signal.aborted) {
          setActivityLoading(false);
        }
      }
    }

    void loadActivity();
    return () => controller.abort();
  }, [activeTab, activityRefreshToken, getAuthHeaders, params.botId, sessionActive, walletAddress]);

  useEffect(() => {
    if (!sessionActive || !walletAddress || primaryLoading) {
      return;
    }

    const effectiveRefreshIntervalMs = pageVisible ? REFRESH_INTERVAL_MS : Math.max(REFRESH_INTERVAL_MS * 3, 180000);
    const interval = window.setInterval(() => {
      setRuntimeRefreshToken((value) => value + 1);
      if (activeTab === "activity") {
        setActivityRefreshToken((value) => value + 1);
      }
    }, effectiveRefreshIntervalMs);

    return () => window.clearInterval(interval);
  }, [activeTab, pageVisible, primaryLoading, sessionActive, walletAddress]);

  useEffect(() => {
    if (!sessionActive || !walletAddress || activeTab !== "operate") {
      return;
    }

    if (!activeRuntimeId) {
      setRuntimePolicyStatus("idle");
      setRuntimePolicyError(null);
      setRuntimePolicyRuntimeId(null);
      return;
    }

    if (runtimePolicyRuntimeId === activeRuntimeId) {
      return;
    }

    const controller = new AbortController();
    const resolvedWallet = walletAddress;

    async function loadRuntimePolicy() {
      setRuntimePolicyStatus("loading");
      setRuntimePolicyError(null);
      try {
        const headers = await getAuthHeaders();
        const walletQuery = encodeURIComponent(resolvedWallet);
        const response = await fetch(
          `${API_BASE_URL}/api/bots/${params.botId}/risk-state?wallet_address=${walletQuery}`,
          {
            cache: "no-store",
            headers,
            signal: controller.signal,
          },
        );
        const payload = await unwrapResponse<RuntimeRiskStateResponse>(response, "Could not load runtime policy");

        if (controller.signal.aborted) {
          return;
        }

        setRuntimePolicy(runtimePolicyDraftFromPolicy(payload.risk_policy_json));
        setRuntimePolicyRuntimeId(payload.runtime_id);
        setRuntimePolicyStatus("idle");
      } catch (loadError) {
        if (controller.signal.aborted) {
          return;
        }
        setRuntimePolicyError(loadError instanceof Error ? loadError.message : "Could not load runtime policy");
        setRuntimePolicyStatus("idle");
      }
    }

    void loadRuntimePolicy();
    return () => controller.abort();
  }, [
    activeRuntimeId,
    activeTab,
    getAuthHeaders,
    params.botId,
    runtimePolicyRuntimeId,
    sessionActive,
    walletAddress,
  ]);

  const visibleBot = sessionActive ? bot : null;
  const visibleRuntimeOverview = sessionActive ? runtimeOverview : null;
  const visibleError = sessionActive ? error : null;

  const initialPublishingSettings = useMemo<PublishingSettings | null>(() => {
    if (!visibleBot) {
      return null;
    }

    const displayName = walletAddress
      ? `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}`
      : "";
    const publishState =
      visibleBot.visibility === "public"
        ? "published"
        : visibleBot.visibility === "unlisted"
          ? "unlisted"
          : visibleBot.visibility === "invite_only"
            ? "invite_only"
            : "draft";

    return {
      bot_definition_id: visibleBot.id,
      visibility: visibleBot.visibility,
      access_mode: visibleBot.visibility,
      publish_state: publishState,
      hero_headline: "",
      access_note: "",
      invite_wallet_addresses: [],
      invite_count: 0,
      creator_profile: {
        display_name: displayName,
        headline: "",
        bio: "",
        slug: "",
      },
    };
  }, [visibleBot, walletAddress]);

  function refreshRuntimeData() {
    setRuntimeRefreshToken((value) => value + 1);
    if (activeTab === "activity") {
      setActivityRefreshToken((value) => value + 1);
    }
  }

  async function saveRuntimePolicy() {
    if (!walletAddress || !activeRuntimeId) {
      return;
    }

    setRuntimePolicyStatus("saving");
    setRuntimePolicyError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/bots/${params.botId}/risk-state`, {
        method: "PATCH",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          wallet_address: walletAddress,
          risk_policy_json: runtimePolicyDraftToPayload(runtimePolicy),
        }),
      });
      const payload = await unwrapResponse<RuntimeRiskStateResponse>(response, "Could not save runtime policy");
      setRuntimePolicy(runtimePolicyDraftFromPolicy(payload.risk_policy_json));
      setRuntimePolicyRuntimeId(payload.runtime_id);
      setRuntimePolicyStatus("idle");
      refreshRuntimeData();
    } catch (saveError) {
      setRuntimePolicyError(saveError instanceof Error ? saveError.message : "Could not save runtime policy");
      setRuntimePolicyStatus("idle");
    }
  }

  return (
    <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">
      <section className="flex flex-wrap items-end justify-between gap-4 border-b border-[rgba(255,255,255,0.08)] pb-6 md:pb-8">
        <div className="grid gap-2">
          <h1 className="font-mono text-[clamp(2rem,4vw,2.8rem)] font-bold uppercase tracking-tight text-neutral-50">
            {visibleBot?.name ?? (primaryLoading ? "Loading bot" : "Bot workspace")}
          </h1>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400">
            {visibleBot?.strategy_type
              ? `${visibleBot.strategy_type} bot workspace.`
              : "Runtime, settings, and activity in one place."}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            href={`/builder?botId=${encodeURIComponent(params.botId)}`}
            className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
          >
            Edit in builder
          </Link>
          <Link
            href={`/backtests?botId=${encodeURIComponent(params.botId)}`}
            className="rounded-full border border-[rgba(116,185,127,0.22)] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f] transition hover:border-[#74b97f] hover:bg-[#74b97f]/8"
          >
            Open backtests
          </Link>
          <Link
            href="/bots"
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
          >
            Back to my bots
          </Link>
        </div>
      </section>

      {!authenticated ? (
        <article className="flex flex-wrap items-center justify-between gap-4 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-5">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
              Sign in required
            </span>
            <p className="text-sm leading-7 text-neutral-400">
              Connect your wallet to manage runtime actions, publishing, and advanced settings.
            </p>
          </div>
          <button
            type="button"
            onClick={login}
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
          >
            Sign in to manage this bot
          </button>
        </article>
      ) : null}

      {visibleError ? (
        <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
          {visibleError}
        </article>
      ) : null}

      <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4 md:p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">
              Workspace
            </span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              Choose a desk
            </h2>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400">
              Keep monitoring, operations, and recent activity separate so the page stays easier to scan.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <TabButton
              active={activeTab === "overview"}
              label="Overview"
              onClick={() => setActiveTab("overview")}
            />
            <TabButton
              active={activeTab === "operate"}
              label="Operate"
              onClick={() => setActiveTab("operate")}
            />
            <TabButton
              active={activeTab === "activity"}
              label="Activity"
              onClick={() => setActiveTab("activity")}
            />
          </div>
        </div>

        {activeTab === "overview" ? (
          <section className="grid gap-6">
            <div className="grid gap-3">
              <SectionIntro
                eyebrow="Overview"
                title="Runtime snapshot"
                copy="A compact view of performance, health, and failure signals."
              />
              {primaryLoading && !performance ? (
                <DeferredPanelPlaceholder
                  eyebrow="Performance"
                  title="Loading live performance"
                  body="PnL and open position metrics are loading from the latest runtime snapshot."
                />
              ) : (
                <BotPerformancePanel performance={sessionActive ? performance : null} />
              )}
            </div>

            {walletAddress ? (
              <div className="grid gap-6 xl:grid-cols-2">
                <RuntimeHealthCard
                  health={visibleRuntimeOverview?.health ?? null}
                  metrics={visibleRuntimeOverview?.metrics ?? null}
                />
                <RuntimeFailurePanel metrics={visibleRuntimeOverview?.metrics ?? null} />
              </div>
            ) : (
              <article className="rounded-[1.8rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] px-5 py-5 text-sm leading-7 text-neutral-400">
                Sign in to see runtime health, failure review, and live monitoring details.
              </article>
            )}
          </section>
        ) : null}

        {activeTab === "operate" ? (
          <section className="grid gap-6">
            <div className="grid gap-3">
              <SectionIntro
                eyebrow="Operate"
                title="Control the bot"
                copy="Deploy, pause, publish, and tune the runtime from one operations desk."
              />

              {walletAddress ? (
                <RuntimeControls
                  botId={params.botId}
                  walletAddress={walletAddress}
                  riskPolicy={runtimePolicy}
                  policyLoading={runtimePolicyStatus === "loading"}
                  getAuthHeaders={getAuthHeaders}
                  onRuntimeUpdate={refreshRuntimeData}
                />
              ) : (
                <article className="rounded-[1.8rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] px-5 py-5 text-sm leading-7 text-neutral-400">
                  Connect the wallet for this bot to unlock deployment and live controls.
                </article>
              )}
            </div>

            {walletAddress && visibleBot ? (
              <div className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] p-4 md:p-5">
                <div className="grid gap-5 xl:grid-cols-[0.28fr_1fr] xl:items-start">
                  <div className="grid gap-4">
                    <div className="rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4">
                      <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
                        Publishing
                      </div>
                      <div className="mt-2 font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
                        Marketplace profile
                      </div>
                      <p className="mt-2 text-sm leading-6 text-neutral-400">
                        Access mode, creator details, and discovery copy.
                      </p>
                    </div>

                    <div className="rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4">
                      <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
                        Advanced settings
                      </div>
                      <div className="mt-2 font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
                        Runtime policy
                      </div>
                      <p className="mt-2 text-sm leading-6 text-neutral-400">
                        Leverage, drawdown, cooldowns, and sizing rules.
                      </p>
                    </div>
                  </div>

                  <div className="grid gap-5">
                    <div className="grid gap-3">
                      <SectionIntro
                        eyebrow="Publishing"
                        title="Control visibility"
                        copy="Manage how this bot appears in the marketplace."
                      />
                      <BotPublishingPanel
                        key={visibleBot.id}
                        botId={visibleBot.id}
                        walletAddress={walletAddress}
                        getAuthHeaders={getAuthHeaders}
                        initialSettings={initialPublishingSettings}
                        onSaved={(nextSettings) => {
                          setBot((current) => (current ? { ...current, visibility: nextSettings.visibility } : current));
                        }}
                      />
                    </div>

                    <div className="h-px bg-[rgba(255,255,255,0.06)]" />

                    <div className="grid gap-3">
                      <SectionIntro
                        eyebrow="Advanced settings"
                        title="Runtime policy"
                        copy="The deploy controls and live policy editor both use this same policy source."
                      />
                      <AdvancedSettingsPanel
                        policy={runtimePolicy}
                        status={runtimePolicyStatus}
                        error={runtimePolicyError}
                        isDeployed={Boolean(activeRuntimeId)}
                        onPolicyChange={(nextPolicy) => {
                          setRuntimePolicy(nextPolicy);
                          setRuntimePolicyError(null);
                        }}
                        onSave={saveRuntimePolicy}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

        {activeTab === "activity" ? (
          <section className="grid gap-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <SectionIntro
                eyebrow="Activity stream"
                title="Recent runtime activity"
                copy="Latest decisions, outcomes, and repeated checks."
              />
              <span className="text-xs text-neutral-500">
                latest {EVENTS_PAGE_SIZE} events, refreshed about every minute
              </span>
            </div>

            {eventsError ? (
              <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
                {eventsError}
              </article>
            ) : null}

            {activityLoading && events.length === 0 ? (
              <DeferredPanelPlaceholder
                eyebrow="Activity stream"
                title="Loading recent activity"
                body="Recent runtime decisions are loading only when you open the activity desk."
              />
            ) : (
              <ExecutionLog events={sessionActive ? events : []} />
            )}
          </section>
        ) : null}
      </section>
    </main>
  );
}


function SectionIntro({
  eyebrow,
  title,
  copy,
}: {
  eyebrow: string;
  title: string;
  copy: string;
}) {
  return (
    <div className="grid gap-1 border-t border-[rgba(255,255,255,0.06)] pt-4">
      <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">
        {eyebrow}
      </span>
      <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">{title}</h2>
      <p className="max-w-3xl text-sm leading-7 text-neutral-400">{copy}</p>
    </div>
  );
}

function TabButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "rounded-full bg-[#dce85d] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a]"
          : "rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
      }
    >
      {label}
    </button>
  );
}
