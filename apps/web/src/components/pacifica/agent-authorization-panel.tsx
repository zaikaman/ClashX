"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { encodeBase58 } from "@/lib/base58";
import { useClashxAuth } from "@/lib/clashx-auth";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const PROVIDER_POLL_VISIBLE_MS = 4_000;
const PROVIDER_POLL_HIDDEN_MS = 15_000;

type SigningDraft = {
  type: string;
  message: string | null;
  request_payload: Record<string, unknown>;
};

type AuthorizationResponse = {
  id: string;
  user_id: string;
  wallet_address: string;
  account_address: string;
  agent_wallet_address: string;
  status: string;
  builder_code: string | null;
  max_fee_rate: string | null;
  builder_approval_required: boolean;
  builder_approved_at: string | null;
  agent_bound_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  builder_approval_draft: SigningDraft | null;
  bind_agent_draft: SigningDraft | null;
};

type SolanaProvider = {
  connect: (options?: { onlyIfTrusted?: boolean }) => Promise<{ publicKey: { toString(): string } }>;
  signMessage: (message: Uint8Array, display?: "utf8") => Promise<{ publicKey: { toString(): string }; signature: Uint8Array }>;
  publicKey?: { toString(): string };
  isPhantom?: boolean;
  isSolflare?: boolean;
  isBackpack?: boolean;
};

declare global {
  interface Window {
    solana?: SolanaProvider;
    phantom?: { solana?: SolanaProvider };
    solflare?: SolanaProvider;
    backpack?: { solana?: SolanaProvider };
  }
}

function getProvider(): SolanaProvider | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.phantom?.solana ?? window.backpack?.solana ?? window.solflare ?? window.solana ?? null;
}

function getProviderLabel(provider: SolanaProvider | null): string {
  if (!provider) {
    return "No browser Solana signer";
  }
  if (provider.isPhantom) {
    return "Phantom detected";
  }
  if (provider.isSolflare) {
    return "Solflare detected";
  }
  if (provider.isBackpack) {
    return "Backpack detected";
  }
  return "Injected Solana signer detected";
}

export function AgentAuthorizationPanel() {
  const { authenticated, login, walletAddress: authenticatedWallet, getAuthHeaders } = useClashxAuth();
  const [walletAddress, setWalletAddress] = useState("");
  const [displayName, setDisplayName] = useState("Capital Pilot");
  const [authorization, setAuthorization] = useState<AuthorizationResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "connecting" | "loading" | "signing" | "activating" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [connectedWallet, setConnectedWallet] = useState<string | null>(null);
  const [providerLabel, setProviderLabel] = useState("Checking browser signer");

  const refreshAuthorization = useCallback(async () => {
    if (!authenticated || !walletAddress) {
      setAuthorization(null);
      return;
    }

    const response = await fetch(`${API_BASE_URL}/api/pacifica/authorize?wallet_address=${encodeURIComponent(walletAddress)}`, {
      cache: "no-store",
      headers: await getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Unable to load agent wallet status");
    }
    const payload = (await response.json()) as AuthorizationResponse | null;
    setAuthorization(payload);
  }, [authenticated, getAuthHeaders, walletAddress]);

  useEffect(() => {
    if (authenticatedWallet) {
      setWalletAddress(authenticatedWallet);
    }
  }, [authenticatedWallet]);

  useEffect(() => {
    const refreshProviderState = () => {
      const provider = getProvider();
      setProviderLabel(getProviderLabel(provider));
      setConnectedWallet(provider?.publicKey?.toString() ?? null);
    };

    let intervalId = 0;
    const startPolling = () => {
      window.clearInterval(intervalId);
      const pollMs = document.visibilityState === "visible" ? PROVIDER_POLL_VISIBLE_MS : PROVIDER_POLL_HIDDEN_MS;
      intervalId = window.setInterval(refreshProviderState, pollMs);
    };

    refreshProviderState();
    startPolling();
    window.addEventListener("focus", refreshProviderState);
    window.addEventListener("online", refreshProviderState);
    document.addEventListener("visibilitychange", startPolling);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", refreshProviderState);
      window.removeEventListener("online", refreshProviderState);
      document.removeEventListener("visibilitychange", startPolling);
    };
  }, []);

  useEffect(() => {
    if (!authenticated || !walletAddress) {
      setAuthorization(null);
      return;
    }

    const timeout = window.setTimeout(async () => {
      try {
        await refreshAuthorization();
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load agent wallet status");
      }
    }, 250);

    return () => window.clearTimeout(timeout);
  }, [authenticated, refreshAuthorization, walletAddress]);

  const runtimeReady = authorization?.status === "active";
  const signingWalletMatches = !authenticatedWallet || !connectedWallet || authenticatedWallet === connectedWallet;
  const needsBrowserSigner = authenticated && !runtimeReady && !getProvider();

  async function connectWallet() {
    if (!authenticated) {
      login();
      setError("Sign in with Privy before connecting the signing wallet.");
      setStatus("error");
      return;
    }
    const provider = getProvider();
    if (!provider) {
      setError("Install a Solana wallet like Phantom or Solflare to authorize delegated bot execution.");
      setStatus("error");
      return;
    }

    setStatus("connecting");
    setError(null);
    try {
      const result = await provider.connect();
      const address = result.publicKey.toString();
      if (authenticatedWallet && authenticatedWallet !== address) {
        throw new Error("The connected signing wallet must match the wallet linked to your Privy account.");
      }
      setConnectedWallet(address);
      setWalletAddress(address);
      setStatus("idle");
    } catch (connectError) {
      setStatus("error");
      setError(connectError instanceof Error ? connectError.message : "Wallet connection failed");
    }
  }

  async function signDraft(provider: SolanaProvider, draft: SigningDraft | null) {
    if (!draft?.message) {
      return null;
    }
    const encodedMessage = new TextEncoder().encode(draft.message);
    let signed;
    try {
      signed = await provider.signMessage(encodedMessage, "utf8");
    } catch {
      signed = await provider.signMessage(encodedMessage);
    }
    const signerAddress = signed.publicKey.toString();
    if (walletAddress && signerAddress !== walletAddress) {
      throw new Error("The wallet that signed the authorization message does not match the Pacifica account wallet.");
    }
    return encodeBase58(signed.signature);
  }

  async function authorizeWallet() {
    if (!authenticated) {
      login();
      setError("Sign in with Privy before authorizing the bot runtime wallet.");
      setStatus("error");
      return;
    }
    const provider = getProvider();
    if (!provider) {
      setError("Install a Solana wallet like Phantom or Solflare to authorize delegated bot execution.");
      setStatus("error");
      return;
    }
    if (!walletAddress) {
      setError("Connect a wallet first.");
      setStatus("error");
      return;
    }

    setStatus("loading");
    setError(null);
    try {
      const requestAuthorizationDraft = async (forceReissue: boolean) => {
        const startResponse = await fetch(`${API_BASE_URL}/api/pacifica/authorize/start`, {
          method: "POST",
          headers: await getAuthHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ wallet_address: walletAddress, display_name: displayName, force_reissue: forceReissue }),
        });
        const startPayload = (await startResponse.json()) as AuthorizationResponse | { detail?: string };
        if (!startResponse.ok) {
          throw new Error("detail" in startPayload ? startPayload.detail ?? "Authorization start failed" : "Authorization start failed");
        }
        return startPayload as AuthorizationResponse;
      };

      let draft = await requestAuthorizationDraft(runtimeReady);
      if (!draft.bind_agent_draft?.message) {
        draft = await requestAuthorizationDraft(true);
      }

      setAuthorization(draft);
      setStatus("signing");

      const builderApprovalSignature = await signDraft(provider, draft.builder_approval_draft);
      const bindAgentSignature = await signDraft(provider, draft.bind_agent_draft);
      if (!bindAgentSignature) {
        throw new Error("Unable to create a fresh agent bind draft. Reload the Agent Desk and try re-arming again.");
      }

      setStatus("activating");
      const activateResponse = await fetch(`${API_BASE_URL}/api/pacifica/authorize/${draft.id}/activate`, {
        method: "POST",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          builder_approval_signature: builderApprovalSignature,
          bind_agent_signature: bindAgentSignature,
        }),
      });
      const activatePayload = (await activateResponse.json()) as AuthorizationResponse | { detail?: string };
      if (!activateResponse.ok) {
        throw new Error("detail" in activatePayload ? activatePayload.detail ?? "Authorization activation failed" : "Authorization activation failed");
      }
      setAuthorization(activatePayload as AuthorizationResponse);
      setStatus("idle");
    } catch (authorizeError) {
      setStatus("error");
      setError(authorizeError instanceof Error ? authorizeError.message : "Authorization failed");
      try {
        await refreshAuthorization();
      } catch {
        // Ignore refresh errors; the primary authorization error is already surfaced.
      }
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_1fr]">
      {/* Left panel — form */}
      <section className="grid gap-6 border-l-2 border-[#dce85d] bg-[#16181a] p-6 md:p-8">
        <div className="grid gap-3 border-b border-[rgba(255,255,255,0.06)] pb-5">
          <span className="label text-[#dce85d]">delegated bot runtime desk</span>
          <h2 className="font-mono text-[clamp(1.8rem,4vw,3.4rem)] font-extrabold uppercase leading-[0.92] tracking-tight">
            Arm your Pacifica bot runtime.
          </h2>
          <p className="max-w-xl text-sm leading-7 text-neutral-400">
            ClashX generates a dedicated agent wallet for your account. Your connected Solana wallet signs locally so bot execution can run without manual order entry.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="bg-neutral-900 px-4 py-3">
            <div className="label text-[0.58rem]">provider</div>
            <div className="mt-1.5 font-mono text-base font-bold uppercase tracking-tight">{providerLabel}</div>
          </div>
          <div className="bg-neutral-900 px-4 py-3">
            <div className="label text-[0.58rem]">runtime status</div>
            <div className={`mt-1.5 font-mono text-base font-bold uppercase tracking-tight ${runtimeReady ? "text-[#74b97f]" : ""}`}>
              {runtimeReady ? "active" : authorization?.status ?? "not armed"}
            </div>
          </div>
        </div>

        <div className="grid gap-4">
          <label className="grid gap-1.5 text-sm text-neutral-400">
            Runtime wallet
            <input
              value={walletAddress}
              onChange={(event) => setWalletAddress(event.target.value)}
              readOnly={Boolean(authenticatedWallet)}
              className="border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
            />
          </label>
          <label className="grid gap-1.5 text-sm text-neutral-400">
            Bot alias
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              className="border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
            />
          </label>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={connectWallet}
            disabled={status === "connecting"}
            className="inline-flex items-center justify-center rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-2.5 font-mono text-xs font-semibold uppercase tracking-wider text-neutral-400 transition-all duration-200 hover:border-neutral-50 hover:text-neutral-50"
          >
            {status === "connecting" ? <><span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full spinner-reverse mr-2 align-middle"></span>connecting</> : connectedWallet ? "wallet connected ✓" : "connect wallet"}
          </button>
          <button
            type="button"
            onClick={authorizeWallet}
            disabled={status === "loading" || status === "signing" || status === "activating" || !walletAddress || !authenticated || !connectedWallet || !signingWalletMatches}
            className="inline-flex items-center justify-center bg-[#dce85d] px-5 py-2.5 font-mono text-xs font-semibold uppercase tracking-wider text-[#090a0a] transition-all duration-200 hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {status === "loading" || status === "signing" || status === "activating" ? <><span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full spinner-reverse mr-2 align-middle"></span>arming runtime</>
              : runtimeReady
                ? "re-arm runtime"
                : "authorize runtime"}
          </button>
        </div>

        {error ? <p className="text-sm text-[#dce85d]">{error}</p> : null}
        {connectedWallet ? <p className="text-xs text-neutral-500">Connected: {connectedWallet}</p> : null}
        {!signingWalletMatches && authenticatedWallet ? (
          <p className="text-sm text-[#dce85d]">
            Your browser signer does not match the Privy-linked wallet. Link and connect the same external Solana wallet in both places.
          </p>
        ) : null}
        {needsBrowserSigner && authenticatedWallet ? (
          <p className="text-sm text-neutral-400">
            Privy authenticated your wallet, but runtime authorization still needs a browser Solana signer extension for local message signing.
          </p>
        ) : null}
        {runtimeReady ? (
          <p className="text-sm text-neutral-400">
            If Pacifica says the signer is unauthorized, use <span className="font-semibold text-neutral-50">re-arm runtime</span> to generate and bind a fresh delegated signer.
          </p>
        ) : null}
        {runtimeReady ? (
          <Link
            href="/builder"
            className="inline-flex items-center gap-2 bg-[#74b97f] px-5 py-2.5 font-mono text-xs font-semibold uppercase tracking-wider text-[#090a0a] transition-all duration-200 hover:brightness-110"
          >
            go to builder <span>→</span>
          </Link>
        ) : null}
      </section>

      {/* Right panel — manifest */}
      <section className="grid gap-5 border-l-2 border-[color:var(--mint-dim)] bg-[#16181a] p-6 md:p-8">
        <div className="grid gap-2 border-b border-[rgba(255,255,255,0.06)] pb-5">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">runtime manifest</span>
          <div className="font-mono text-xl font-extrabold uppercase tracking-tight break-all">
            {authorization?.agent_wallet_address ? authorization.agent_wallet_address : "No agent wallet staged yet"}
          </div>
        </div>

        {/* Steps timeline */}
        <div className="grid gap-0">
          {[
            { step: 1, title: "builder approval", desc: "Your connected wallet signs the offchain authorization messages locally. ClashX only receives the resulting signatures." },
            { step: 2, title: "runtime binding", desc: "Pacifica binds your dedicated agent wallet to your account for future bot execution." },
            { step: 3, title: "copy-ready automation", desc: "Once active, bot copying and delegated actions gate against this record instead of a raw key." },
          ].map((item) => (
            <div key={item.step} className="relative grid gap-2 border-l-2 border-[rgba(255,255,255,0.06)] py-4 pl-6">
              <div className="absolute -left-[7px] top-5 h-3 w-3 rounded-full bg-neutral-900 border-2 border-[rgba(255,255,255,0.12)]" />
              <div className="label text-[0.58rem]">step {item.step}</div>
              <div className="font-mono text-base font-bold uppercase tracking-tight">{item.title}</div>
              <p className="text-sm leading-6 text-neutral-400">{item.desc}</p>
            </div>
          ))}
        </div>

        {/* Current status */}
        <div className="grid gap-2 border-t border-[rgba(255,255,255,0.06)] pt-5 text-sm text-neutral-400">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">current runtime dossier</span>
          <div>Status: <span className="font-semibold text-neutral-50">{authorization?.status ?? "not started"}</span></div>
          <div>Builder code: <span className="font-semibold text-neutral-50">{authorization?.builder_code ?? "not configured"}</span></div>
          <div>Builder approval: <span className="font-semibold text-neutral-50">{authorization?.builder_approved_at ? "complete" : authorization?.builder_approval_required ? "pending" : "not required"}</span></div>
          <div>Agent bind: <span className="font-semibold text-neutral-50">{authorization?.agent_bound_at ? "complete" : "pending"}</span></div>
          <div>Signing wallet match: <span className="font-semibold text-neutral-50">{signingWalletMatches ? "verified" : "mismatch"}</span></div>
          {authorization?.last_error ? <div className="text-[#dce85d]">Error: {authorization.last_error}</div> : null}
        </div>
      </section>
    </div>
  );
}
