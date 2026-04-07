"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

import { BotPerformancePanel } from "@/components/bots/bot-performance-panel";
import { ExecutionLog } from "@/components/bots/execution-log";
import { RuntimeFailurePanel } from "@/components/bots/runtime-failure-panel";
import { RuntimeHealthCard } from "@/components/bots/runtime-health-card";
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
  request_payload: Record<string, unknown>;
  result_payload: Record<string, unknown>;
  status: string;
  error_reason?: string | null;
  created_at: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const EVENTS_PAGE_SIZE = 40;
const REFRESH_INTERVAL_MS = 15000;

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
  const [performanceError, setPerformanceError] = useState<string | null>(null);
  const [primaryLoading, setPrimaryLoading] = useState(false);
  const [secondaryLoading, setSecondaryLoading] = useState(false);
  const [runtimeRefreshToken, setRuntimeRefreshToken] = useState(0);
  const [secondaryRefreshToken, setSecondaryRefreshToken] = useState(0);
  const [activeTab, setActiveTab] = useState<"overview" | "operate" | "activity">("overview");

  const sessionActive = authenticated && Boolean(walletAddress);

  useEffect(() => {
    if (!sessionActive || !walletAddress) {
      setBot(null);
      setEvents([]);
      setRuntimeOverview(null);
      setPerformance(null);
      setError(null);
      setEventsError(null);
      setPerformanceError(null);
      setPrimaryLoading(false);
      setSecondaryLoading(false);
      setRuntimeRefreshToken(0);
      setSecondaryRefreshToken(0);
      return;
    }

    const resolvedWallet = walletAddress;
    const controller = new AbortController();

    async function loadPrimary() {
      setPrimaryLoading(true);
      setSecondaryLoading(false);
      setBot(null);
      setEvents([]);
      setRuntimeOverview(null);
      setPerformance(null);
      setError(null);
      setEventsError(null);
      setPerformanceError(null);
      setRuntimeRefreshToken(0);
      setSecondaryRefreshToken(0);

      try {
        const headers = await getAuthHeaders();
        const walletQuery = encodeURIComponent(resolvedWallet);
        const [botResponse, overviewResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/bots/${params.botId}?wallet_address=${walletQuery}`, {
            cache: "no-store",
            headers,
            signal: controller.signal,
          }),
          fetch(`${API_BASE_URL}/api/bots/${params.botId}/runtime-overview?wallet_address=${walletQuery}`, {
            headers,
            signal: controller.signal,
          }),
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
        setError(null);
        setSecondaryLoading(true);
        setSecondaryRefreshToken(1);
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
          `${API_BASE_URL}/api/bots/${params.botId}/runtime-overview?wallet_address=${walletQuery}`,
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
    if (!sessionActive || !walletAddress || secondaryRefreshToken === 0) {
      return;
    }

    const resolvedWallet = walletAddress;
    const controller = new AbortController();

    async function loadSecondary() {
      setSecondaryLoading(true);
      try {
        const headers = await getAuthHeaders();
        const walletQuery = encodeURIComponent(resolvedWallet);

        const [eventsResult, performanceResult] = await Promise.allSettled([
          (async () => {
            const response = await fetch(
              `${API_BASE_URL}/api/bots/${params.botId}/events?wallet_address=${walletQuery}&limit=${EVENTS_PAGE_SIZE}`,
              {
                cache: "no-store",
                headers,
                signal: controller.signal,
              },
            );
            return unwrapResponse<BotExecutionEvent[]>(response, "Could not load activity stream");
          })(),
          (async () => {
            const response = await fetch(
              `${API_BASE_URL}/api/bots/${params.botId}/runtime-overview?wallet_address=${walletQuery}&include_performance=true&performance_mode=fast`,
              {
                headers,
                signal: controller.signal,
              },
            );
            const overview = await unwrapResponse<RuntimeOverview>(
              response,
              "Could not load performance snapshot",
            );
            return overview.performance;
          })(),
        ]);

        if (controller.signal.aborted) {
          return;
        }

        if (eventsResult.status === "fulfilled") {
          setEvents(eventsResult.value);
          setEventsError(null);
        } else {
          setEventsError(
            eventsResult.reason instanceof Error
              ? eventsResult.reason.message
              : "Could not load activity stream",
          );
        }

        if (performanceResult.status === "fulfilled") {
          setPerformance(performanceResult.value ?? null);
          setPerformanceError(null);
        } else {
          setPerformanceError(
            performanceResult.reason instanceof Error
              ? performanceResult.reason.message
              : "Could not load performance snapshot",
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setSecondaryLoading(false);
        }
      }
    }

    void loadSecondary();
    return () => controller.abort();
  }, [getAuthHeaders, params.botId, secondaryRefreshToken, sessionActive, walletAddress]);

  useEffect(() => {
    if (!sessionActive || !walletAddress || primaryLoading) {
      return;
    }

    const interval = window.setInterval(() => {
      setRuntimeRefreshToken((value) => value + 1);
      setSecondaryRefreshToken((value) => value + 1);
    }, REFRESH_INTERVAL_MS);

    return () => window.clearInterval(interval);
  }, [primaryLoading, sessionActive, walletAddress]);

  const visibleBot = sessionActive ? bot : null;
  const visibleRuntimeOverview = sessionActive ? runtimeOverview : null;
  const visibleError = sessionActive ? error : null;
  const runtime = useMemo(() => {
    if (!visibleRuntimeOverview?.health.runtime_id) {
      return null;
    }
    return {
      status: visibleRuntimeOverview.health.status,
      mode: visibleRuntimeOverview.health.mode,
      updated_at:
        visibleRuntimeOverview.health.last_runtime_update ??
        visibleRuntimeOverview.metrics.last_event_at ??
        "",
    };
  }, [visibleRuntimeOverview]);

  const runtimeHealth = visibleRuntimeOverview?.health.health ?? "not deployed";
  const runtimeReasons = (visibleRuntimeOverview?.health.reasons ?? []).slice(0, 2);
  const successRate = visibleRuntimeOverview?.metrics
    ? `${(visibleRuntimeOverview.metrics.success_rate * 100).toFixed(1)}%`
    : "--";
  const lastRuntimeEvent = runtime?.updated_at
    ? new Date(runtime.updated_at).toLocaleString()
    : "No runtime event yet";

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
      featured_collection_title: "Featured strategies",
      featured_rank: 0,
      is_featured: false,
      invite_wallet_addresses: [],
      invite_count: 0,
      creator_profile: {
        display_name: displayName,
        headline: "",
        bio: "",
        slug: "",
        featured_collection_title: "Featured strategies",
      },
    };
  }, [visibleBot, walletAddress]);

  function refreshRuntimeData() {
    setRuntimeRefreshToken((value) => value + 1);
    setSecondaryRefreshToken((value) => value + 1);
  }

  return (
    <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">
      <section className="grid gap-5 rounded-[2.2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.16),transparent_28%),radial-gradient(circle_at_80%_20%,rgba(116,185,127,0.12),transparent_24%),linear-gradient(135deg,#16181a,#0d0f10)] p-6 md:p-8">
        <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr] xl:items-end">
          <div className="grid gap-5">
            <div className="flex flex-wrap gap-2">
              <span className="rounded-full border border-[rgba(220,232,93,0.24)] bg-[#dce85d]/10 px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">
                Bot workspace
              </span>
              <span className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.18em] text-neutral-300">
                {visibleBot?.visibility ?? "draft"}
              </span>
            </div>

            <div className="grid gap-3">
              <h1 className="max-w-5xl font-mono text-[clamp(2.2rem,5vw,4.4rem)] font-extrabold uppercase leading-[0.9] tracking-[-0.06em] text-neutral-50">
                {visibleBot?.name ?? (primaryLoading ? "Loading bot" : "Bot workspace")}
              </h1>
              <p className="max-w-3xl text-sm leading-7 text-neutral-400 md:text-base">
                {visibleBot?.description ??
                  "Open runtime health, performance, publishing, and live controls from one place."}
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <HeroStat
                label="Status"
                value={runtime?.status ?? "draft"}
                accent="text-neutral-50"
                copy="Current runtime state"
              />
              <HeroStat
                label="Health"
                value={runtimeHealth}
                accent="text-[#74b97f]"
                copy="Latest runtime health"
              />
              <HeroStat
                label="Strategy"
                value={visibleBot?.strategy_type ?? "--"}
                accent="text-[#dce85d]"
                copy="Execution style"
              />
              <HeroStat
                label="Success rate"
                value={successRate}
                accent="text-neutral-50"
                copy="Latest 24h window"
              />
            </div>
          </div>

          <aside className="grid gap-4 rounded-[1.8rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10]/90 p-5">
            <div className="grid gap-3 rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4">
              <SignalLine label="Market scope" value={visibleBot?.market_scope ?? "--"} />
              <SignalLine label="Build flow" value="Builder" />
              <SignalLine label="Last event" value={lastRuntimeEvent} />
            </div>

            {runtimeReasons.length > 0 ? (
              <div className="grid gap-2 rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4">
                <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
                  Current notes
                </span>
                {runtimeReasons.map((reason) => (
                  <p key={reason} className="text-sm leading-6 text-neutral-400">
                    {reason}
                  </p>
                ))}
              </div>
            ) : null}

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
          </aside>
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

      {performanceError && !performance ? (
        <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
          {performanceError}
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
              {secondaryLoading && !performance ? (
                <DeferredPanelPlaceholder
                  eyebrow="Performance"
                  title="Loading live performance"
                  body="PnL and open position metrics are loading after the primary view."
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
                        Access mode, creator details, and shelf placement.
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
                        title="Refine live guardrails"
                        copy="Tighten execution boundaries after deployment."
                      />
                      {visibleRuntimeOverview?.health.runtime_id ? (
                        <AdvancedSettingsPanel
                          botId={params.botId}
                          walletAddress={walletAddress}
                          getAuthHeaders={getAuthHeaders}
                          onSaved={refreshRuntimeData}
                        />
                      ) : (
                        <article className="rounded-[1.8rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-5 text-sm leading-7 text-neutral-400">
                          Deploy this bot to unlock advanced runtime policy controls.
                        </article>
                      )}
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
                latest {EVENTS_PAGE_SIZE} events, refreshed every 15 seconds
              </span>
            </div>

            {eventsError ? (
              <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
                {eventsError}
              </article>
            ) : null}

            {secondaryLoading && events.length === 0 ? (
              <DeferredPanelPlaceholder
                eyebrow="Activity stream"
                title="Loading recent activity"
                body="Recent runtime decisions are loading after the primary view."
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

function HeroStat({
  label,
  value,
  copy,
  accent,
}: {
  label: string;
  value: string;
  copy: string;
  accent: string;
}) {
  return (
    <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] p-4">
      <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</span>
      <div className={`font-mono text-2xl font-bold uppercase ${accent}`}>{value}</div>
      <p className="text-xs leading-6 text-neutral-400">{copy}</p>
    </article>
  );
}

function SignalLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[rgba(255,255,255,0.06)] pb-3 last:border-b-0 last:pb-0">
      <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</span>
      <span className="text-right text-sm font-semibold text-neutral-100">{value}</span>
    </div>
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
    <div className="grid gap-1">
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
