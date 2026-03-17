"use client";

import { useEffect, useMemo, useState } from "react";

import { useClashxAuth } from "@/lib/clashx-auth";

type RuntimeRow = {
  runtime_id: string;
  bot_name: string;
  rank?: number;
};

type MirrorPreviewResponse = {
  source_runtime_id: string;
  source_bot_definition_id: string;
  source_bot_name: string;
  source_wallet_address: string;
  follower_wallet_address: string;
  mode: string;
  scale_bps: number;
  warnings: string[];
  mirrored_positions: Array<{
    symbol: string;
    side: string;
    size_source: number;
    size_mirrored: number;
    mark_price: number;
    notional_estimate: number;
  }>;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const fieldClassName =
  "rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3.5 py-3 text-sm text-neutral-50 outline-none transition placeholder:text-neutral-600 focus:border-[#dce85d]";

export function BotMirrorModal({
  runtime,
  open,
  onClose,
  onMirrored,
}: {
  runtime: RuntimeRow | null;
  open: boolean;
  onClose: () => void;
  onMirrored?: () => void;
}) {
  const { ready, authenticated, login, walletAddress: authenticatedWallet, getAuthHeaders } = useClashxAuth();
  const [walletAddress, setWalletAddress] = useState("");
  const [displayName, setDisplayName] = useState("Bot follower");
  const [scaleBps, setScaleBps] = useState(10_000);
  const [preview, setPreview] = useState<MirrorPreviewResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "confirming">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authenticatedWallet) {
      setWalletAddress(authenticatedWallet);
    }
  }, [authenticatedWallet]);

  useEffect(() => {
    if (!open || !runtime) {
      return;
    }

    if (!ready) {
      return;
    }

    const currentRuntime = runtime;
    if (!authenticated || !walletAddress) {
      setPreview(null);
      setError("Sign in with Privy and link your wallet before previewing a live follow.");
      return;
    }

    async function loadPreview() {
      setStatus("loading");
      setError(null);

      try {
        const response = await fetch(`${API_BASE_URL}/api/bot-copy/preview`, {
          method: "POST",
          headers: await getAuthHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            source_runtime_id: currentRuntime.runtime_id,
            follower_wallet_address: walletAddress.trim(),
            scale_bps: scaleBps,
          }),
        });
        const payload = (await response.json()) as MirrorPreviewResponse | { detail?: string };
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Mirror preview failed" : "Mirror preview failed");
        }
        setPreview(payload as MirrorPreviewResponse);
      } catch (previewError) {
        setPreview(null);
        setError(previewError instanceof Error ? previewError.message : "Mirror preview failed");
      } finally {
        setStatus("idle");
      }
    }

    void loadPreview();
  }, [authenticated, getAuthHeaders, open, ready, runtime, scaleBps, walletAddress]);

  const scaleLabel = useMemo(() => `${(scaleBps / 100).toFixed(0)}%`, [scaleBps]);

  if (!open || !runtime) {
    return null;
  }

  const activeRuntime = runtime;
  const canActivate = ready && authenticated && walletAddress.trim().length >= 8 && status !== "confirming" && preview !== null;

  async function activateMirror() {
    if (!authenticated) {
      login();
      return;
    }

    setStatus("confirming");
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/bot-copy/mirror`, {
        method: "POST",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          source_runtime_id: activeRuntime.runtime_id,
          follower_wallet_address: walletAddress.trim(),
          follower_display_name: displayName.trim() || undefined,
          scale_bps: scaleBps,
          risk_ack_version: "v1",
        }),
      });
      const payload = (await response.json()) as { detail?: string };
      if (!response.ok) {
        throw new Error(payload.detail ?? "Mirror activation failed");
      }
      onMirrored?.();
      onClose();
    } catch (activationError) {
      setError(activationError instanceof Error ? activationError.message : "Mirror activation failed");
    } finally {
      setStatus("idle");
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid overflow-y-auto bg-[color:var(--bg-overlay)] p-4 backdrop-blur-sm md:p-8">
      <div className="m-auto grid w-full max-w-3xl gap-0 rounded-[2rem] border border-[rgba(255,255,255,0.12)] bg-[#090a0a]">
        <div className="flex items-start justify-between gap-4 border-b border-[rgba(255,255,255,0.06)] p-6 md:p-8">
          <div className="grid gap-2">
            <span className="label text-[#dce85d]">Live follow</span>
            <h2 className="font-mono text-[clamp(1.6rem,4vw,2.8rem)] font-extrabold uppercase tracking-tight">
              Mirror {activeRuntime.bot_name}
            </h2>
            <p className="max-w-lg text-sm leading-6 text-neutral-400">Preview current mirrored exposure, then activate follow mode only if the live risk profile still makes sense to you.</p>
          </div>
          <button type="button" onClick={onClose} className="label transition hover:text-neutral-50" aria-label="Close mirror modal">
            x
          </button>
        </div>

        <div className="grid gap-6 p-6 md:p-8">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-1.5 text-sm text-neutral-400">
              Follower wallet
              <input
                value={walletAddress}
                onChange={(event) => setWalletAddress(event.target.value)}
                readOnly={Boolean(authenticatedWallet)}
                className={fieldClassName}
              />
            </label>
            <label className="grid gap-1.5 text-sm text-neutral-400">
              Display name
              <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} className={fieldClassName} />
            </label>
          </div>

          <label className="grid gap-2 text-sm text-neutral-400">
            Scale {scaleLabel}
            <input
              type="range"
              min={500}
              max={30000}
              step={500}
              value={scaleBps}
              onChange={(event) => setScaleBps(Number(event.target.value))}
              className="accent-[#dce85d]"
            />
          </label>

          {status === "loading" ? <p className="text-sm text-neutral-400">Building mirror packet...</p> : null}
          {error ? <p className="text-sm text-[#dce85d]">{error}</p> : null}

          <div className="grid gap-2">
            {(preview?.mirrored_positions ?? []).length > 0 ? (
              preview?.mirrored_positions.map((position, index) => (
                <article
                  key={`${position.symbol}-${index}`}
                  className="grid gap-2 rounded-[1.25rem] bg-[#16181a] px-4 py-3 md:grid-cols-[0.8fr_1fr_0.8fr] md:items-center"
                >
                  <div>
                    <div className="font-mono text-base font-bold uppercase tracking-tight text-neutral-50">{position.symbol}</div>
                    <div className="label text-[0.58rem]">{position.side}</div>
                  </div>
                  <div className="text-sm text-neutral-400">
                    {position.size_source.toFixed(3)} to {position.size_mirrored.toFixed(3)}
                  </div>
                  <div className="text-right text-sm text-neutral-400">Est. ${position.notional_estimate.toLocaleString()}</div>
                </article>
              ))
            ) : (
              <article className="rounded-[1.25rem] bg-[#16181a] px-4 py-4 text-sm leading-6 text-neutral-400">
                {status === "loading"
                  ? "Previewing live exposure..."
                  : "This runtime has no open positions right now, so activation would wait for the next source action."}
              </article>
            )}
          </div>

          <div className="grid gap-2 rounded-[1.5rem] bg-[#16181a] p-4 text-sm text-neutral-400">
            <span className="label text-[#dce85d]">Risk acknowledgement</span>
            {(preview?.warnings ?? []).map((warning) => (
              <p key={warning}>{warning}</p>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void activateMirror()}
              disabled={!canActivate}
              className="bg-[#dce85d] px-6 py-3 font-mono text-xs font-semibold uppercase tracking-wider text-[#090a0a] transition hover:bg-[#e8f06d] disabled:opacity-50"
            >
              {status === "confirming" ? "Activating follow..." : "Activate follow"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-6 py-3 font-mono text-xs font-semibold uppercase tracking-wider text-neutral-400 transition hover:border-neutral-50 hover:text-neutral-50"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
