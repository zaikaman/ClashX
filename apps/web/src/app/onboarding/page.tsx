"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  LoaderCircle,
  RefreshCw,
} from "lucide-react";

import { ClashXLogo } from "@/components/clashx-logo";
import { PrivyAuthButton } from "@/components/auth/privy-auth-button";
import { AgentAuthorizationPanel } from "@/components/pacifica/agent-authorization-panel";
import { useClashxAuth } from "@/lib/clashx-auth";
import { hasCompletedOnboardingForWallet, writeStoredOnboardingState } from "@/lib/onboarding-state";
import {
  fetchPacificaReadiness,
  type PacificaReadinessPayload,
} from "@/lib/pacifica-readiness";

type ReadinessStatus = "idle" | "loading" | "error";

function formatSol(value: number) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 3,
  }).format(value);
}

function formatUsd(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value >= 100 ? 0 : 2,
    maximumFractionDigits: value >= 100 ? 0 : 2,
  }).format(value);
}

function formatMetricUsd(value: number | null) {
  return value === null ? "--" : formatUsd(value);
}

function extractAgentAuthorized(readiness: PacificaReadinessPayload | null) {
  return Boolean(readiness?.steps.find((step) => step.id === "agent_authorization")?.verified);
}

function ExternalAction({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-sm font-medium text-[#dce85d] hover:text-[#f0f5a6] underline underline-offset-4 decoration-[#dce85d]/30 transition"
    >
      {label}
    </a>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const { ready, authenticated, walletAddress, getAuthHeaders, logout } = useClashxAuth();
  const [readiness, setReadiness] = useState<PacificaReadinessPayload | null>(null);
  const [status, setStatus] = useState<ReadinessStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const connected = ready && authenticated && Boolean(walletAddress);
  const resolvedReadiness = connected ? readiness : null;
  const resolvedStatus = connected ? status : "idle";
  const resolvedError = connected ? error : null;

  const solReady = Boolean(
    resolvedReadiness && resolvedReadiness.metrics.sol_balance >= resolvedReadiness.metrics.min_sol_balance,
  );
  const equityReady = Boolean(
    resolvedReadiness &&
      resolvedReadiness.metrics.equity_usd !== null &&
      resolvedReadiness.metrics.equity_usd >= resolvedReadiness.metrics.min_equity_usd,
  );
  const agentReady = extractAgentAuthorized(resolvedReadiness);
  const launchReady = connected && solReady && equityReady && agentReady;
  const currentStep = !connected ? 1 : !solReady ? 2 : !equityReady ? 3 : !agentReady ? 4 : 5;

  const refreshReadiness = useCallback(async () => {
    if (!authenticated || !walletAddress) {
      return;
    }

    setStatus("loading");
    setError(null);
    try {
      const payload = await fetchPacificaReadiness(walletAddress, getAuthHeaders);
      setReadiness(payload);
      setStatus("idle");
    } catch (refreshError) {
      setStatus("error");
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : "Unable to verify Pacifica readiness right now.",
      );
    }
  }, [authenticated, getAuthHeaders, walletAddress]);

  useEffect(() => {
    if (!authenticated || !walletAddress) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      void refreshReadiness();
    }, 0);
    const intervalId = window.setInterval(() => {
      void refreshReadiness();
    }, 8000);

    return () => {
      window.clearTimeout(timeoutId);
      window.clearInterval(intervalId);
    };
  }, [authenticated, refreshReadiness, walletAddress]);

  useEffect(() => {
    if (!launchReady || !walletAddress) {
      return;
    }
    writeStoredOnboardingState(walletAddress);
  }, [launchReady, walletAddress]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-sm text-neutral-500 font-medium">
        <LoaderCircle className="h-4 w-4 animate-spin mr-2" />
        Loading...
      </div>
    );
  }

  return (
    <main className="flex min-h-screen flex-col bg-zinc-950 text-neutral-50 selection:bg-[#dce85d]/30">
      <header className="flex h-16 items-center justify-between px-6 sm:px-8">
        <Link href="/" className="inline-flex items-center gap-3 opacity-80 hover:opacity-100 transition">
          <ClashXLogo className="h-5 w-5 text-neutral-50" />
          <span className="text-sm font-semibold tracking-tight">ClashX</span>
        </Link>
        <div className="flex items-center gap-6">
          {connected && currentStep < 5 && (
            <button
              onClick={() => void logout()}
              className="text-xs font-semibold text-neutral-400 hover:text-white transition tracking-wide"
            >
              Disconnect Wallet
            </button>
          )}
          {currentStep < 5 ? (
            <div className="text-xs font-semibold text-neutral-500 uppercase tracking-widest">
              Step {currentStep} / 4
            </div>
          ) : null}
        </div>
      </header>

      <div className="flex-1 flex flex-col justify-center px-6 sm:px-8 py-12">
        <div className="mx-auto w-full max-w-md">
          {currentStep === 1 && (
            <div className="grid gap-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out-quart">
              <div className="grid gap-3">
                <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight">Connect your wallet</h1>
                <p className="text-base text-neutral-400 leading-relaxed">
                  Use the same Solana wallet for sign-in, Pacifica funding, and agent authorization.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4 flex justify-center">
                <PrivyAuthButton />
              </div>
            </div>
          )}

          {currentStep === 2 && (
            <div className="grid gap-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out-quart">
              <div className="grid gap-3">
                <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight">Add devnet SOL</h1>
                <p className="text-base text-neutral-400 leading-relaxed">
                  We need a confirmed devnet balance before the trading interface opens.
                </p>
              </div>

              <div className="grid gap-5 rounded-2xl border border-white/10 bg-white/[0.02] p-6">
                <div className="flex justify-between items-baseline">
                  <div>
                    <div className="text-sm text-neutral-500 mb-1 font-medium">Current Balance</div>
                    <div className="text-3xl font-semibold tracking-tight">
                      {resolvedReadiness ? `${formatSol(resolvedReadiness.metrics.sol_balance)} SOL` : "--"}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-neutral-500 mb-1 font-medium">Required</div>
                    <div className="text-base font-semibold text-neutral-300">
                      0.1 SOL
                    </div>
                  </div>
                </div>

                <div className="h-px bg-white/10 w-full" />

                <div className="flex items-center justify-between">
                  <ExternalAction href="https://faucet.solana.com" label="Solana Faucet" />
                  <button
                    onClick={() => void refreshReadiness()}
                    disabled={resolvedStatus === "loading"}
                    className="text-sm font-medium text-neutral-400 hover:text-white transition disabled:opacity-50 inline-flex items-center gap-2"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${resolvedStatus === "loading" ? "animate-spin" : ""}`} />
                    Refresh
                  </button>
                </div>
              </div>
            </div>
          )}

          {currentStep === 3 && (
            <div className="grid gap-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out-quart">
              <div className="grid gap-3">
                <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight">Reach $100 Pacifica equity</h1>
                <div className="space-y-4">
                  <p className="text-base text-neutral-400 leading-relaxed">
                    ClashX uses the Pacifica protocol as its underlying trading engine. To enable automated trading, you need to fund your Pacifica account on devnet.
                  </p>
                  <ol className="list-decimal list-outside ml-4 text-sm text-neutral-400 space-y-2 marker:text-neutral-500">
                    <li>Go to the <strong className="text-neutral-200">Pacifica Faucet</strong> and mint test USDP tokens.</li>
                    <li>Navigate to the <strong className="text-neutral-200">Portfolio</strong> tab and deposit at least $100 USDP.</li>
                    <li>Return here and click refresh.</li>
                  </ol>
                </div>
              </div>

              <div className="grid gap-5 rounded-2xl border border-white/10 bg-white/[0.02] p-6">
                <div className="flex justify-between items-baseline">
                  <div>
                    <div className="text-sm text-neutral-500 mb-1 font-medium">Current Equity</div>
                    <div className="text-3xl font-semibold tracking-tight">
                      {resolvedReadiness ? formatMetricUsd(resolvedReadiness.metrics.equity_usd) : "--"}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-neutral-500 mb-1 font-medium">Required</div>
                    <div className="text-base font-semibold text-neutral-300">
                      $100.00
                    </div>
                  </div>
                </div>

                <div className="h-px bg-white/10 w-full" />

                <div className="flex items-center justify-between">
                  <div className="flex flex-col gap-1.5 sm:flex-row sm:gap-4">
                    <ExternalAction href="https://test-app.pacifica.fi/faucet" label="1. Mint USDP" />
                    <ExternalAction href="https://test-app.pacifica.fi/portfolio" label="2. Deposit" />
                  </div>
                  <button
                    onClick={() => void refreshReadiness()}
                    disabled={resolvedStatus === "loading"}
                    className="text-sm font-medium text-neutral-400 hover:text-white transition disabled:opacity-50 inline-flex items-center gap-2 self-end sm:self-auto"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${resolvedStatus === "loading" ? "animate-spin" : ""}`} />
                    Refresh
                  </button>
                </div>
              </div>
            </div>
          )}

          {currentStep === 4 && (
            <div className="grid gap-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out-quart">
              <div className="grid gap-3">
                <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight">Authorize agent signer</h1>
                <p className="text-base text-neutral-400 leading-relaxed">
                  Bind the delegated agent wallet so ClashX can execute trades autonomously.
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
                <AgentAuthorizationPanel
                  compact
                  walletAddressOverride={walletAddress}
                  onAuthorized={() => void refreshReadiness()}
                />
              </div>
            </div>
          )}

          {currentStep === 5 && (
            <div className="grid gap-8 text-center animate-in fade-in zoom-in-95 duration-700 ease-out-quart place-items-center">
              <div className="grid h-16 w-16 place-items-center rounded-full bg-[#74b97f]/20 text-[#74b97f] mb-2">
                <CheckCircle2 className="h-8 w-8" />
              </div>
              <div className="grid gap-3">
                <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight">You&apos;re all set.</h1>
                <p className="text-base text-neutral-400 leading-relaxed max-w-[320px] mx-auto">
                  Dashboard access is unlocked, and your setup is securely cached for the next session.
                </p>
              </div>
              <button
                type="button"
                onClick={() => router.push("/dashboard")}
                className="mt-6 inline-flex items-center justify-center gap-2 rounded-full bg-white px-8 py-3.5 text-sm font-semibold text-black transition hover:scale-105 active:scale-95"
              >
                Go to Dashboard
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          )}

          {resolvedError && currentStep < 5 && (
            <div className="mt-6 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {resolvedError}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
