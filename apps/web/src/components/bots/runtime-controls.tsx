"use client";

import { useEffect, useMemo, useState } from "react";

import {
  type RuntimePolicyDraft,
  runtimePolicyDraftToPayloadWithoutAllowlist,
} from "@/components/bots/runtime-policy";
import {
  PacificaOnboardingChecklist,
  type PacificaOnboardingStatus,
} from "@/components/pacifica/onboarding-checklist";
import { useClashxAuth } from "@/lib/clashx-auth";
import {
  PacificaReadinessError,
  fetchPacificaReadiness,
  type PacificaReadinessPayload,
} from "@/lib/pacifica-readiness";

type RuntimeResponse = {
  id: string;
  status: string;
  mode: string;
  updated_at: string;
  deployed_at?: string | null;
  stopped_at?: string | null;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const SECTION_CARD_CLASS =
  "grid gap-4 rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] p-4";

export function RuntimeControls({
  botId,
  walletAddress,
  riskPolicy,
  policyLoading = false,
  getAuthHeaders,
  onRuntimeUpdate,
}: {
  botId: string;
  walletAddress: string;
  riskPolicy: RuntimePolicyDraft;
  policyLoading?: boolean;
  getAuthHeaders: (headersInit?: HeadersInit) => Promise<Headers>;
  onRuntimeUpdate?: (runtime: RuntimeResponse) => void;
}) {
  const { authenticated } = useClashxAuth();
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

  const serializedRiskPolicy = useMemo(
    () => runtimePolicyDraftToPayloadWithoutAllowlist(riskPolicy),
    [riskPolicy],
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
        const payload = await fetchPacificaReadiness(walletAddress, getAuthHeaders);
        if (!cancelled) {
          setReadiness(payload);
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
    if (policyLoading) {
      return "Loading the shared runtime policy.";
    }
    if (readinessStatus === "loading") {
      return "Checking Pacifica readiness.";
    }
    if (readinessStatus === "error") {
      return "Unable to verify Pacifica readiness right now.";
    }
    return readiness?.blockers[0] ?? null;
  }, [authenticated, policyLoading, readiness?.blockers, readinessStatus, walletAddress]);

  async function invoke(action: "deploy" | "pause" | "resume" | "stop") {
    if (action === "deploy" && !setupStatus.ready) {
      setSetupOpen(true);
      return;
    }

    setStatus(action);
    setError(null);

    try {
      if (action === "deploy") {
        await fetchPacificaReadiness(walletAddress, getAuthHeaders).then((payload) => {
          setReadiness(payload);
          if (!payload.ready) {
            throw new PacificaReadinessError(payload);
          }
        });
      }

      const endpoint = `${API_BASE_URL}/api/bots/${botId}/${action}`;
      const body =
        action === "deploy"
          ? { wallet_address: walletAddress, risk_policy_json: serializedRiskPolicy }
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
      if (action === "deploy" && runtimeError instanceof PacificaReadinessError) {
        setSetupOpen(true);
      }
      setError(runtimeError instanceof Error ? runtimeError.message : "Runtime action failed");
    } finally {
      setStatus("idle");
    }
  }

  return (
    <article className="grid gap-5 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <PacificaOnboardingChecklist
        open={setupOpen}
        onClose={() => setSetupOpen(false)}
        mode="builder"
        onStatusChange={setSetupStatus}
        walletAddressOverride={walletAddress}
      />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">
            Runtime controls
          </span>
          <h3 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
            Run this bot live
          </h3>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            Check deployment readiness, review the shared runtime policy, and control the live runtime from one place.
          </p>
        </div>
        <span className="text-xs text-neutral-500">wallet-bound live deployment</span>
      </div>

      <div className={SECTION_CARD_CLASS}>
        <div className="grid gap-1">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
            Shared runtime policy
          </span>
          <p className="text-sm leading-7 text-neutral-400">
            Deploy uses the runtime policy configured below in the runtime policy editor. This panel is read-only so the operate tab has one policy source instead of competing forms.
          </p>
        </div>

        {policyLoading ? (
          <div className="rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-400">
            Loading the current runtime policy before the next deploy.
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <PolicyStat label="Leverage cap" value={`${riskPolicy.maxLeverage}x`} />
            <PolicyStat label="Max order size" value={`$${riskPolicy.maxOrderSizeUsd}`} />
            <PolicyStat label="Allocated capital" value={`$${riskPolicy.allocatedCapitalUsd}`} />
            <PolicyStat label="Max open positions" value={`${riskPolicy.maxOpenPositions}`} />
            <PolicyStat label="Cooldown" value={`${riskPolicy.cooldownSeconds}s`} />
            <PolicyStat label="Max drawdown" value={`${riskPolicy.maxDrawdownPct}%`} />
            <PolicyStat
              label="Market scope"
              value={riskPolicy.allowedSymbols.trim().length > 0 ? riskPolicy.allowedSymbols.split(',').join(', ') : "All supported"}
            />
            <PolicyStat label="Sizing mode" value={riskPolicy.sizingMode.replaceAll("_", " ")} />
            <PolicyStat
              label={riskPolicy.sizingMode === "fixed_usd" ? "USD per trade" : "Risk per trade"}
              value={
                riskPolicy.sizingMode === "fixed_usd"
                  ? `$${riskPolicy.fixedUsdAmount}`
                  : `${riskPolicy.riskPerTradePct}% (builder SL)`
              }
            />
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3">
          <p className="text-xs leading-6 text-neutral-500">
            With this profile, the bot can hold up to {riskPolicy.maxOpenPositions} live position
            {riskPolicy.maxOpenPositions === 1 ? "" : "s"} and waits {riskPolicy.cooldownSeconds}s before the next fresh entry.
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
          <pre className="overflow-x-auto rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3 text-xs leading-6 text-neutral-300">
            {JSON.stringify(serializedRiskPolicy, null, 2)}
          </pre>
        ) : null}
      </div>

      {readinessBlocker && status !== "deploy" ? (
        <div className="rounded-[1.2rem] border border-[rgba(220,232,93,0.18)] bg-[rgba(220,232,93,0.08)] px-4 py-3 text-sm leading-6 text-neutral-200">
          <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d]">
            Deploy blocked
          </div>
          <div className="mt-1">{readinessBlocker}</div>
        </div>
      ) : null}

      {error ? <p className="text-sm text-[#dce85d]">{error}</p> : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void invoke("deploy")}
          disabled={status !== "idle" || policyLoading}
          className="bg-[#dce85d] px-4 py-2.5 font-mono text-[0.62rem] font-semibold uppercase tracking-wider text-[#090a0a] transition hover:bg-[#e8f06d] disabled:opacity-60"
        >
          {status === "deploy" ? "deploying..." : "deploy"}
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
    </article>
  );
}

function PolicyStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3 min-w-0">
      <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</div>
      <div className="mt-2 text-sm text-neutral-200 line-clamp-2" title={value}>{value}</div>
    </div>
  );
}
