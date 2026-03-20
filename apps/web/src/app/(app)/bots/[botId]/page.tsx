"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

import { AdvancedSettingsPanel } from "@/components/bots/advanced-settings-panel";
import { BotPerformancePanel } from "@/components/bots/bot-performance-panel";
import { ExecutionLog } from "@/components/bots/execution-log";
import { RuntimeFailurePanel } from "@/components/bots/runtime-failure-panel";
import { RuntimeHealthCard } from "@/components/bots/runtime-health-card";
import { RuntimeControls } from "@/components/bots/runtime-controls";
import { useClashxAuth } from "@/lib/clashx-auth";
import type { RuntimeOverview } from "@/lib/runtime-overview";

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

export default function BotDetailPage({ params: paramsPromise }: { params: Promise<{ botId: string }> }) {
  const params = use(paramsPromise);
  const { authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();

  const [bot, setBot] = useState<BotDefinition | null>(null);
  const [events, setEvents] = useState<BotExecutionEvent[]>([]);
  const [runtimeOverview, setRuntimeOverview] = useState<RuntimeOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const resolvedWalletValue = walletAddress;
    if (!authenticated || !resolvedWalletValue) {
      return;
    }

    const controller = new AbortController();

    async function loadDetails() {
      try {
        const headers = await getAuthHeaders();
        const walletQuery = encodeURIComponent(resolvedWalletValue ?? "");
        const [botResponse, eventsResponse, overviewResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/bots/${params.botId}?wallet_address=${walletQuery}`, {
            cache: "no-store",
            headers,
            signal: controller.signal,
          }),
          fetch(`${API_BASE_URL}/api/bots/${params.botId}/events?wallet_address=${walletQuery}&limit=100`, {
            cache: "no-store",
            headers,
            signal: controller.signal,
          }),
          fetch(`${API_BASE_URL}/api/bots/${params.botId}/runtime-overview?wallet_address=${walletQuery}`, {
            cache: "no-store",
            headers,
            signal: controller.signal,
          }),
        ]);

        const [nextBot, nextEvents, nextOverview] = await Promise.all([
          unwrapResponse<BotDefinition>(botResponse, "Could not load bot"),
          unwrapResponse<BotExecutionEvent[]>(eventsResponse, "Could not load events"),
          unwrapResponse<RuntimeOverview>(overviewResponse, "Could not load runtime overview"),
        ]);

        if (controller.signal.aborted) {
          return;
        }
        setBot(nextBot);
        setEvents(nextEvents);
        setRuntimeOverview(nextOverview);
        setError(null);
      } catch (loadError) {
        if (controller.signal.aborted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Could not load bot runtime");
      }
    }

    void loadDetails();
    return () => controller.abort();
  }, [authenticated, walletAddress, params.botId, getAuthHeaders, refreshToken]);

  useEffect(() => {
    if (!authenticated || !walletAddress) {
      return;
    }
    const interval = window.setInterval(() => {
      setRefreshToken((value) => value + 1);
    }, 15000);
    return () => window.clearInterval(interval);
  }, [authenticated, walletAddress]);

  const sessionActive = authenticated && Boolean(walletAddress);
  const visibleBot = sessionActive ? bot : null;
  const visibleEvents = sessionActive ? events : [];
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

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <article className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <span className="label text-[#dce85d]">Bot summary</span>
          <h2 className="font-mono text-3xl font-bold uppercase tracking-tight text-neutral-50">
            {visibleBot?.name ?? "Loading bot"}
          </h2>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            {visibleBot?.description ?? "Loading the bot description and runtime data."}
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
                href={`/build?botId=${encodeURIComponent(params.botId)}`}
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

      <BotPerformancePanel performance={visibleRuntimeOverview?.performance ?? null} />

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
            onRuntimeUpdate={() => {
              setRefreshToken((value) => value + 1);
            }}
          />
        ) : (
          <article className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-5 text-sm leading-7 text-neutral-400">
            Connect the wallet for this bot if you want to start, stop, or change the runtime.
          </article>
        )}
      </section>

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
            onSaved={() => setRefreshToken((value) => value + 1)}
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
          <span className="text-xs text-neutral-500">refreshes every 15 seconds while this page is open</span>
        </div>
        <ExecutionLog events={visibleEvents} />
      </section>
    </main>
  );
}
