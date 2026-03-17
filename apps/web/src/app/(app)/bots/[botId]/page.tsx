"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

import { AdvancedSettingsPanel } from "@/components/bots/advanced-settings-panel";
import { ExecutionLog } from "@/components/bots/execution-log";
import { RuntimeFailurePanel } from "@/components/bots/runtime-failure-panel";
import { RuntimeHealthCard } from "@/components/bots/runtime-health-card";
import { RuntimeControls } from "@/components/bots/runtime-controls";
import { useClashxAuth } from "@/lib/clashx-auth";

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

type RuntimeState = {
  status: string;
  mode: string;
  updated_at: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function BotDetailPage({ params: paramsPromise }: { params: Promise<{ botId: string }> }) {
  const params = use(paramsPromise);
  const { authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();

  const [bot, setBot] = useState<BotDefinition | null>(null);
  const [events, setEvents] = useState<BotExecutionEvent[]>([]);
  const [runtime, setRuntime] = useState<RuntimeState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const resolvedWallet = walletAddress;
    if (!authenticated || !resolvedWallet) {
      setBot(null);
      setEvents([]);
      setRuntime(null);
      return;
    }

    async function loadDetails() {
      try {
        const headers = await getAuthHeaders();
        const botResponse = await fetch(
          `${API_BASE_URL}/api/bots/${params.botId}?wallet_address=${encodeURIComponent(resolvedWallet ?? "")}`,
          { cache: "no-store", headers },
        );
        const botPayload = (await botResponse.json()) as BotDefinition | { detail?: string };
        if (!botResponse.ok) {
          throw new Error("detail" in botPayload ? botPayload.detail ?? "Could not load bot" : "Could not load bot");
        }
        setBot(botPayload as BotDefinition);

        const eventsResponse = await fetch(
          `${API_BASE_URL}/api/bots/${params.botId}/events?wallet_address=${encodeURIComponent(resolvedWallet ?? "")}&limit=100`,
          { cache: "no-store", headers },
        );
        const eventsPayload = (await eventsResponse.json()) as BotExecutionEvent[] | { detail?: string };
        if (!eventsResponse.ok) {
          throw new Error("detail" in eventsPayload ? eventsPayload.detail ?? "Could not load events" : "Could not load events");
        }
        const nextEvents = eventsPayload as BotExecutionEvent[];
        setEvents(nextEvents);
        setRefreshToken((value) => value + 1);

        const transition = nextEvents.find((event) => event.event_type.startsWith("runtime."));
        if (transition) {
          setRuntime({
            status: String(transition.result_payload?.status ?? "unknown"),
            mode: "live",
            updated_at: transition.created_at,
          });
        } else {
          setRuntime(null);
        }

        setError(null);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load bot runtime");
      }
    }

    void loadDetails();
  }, [authenticated, walletAddress, params.botId, getAuthHeaders]);

  const runtimeHealth = useMemo(() => {
    const errorCount = events.filter((event) => event.status === "error").length;
    if (!runtime) {
      return "not deployed";
    }
    if (runtime.status === "active" && errorCount === 0) {
      return "healthy";
    }
    if (runtime.status === "active" && errorCount > 0) {
      return "degraded";
    }
    return runtime.status;
  }, [events, runtime]);

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <article className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <span className="label text-[#dce85d]">Bot summary</span>
          <h2 className="font-mono text-3xl font-bold uppercase tracking-tight text-neutral-50">
            {bot?.name ?? "Loading bot"}
          </h2>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            {bot?.description ?? "Loading the bot description and runtime data."}
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Build flow</div>
              <div className="mt-1 text-sm font-semibold text-neutral-50">Builder</div>
            </div>
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Strategy type</div>
              <div className="mt-1 text-sm font-semibold text-neutral-50">{bot?.strategy_type ?? "--"}</div>
            </div>
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Market scope</div>
              <div className="mt-1 text-sm font-semibold text-neutral-50">{bot?.market_scope ?? "--"}</div>
            </div>
          </div>
        </article>

        <article className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <div className="flex items-center justify-between gap-3">
            <span className="label text-[#74b97f]">Runtime snapshot</span>
            <Link
              href="/bots"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
            >
              Back to my bots
            </Link>
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

      {!authenticated ? (
        <button
          type="button"
          onClick={login}
          className="w-fit rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
        >
          Sign in to manage this bot
        </button>
      ) : null}

      {error ? (
        <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
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
            onRuntimeUpdate={(nextRuntime) => {
              setRuntime({ status: nextRuntime.status, mode: nextRuntime.mode, updated_at: nextRuntime.updated_at });
              setEvents((current) => current);
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
          <RuntimeHealthCard
            botId={params.botId}
            walletAddress={walletAddress}
            getAuthHeaders={getAuthHeaders}
            refreshToken={refreshToken}
          />
          <RuntimeFailurePanel
            botId={params.botId}
            walletAddress={walletAddress}
            getAuthHeaders={getAuthHeaders}
            refreshToken={refreshToken}
          />
        </section>
      ) : null}

      {walletAddress ? (
        <section className="grid gap-3">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Advanced settings</span>
          <AdvancedSettingsPanel
            botId={params.botId}
            walletAddress={walletAddress}
            getAuthHeaders={getAuthHeaders}
            onSaved={() => setRefreshToken((value) => value + 1)}
          />
        </section>
      ) : null}

      <section className="grid gap-4">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Execution log</span>
        <ExecutionLog events={events} />
      </section>
    </main>
  );
}
