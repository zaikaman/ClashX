"use client";

import { useEffect, useMemo, useState } from "react";

import {
  PacificaOnboardingChecklist,
  type PacificaOnboardingStatus,
} from "@/components/pacifica/onboarding-checklist";
import { useClashxAuth } from "@/lib/clashx-auth";

type RuntimeResponse = {
  id: string;
  status: string;
  mode: string;
  updated_at: string;
  deployed_at?: string | null;
  stopped_at?: string | null;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type PacificaReadinessPayload = {
  ready: boolean;
  blockers: string[];
};

export function RuntimeControls({
  botId,
  walletAddress,
  getAuthHeaders,
  onRuntimeUpdate,
}: {
  botId: string;
  walletAddress: string;
  getAuthHeaders: (headersInit?: HeadersInit) => Promise<Headers>;
  onRuntimeUpdate?: (runtime: RuntimeResponse) => void;
}) {
  const { authenticated } = useClashxAuth();
  const [maxLeverage, setMaxLeverage] = useState(5);
  const [maxOrderSizeUsd, setMaxOrderSizeUsd] = useState(200);
  const [allocatedCapitalUsd, setAllocatedCapitalUsd] = useState(200);
  const [cooldownSeconds, setCooldownSeconds] = useState(45);
  const [maxDrawdownPct, setMaxDrawdownPct] = useState(18);
  const [maxOpenPositions, setMaxOpenPositions] = useState(1);
  const [showRawPolicy, setShowRawPolicy] = useState(false);
  const [status, setStatus] = useState<"idle" | "deploy" | "pause" | "resume" | "stop">("idle");
  const [error, setError] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<PacificaReadinessPayload | null>(null);
  const [readinessStatus, setReadinessStatus] = useState<"idle" | "loading" | "error">("idle");
  const [setupOpen, setSetupOpen] = useState(false);
  const [setupStatus, setSetupStatus] = useState<PacificaOnboardingStatus>({
    ready: false,
    blocker: "Sign in with your trading wallet before you deploy.",
    fundingVerified: false,
    appAccessVerified: false,
    agentAuthorized: false,
  });

  const riskPolicy = useMemo(
    () => ({
      max_leverage: maxLeverage,
      max_order_size_usd: maxOrderSizeUsd,
      allocated_capital_usd: allocatedCapitalUsd,
      cooldown_seconds: cooldownSeconds,
      max_drawdown_pct: maxDrawdownPct,
      max_open_positions: maxOpenPositions,
    }),
    [
      allocatedCapitalUsd,
      cooldownSeconds,
      maxDrawdownPct,
      maxLeverage,
      maxOpenPositions,
      maxOrderSizeUsd,
    ],
  );

  useEffect(() => {
    if (!authenticated || !walletAddress) {
      setReadiness(null);
      setReadinessStatus("idle");
      return;
    }

    let cancelled = false;

    async function loadReadiness() {
      setReadinessStatus("loading");
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/pacifica/readiness?wallet_address=${encodeURIComponent(walletAddress.trim())}`,
          {
            cache: "no-store",
            headers: await getAuthHeaders(),
          },
        );
        const payload = (await response.json()) as PacificaReadinessPayload | { detail?: string };
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Pacifica readiness check failed." : "Pacifica readiness check failed.");
        }
        if (!cancelled) {
          setReadiness(payload as PacificaReadinessPayload);
          setReadinessStatus("idle");
        }
      } catch {
        if (!cancelled) {
          setReadiness(null);
          setReadinessStatus("error");
        }
      }
    }

    void loadReadiness();
    return () => {
      cancelled = true;
    };
  }, [authenticated, getAuthHeaders, walletAddress]);

  const readinessBlocker = useMemo(() => {
    if (!authenticated) {
      return "Sign in with your trading wallet before you deploy.";
    }
    if (!walletAddress) {
      return "Connect the wallet you want ClashX to trade with.";
    }
    if (readinessStatus === "loading") {
      return "Checking Pacifica readiness.";
    }
    if (readinessStatus === "error") {
      return "Unable to verify Pacifica readiness right now.";
    }
    return readiness?.blockers[0] ?? null;
  }, [authenticated, readiness?.blockers, readinessStatus, walletAddress]);

  async function invoke(action: "deploy" | "pause" | "resume" | "stop") {
    if (action === "deploy" && !setupStatus.ready) {
      setSetupOpen(true);
      return;
    }
    setStatus(action);
    setError(null);
    try {
      const endpoint = `${API_BASE_URL}/api/bots/${botId}/${action}`;
      const body =
        action === "deploy"
          ? { wallet_address: walletAddress, risk_policy_json: riskPolicy }
          : undefined;

      const response = await fetch(endpoint, {
        method: "POST",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: body ? JSON.stringify(body) : undefined,
      });
      const payload = (await response.json()) as RuntimeResponse | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Runtime action failed" : "Runtime action failed");
      }
      onRuntimeUpdate?.(payload as RuntimeResponse);
    } catch (runtimeError) {
      setError(runtimeError instanceof Error ? runtimeError.message : "Runtime action failed");
    } finally {
      setStatus("idle");
    }
  }

  return (
    <section className="grid gap-5 border-l-2 border-[#74b97f] bg-[#16181a] p-6">
      <PacificaOnboardingChecklist
        open={setupOpen}
        onClose={() => setSetupOpen(false)}
        mode="builder"
        onStatusChange={setSetupStatus}
      />
      <div className="flex items-center justify-between">
        <span className="label text-[#74b97f]">runtime controls</span>
        <span className="text-xs text-neutral-500">wallet-bound live deployment</span>
      </div>

      <div className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
        <div className="grid gap-1">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">deploy profile</span>
          <p className="text-sm leading-6 text-neutral-400">
            Set the live guardrails the bot will use the moment it starts trading.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <label className="grid gap-1.5 text-sm text-neutral-400">
            Max leverage
            <input
              type="number"
              min={1}
              value={maxLeverage}
              onChange={(event) => setMaxLeverage(Number(event.target.value))}
              className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
            />
          </label>
          <label className="grid gap-1.5 text-sm text-neutral-400">
            Max order size
            <input
              type="number"
              min={1}
              value={maxOrderSizeUsd}
              onChange={(event) => setMaxOrderSizeUsd(Number(event.target.value))}
              className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
            />
          </label>
          <label className="grid gap-1.5 text-sm text-neutral-400">
            Allocated capital
            <input
              type="number"
              min={1}
              value={allocatedCapitalUsd}
              onChange={(event) => setAllocatedCapitalUsd(Number(event.target.value))}
              className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
            />
          </label>
          <label className="grid gap-1.5 text-sm text-neutral-400">
            Cooldown
            <input
              type="number"
              min={0}
              value={cooldownSeconds}
              onChange={(event) => setCooldownSeconds(Number(event.target.value))}
              className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
            />
          </label>
          <label className="grid gap-1.5 text-sm text-neutral-400">
            Max drawdown %
            <input
              type="number"
              min={0}
              step="0.1"
              value={maxDrawdownPct}
              onChange={(event) => setMaxDrawdownPct(Number(event.target.value))}
              className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
            />
          </label>
          <label className="grid gap-1.5 text-sm text-neutral-400">
            Open positions allowed
            <input
              type="number"
              min={1}
              value={maxOpenPositions}
              onChange={(event) => setMaxOpenPositions(Number(event.target.value))}
              className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[rgba(255,255,255,0.05)] bg-[#111416] px-4 py-3">
          <p className="text-xs leading-6 text-neutral-500">
            With this profile, the bot can hold up to {maxOpenPositions} live position{maxOpenPositions === 1 ? "" : "s"} and waits {cooldownSeconds}s before the next fresh entry.
          </p>
          <button
            type="button"
            onClick={() => setShowRawPolicy((current) => !current)}
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
          >
            {showRawPolicy ? "Hide raw policy" : "View raw policy"}
          </button>
        </div>

        {showRawPolicy ? (
          <pre className="overflow-x-auto rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-4 py-3 text-xs leading-6 text-neutral-300">
            {JSON.stringify(riskPolicy, null, 2)}
          </pre>
        ) : null}
      </div>

      {readinessBlocker && status !== "deploy" ? (
        <div className="rounded-xl border border-[rgba(220,232,93,0.18)] bg-[rgba(220,232,93,0.08)] px-4 py-3 text-sm leading-6 text-neutral-200">
          <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d]">Deploy blocked</div>
          <div className="mt-1">{readinessBlocker}</div>
        </div>
      ) : null}

      {error ? <p className="text-sm text-[#dce85d]">{error}</p> : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void invoke("deploy")}
          disabled={status !== "idle"}
          className="bg-[#dce85d] px-4 py-2.5 font-mono text-[0.62rem] font-semibold uppercase tracking-wider text-[#090a0a] transition hover:bg-[#e8f06d] disabled:opacity-60"
        >
          {status === "deploy" ? "deploying…" : "deploy"}
        </button>
        <button
          type="button"
          onClick={() => void invoke("pause")}
          disabled={status !== "idle"}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2.5 text-[0.62rem] font-semibold uppercase tracking-wider text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d] disabled:opacity-60"
        >
          pause
        </button>
        <button
          type="button"
          onClick={() => void invoke("resume")}
          disabled={status !== "idle"}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2.5 text-[0.62rem] font-semibold uppercase tracking-wider text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f] disabled:opacity-60"
        >
          resume
        </button>
        <button
          type="button"
          onClick={() => void invoke("stop")}
          disabled={status !== "idle"}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2.5 text-[0.62rem] font-semibold uppercase tracking-wider text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d] disabled:opacity-60"
        >
          stop
        </button>
      </div>
    </section>
  );
}
