"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AgentAuthorizationPanel } from "@/components/pacifica/agent-authorization-panel";
import {
  fetchPacificaReadiness,
  type PacificaReadinessPayload,
} from "@/lib/pacifica-readiness";
import { useClashxAuth } from "@/lib/clashx-auth";

export type PacificaOnboardingStatus = {
  ready: boolean;
  blocker: string | null;
  fundingVerified: boolean;
  appAccessVerified: boolean;
  agentAuthorized: boolean;
};

function formatUsd(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value);
}

function formatMetricUsd(value: number | null) {
  return value === null ? "--" : formatUsd(value);
}

function formatSol(value: number) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 3,
  }).format(value);
}

export function PacificaOnboardingChecklist({
  open,
  onClose,
  mode = "builder",
  onStatusChange,
  walletAddressOverride,
}: {
  open: boolean;
  onClose: () => void;
  mode?: "builder" | "agent";
  onStatusChange?: (status: PacificaOnboardingStatus) => void;
  walletAddressOverride?: string | null;
}) {
  const { authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();
  const resolvedWalletAddress = walletAddressOverride?.trim() || walletAddress || null;
  const [readiness, setReadiness] = useState<PacificaReadinessPayload | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [agentAuthorizationOpen, setAgentAuthorizationOpen] = useState(false);
  const resolvedReadiness = authenticated && resolvedWalletAddress ? readiness : null;
  const resolvedStatus = authenticated && resolvedWalletAddress ? status : "idle";
  const resolvedError = authenticated && resolvedWalletAddress ? error : null;

  const loadReadiness = useCallback(async () => {
    if (!authenticated || !resolvedWalletAddress) {
      return null;
    }
    return fetchPacificaReadiness(resolvedWalletAddress, getAuthHeaders);
  }, [authenticated, getAuthHeaders, resolvedWalletAddress]);

  useEffect(() => {
    if (!authenticated || !resolvedWalletAddress) {
      return;
    }

    let cancelled = false;

    async function loadReadiness() {
      const activeWalletAddress = resolvedWalletAddress;
      if (!activeWalletAddress) {
        return;
      }
      setStatus("loading");
      setError(null);
      try {
        const payload = await fetchPacificaReadiness(activeWalletAddress, getAuthHeaders);
        if (cancelled) {
          return;
        }
        setReadiness(payload);
        setStatus("idle");
      } catch (loadError) {
        if (cancelled) {
          return;
        }
        setStatus("error");
        setError(loadError instanceof Error ? loadError.message : "Unable to load Pacifica readiness.");
      }
    }

    void loadReadiness();
    return () => {
      cancelled = true;
    };
  }, [authenticated, getAuthHeaders, resolvedWalletAddress]);

  const fundingStep = resolvedReadiness?.steps.find((step) => step.id === "funding");
  const appAccessStep = resolvedReadiness?.steps.find((step) => step.id === "app_access");
  const agentStep = resolvedReadiness?.steps.find((step) => step.id === "agent_authorization");
  const visibleSteps = resolvedReadiness?.steps.filter((step) => step.id !== "app_access") ?? [];
  const blocker = useMemo(() => {
    if (!authenticated) {
      return "Sign in with your trading wallet before you deploy.";
    }
    if (!resolvedWalletAddress) {
      return "Connect the Solana wallet you want ClashX to trade with.";
    }
    if (resolvedStatus === "loading") {
      return "Checking Pacifica readiness.";
    }
    if (resolvedError) {
      return resolvedError;
    }
    return resolvedReadiness?.blockers[0] ?? null;
  }, [authenticated, resolvedError, resolvedReadiness?.blockers, resolvedStatus, resolvedWalletAddress]);

  useEffect(() => {
    onStatusChange?.({
      ready: blocker === null,
      blocker,
      fundingVerified: Boolean(fundingStep?.verified),
      appAccessVerified: Boolean(appAccessStep?.verified),
      agentAuthorized: Boolean(agentStep?.verified),
    });
  }, [agentStep?.verified, appAccessStep?.verified, blocker, fundingStep?.verified, onStatusChange]);

  const refreshReadiness = useCallback(async () => {
    if (!authenticated || !resolvedWalletAddress) {
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      const payload = await loadReadiness();
      setReadiness(payload);
      setStatus("idle");
    } catch (loadError) {
      setStatus("error");
      setError(loadError instanceof Error ? loadError.message : "Unable to load Pacifica readiness.");
    }
  }, [authenticated, loadReadiness, resolvedWalletAddress]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-[color:var(--bg-overlay)] p-3 backdrop-blur-sm md:p-4">
      <div className="grid w-full max-w-5xl gap-0 border border-[rgba(255,255,255,0.12)] bg-[#090a0a] shadow-[0_32px_80px_oklch(0_0_0_/_0.5)]">
        <div className="flex items-start justify-between gap-4 border-b border-[rgba(255,255,255,0.06)] p-4 md:p-5">
          <div className="grid gap-2">
            <span className="label text-[#dce85d]">
              {mode === "agent" ? "Pacifica launch guide" : "Pacifica deploy guide"}
            </span>
            <h2 className="font-mono text-[clamp(1.25rem,3vw,2rem)] font-extrabold uppercase leading-[0.94] tracking-tight text-neutral-50">
              Pacifica setup before the bot goes live.
            </h2>
            <p className="max-w-2xl text-sm leading-5 text-neutral-400">
              Both checks are verified automatically before deploy is allowed.
            </p>
          </div>
          <button type="button" onClick={onClose} className="label transition hover:text-neutral-50">
            x
          </button>
        </div>

        <div className="grid gap-4 p-4 md:p-5">
          <div className="grid gap-3 xl:grid-cols-[1.4fr_1fr_1fr_1fr]">
            <article className="grid gap-2 rounded-[1.2rem] border border-[rgba(220,232,93,0.14)] bg-[rgba(220,232,93,0.06)] p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[0.58rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">launch state</span>
                <span className={`rounded-full px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${blocker ? "bg-[rgba(220,232,93,0.12)] text-[#dce85d]" : "bg-[rgba(116,185,127,0.18)] text-[#74b97f]"}`}>
                  {blocker ? "blocked" : "ready"}
                </span>
              </div>
              <div className="font-mono text-sm font-bold uppercase tracking-tight text-neutral-50">
                {blocker ?? "All Pacifica checks are verified."}
              </div>
              {resolvedWalletAddress ? <div className="truncate text-[0.7rem] text-neutral-500">{resolvedWalletAddress}</div> : null}
            </article>

            <article className="grid gap-1 rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] p-4">
              <span className="text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">SOL on devnet</span>
              <div className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">
                {resolvedReadiness ? `${formatSol(resolvedReadiness.metrics.sol_balance)} SOL` : "--"}
              </div>
              <p className="text-[0.7rem] leading-4 text-neutral-500">
                Need {resolvedReadiness ? `${formatSol(resolvedReadiness.metrics.min_sol_balance)} SOL` : "0.1 SOL"} minimum.
              </p>
            </article>

            <article className="grid gap-1 rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] p-4">
                <span className="text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Pacifica equity</span>
                <div className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">
                  {resolvedReadiness ? formatMetricUsd(resolvedReadiness.metrics.equity_usd) : "--"}
                </div>
                <p className="text-[0.7rem] leading-4 text-neutral-500">
                  Need {resolvedReadiness ? formatUsd(resolvedReadiness.metrics.min_equity_usd) : "$100"} minimum.
              </p>
            </article>

            <article className="grid gap-1 rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] p-4">
              <span className="text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Agent wallet</span>
              <div className={`font-mono text-xl font-bold uppercase tracking-tight ${agentStep?.verified ? "text-[#74b97f]" : "text-neutral-50"}`}>
                {resolvedReadiness ? resolvedReadiness.metrics.authorization_status : "inactive"}
              </div>
              <p className="text-[0.7rem] leading-4 text-neutral-500">
                {resolvedReadiness?.metrics.builder_code ? `Builder ${resolvedReadiness.metrics.builder_code}` : "Delegated signer required."}
              </p>
            </article>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {visibleSteps.map((step) => (
              <article key={step.id} className="grid gap-3 rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="grid gap-1.5">
                    <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
                      {step.id === "funding" ? "Step 1" : "Step 2"}
                    </span>
                    <h3 className="font-mono text-base font-bold uppercase tracking-tight text-neutral-50">{step.title}</h3>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${step.verified ? "bg-[rgba(116,185,127,0.18)] text-[#74b97f]" : "bg-[rgba(220,232,93,0.12)] text-[#dce85d]"}`}>
                    {step.verified ? "verified" : "not yet"}
                  </span>
                </div>

                <p className="text-sm leading-5 text-neutral-400">{step.detail}</p>

                {step.id === "funding" ? (
                  <div className="grid gap-2 rounded-[1rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a] p-3 text-xs leading-5 text-neutral-400">
                    <div>SOL: <span className="text-neutral-200">{resolvedReadiness ? `${formatSol(resolvedReadiness.metrics.sol_balance)} / ${formatSol(resolvedReadiness.metrics.min_sol_balance)} required` : "--"}</span></div>
                    <div>Equity: <span className="text-neutral-200">{resolvedReadiness ? `${formatMetricUsd(resolvedReadiness.metrics.equity_usd)} / ${formatUsd(resolvedReadiness.metrics.min_equity_usd)} required` : "--"}</span></div>
                    <div className="flex flex-wrap gap-2 pt-1">
                      <a
                        href="https://test-app.pacifica.fi/faucet"
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
                      >
                        Open faucet
                      </a>
                      <a
                        href="https://docs.pacifica.fi/testnet/how-to-start-trading/connect-and-fund-your-wallet"
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
                      >
                        Wallet guide
                      </a>
                    </div>
                  </div>
                ) : null}

                {step.id === "agent_authorization" ? (
                  <div className="grid gap-2 rounded-[1rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a] p-3 text-xs leading-5 text-neutral-400">
                    <div>Status: <span className="text-neutral-200">{resolvedReadiness?.metrics.authorization_status ?? "inactive"}</span></div>
                    <div className="break-all">Agent: <span className="text-neutral-200">{resolvedReadiness?.metrics.agent_wallet_address ?? "not bound yet"}</span></div>
                    <div className="flex flex-wrap gap-2 pt-1">
                      {!agentStep?.verified ? (
                        <button
                          type="button"
                          onClick={() => setAgentAuthorizationOpen((current) => !current)}
                          className="inline-flex items-center rounded-full bg-[#dce85d] px-3 py-1.5 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
                        >
                          {agentAuthorizationOpen ? "Hide authorization" : "Authorize ClashX Agent"}
                        </button>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-[rgba(116,185,127,0.16)] px-3 py-1.5 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">
                          Agent authorized
                        </span>
                      )}
                      {mode === "agent" ? (
                        <Link
                          href="/builder"
                          className="inline-flex items-center rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
                        >
                          Back to builder
                        </Link>
                      ) : null}
                    </div>
                    {agentAuthorizationOpen && !agentStep?.verified ? (
                      <AgentAuthorizationPanel
                        compact
                        walletAddressOverride={resolvedWalletAddress}
                        onAuthorized={() => {
                          setAgentAuthorizationOpen(false);
                          void refreshReadiness();
                        }}
                      />
                    ) : null}
                  </div>
                ) : null}
              </article>
            ))}
          </div>

          {!authenticated ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] px-3 py-3">
              <div className="grid gap-1">
                <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d]">Wallet required</span>
                <p className="text-sm leading-5 text-neutral-400">
                  Sign in first so ClashX can verify Pacifica readiness for the same wallet you&apos;ll deploy from.
                </p>
              </div>
              <button
                type="button"
                onClick={login}
                className="inline-flex items-center rounded-full bg-[#dce85d] px-3 py-1.5 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
              >
                Sign in
              </button>
            </div>
          ) : null}

          {error ? (
            <div className="rounded-[1rem] border border-[#dce85d]/30 bg-[rgba(220,232,93,0.08)] px-3 py-3 text-sm leading-5 text-neutral-200">
              {error}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
