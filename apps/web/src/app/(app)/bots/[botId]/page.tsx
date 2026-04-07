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
    <article className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-5">
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
      updated_at: visibleRuntimeOverview.health.last_runtime_update ?? visibleRuntimeOverview.metrics.last_event_at ?? "",
    };
  }, [visibleRuntimeOverview]);

  const runtimeHealth = visibleRuntimeOverview?.health.health ?? "not deployed";

  function refreshRuntimeData() {
    setRuntimeRefreshToken((value) => value + 1);
    setSecondaryRefreshToken((value) => value + 1);
  }

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <article className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <span className="label text-[#dce85d]">Bot summary</span>
          <h2 className="font-mono text-3xl font-bold uppercase tracking-tight text-neutral-50">
            {visibleBot?.name ?? (primaryLoading ? "Loading bot" : "Bot workspace")}
          </h2>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            {visibleBot?.description ?? "Loading the bot description and core runtime status."}
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Build flow</div>
              <div className="mt-1 text-sm font-semibold text-neutral-50">Builder</div>
            </div>
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Strategy type</div>
              <div className="mt-1 text-sm font-semibold text-neutral-50">{visibleBot?.strategy_type ?? "--"}</div>
            </div>
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Market scope</div>
              <div className="mt-1 text-sm font-semibold text-neutral-50">{visibleBot?.market_scope ?? "--"}</div>
            </div>
          </div>
        </article>

        <article className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <div className="flex items-center justify-between gap-3">
            <span className="label text-[#74b97f]">Runtime snapshot</span>
            <div className="flex items-center gap-2">
              <Link
                href={`/builder?botId=${encodeURIComponent(params.botId)}`}
                className="rounded-full border border-[rgba(220,232,93,0.24)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d] transition hover:border-[#dce85d] hover:bg-[#dce85d]/8"
              >
                Edit in builder
              </Link>
              <Link
                href={`/backtests?botId=${encodeURIComponent(params.botId)}`}
                className="rounded-full border border-[rgba(116,185,127,0.22)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f] transition hover:border-[#74b97f] hover:bg-[#74b97f]/8"
              >
                Open backtests
              </Link>
              <Link
                href="/bots"
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
              >
                Back to my bots
              </Link>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Status</div>
              <div className="mt-1 font-mono text-xl font-bold uppercase text-neutral-50">
                {runtime?.status ?? "draft"}
              </div>
            </div>
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Health</div>
              <div className="mt-1 font-mono text-xl font-bold uppercase text-neutral-50">
                {runtimeHealth}
              </div>
            </div>
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Last runtime event</div>
              <div className="mt-1 text-sm font-semibold text-neutral-50">
                {runtime?.updated_at ? new Date(runtime.updated_at).toLocaleString() : "No runtime event yet"}
              </div>
            </div>
          </div>
        </article>
      </section>

      {performanceError && !performance ? (
        <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
          {performanceError}
        </article>
      ) : null}

      {secondaryLoading && !performance ? (
        <DeferredPanelPlaceholder
          eyebrow="Performance snapshot"
          title="Loading live performance"
          body="PnL and open position metrics are loading after the primary view."
        />
      ) : (
        <BotPerformancePanel performance={sessionActive ? performance : null} />
      )}

      {!authenticated ? (
        <button
          type="button"
          onClick={login}
          className="w-fit rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
        >
          Sign in to manage this bot
        </button>
      ) : null}

      {visibleError ? (
        <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
          {visibleError}
        </article>
      ) : null}

      <section className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Runtime controls</span>
        </div>
        {walletAddress ? (
          <RuntimeControls
            botId={params.botId}
            walletAddress={walletAddress}
            getAuthHeaders={getAuthHeaders}
            onRuntimeUpdate={refreshRuntimeData}
          />
        ) : (
          <article className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-5 text-sm leading-7 text-neutral-400">
            Connect the wallet for this bot if you want to start, stop, or change the runtime.
          </article>
        )}
      </section>

      {walletAddress && visibleBot ? (
        <section className="grid gap-3">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Publishing</span>
          <BotPublishingPanel
            botId={visibleBot.id}
            walletAddress={walletAddress}
            getAuthHeaders={getAuthHeaders}
            onSaved={(nextSettings) => {
              setBot((current) => (current ? { ...current, visibility: nextSettings.visibility } : current));
            }}
          />
        </section>
      ) : null}

      {walletAddress ? (
        <section className="grid gap-6 xl:grid-cols-2">
          <RuntimeHealthCard health={visibleRuntimeOverview?.health ?? null} metrics={visibleRuntimeOverview?.metrics ?? null} />
          <RuntimeFailurePanel metrics={visibleRuntimeOverview?.metrics ?? null} />
        </section>
      ) : null}

      {walletAddress && visibleRuntimeOverview?.health.runtime_id ? (
        <section className="grid gap-3">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Advanced settings</span>
          <AdvancedSettingsPanel
            botId={params.botId}
            walletAddress={walletAddress}
            getAuthHeaders={getAuthHeaders}
            onSaved={refreshRuntimeData}
          />
        </section>
      ) : walletAddress && visibleRuntimeOverview ? (
        <article className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-5 text-sm leading-7 text-neutral-400">
          Deploy this bot to unlock live runtime controls and risk policy settings.
        </article>
      ) : null}

      <section className="grid gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Activity stream</span>
          <span className="text-xs text-neutral-500">
            showing the latest {EVENTS_PAGE_SIZE} events, refreshed every 15 seconds while this page is open
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
    </main>
  );
}
