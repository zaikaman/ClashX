"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useClashxAuth } from "@/lib/clashx-auth";

type BotRuntime = {
  user_id: string;
  display_name: string;
  wallet_address: string;
  rank: number;
  unrealized_pnl: number;
  realized_pnl: number;
  win_streak: number;
};

type PreviewResponse = {
  source_user_id: string;
  source_display_name: string;
  source_wallet_address: string;
  follower_wallet_address: string;
  scale_bps: number;
  warnings: string[];
  confirmation_phrase: string;
  source_rank: number | null;
  source_win_streak: number;
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

export function RiskWarningModal({
  bot,
  open,
  onClose,
  onConfirmed,
}: {
  bot: BotRuntime | null;
  open: boolean;
  onClose: () => void;
  onConfirmed?: () => void;
}) {
  const { authenticated, login, walletAddress: authenticatedWallet, getAuthHeaders } = useClashxAuth();
  const [walletAddress, setWalletAddress] = useState("");
  const [displayName, setDisplayName] = useState("Velvet Copier");
  const [scaleBps, setScaleBps] = useState(10_000);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [confirmationText, setConfirmationText] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "confirming" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authenticatedWallet) {
      setWalletAddress(authenticatedWallet);
    }
  }, [authenticatedWallet]);

  useEffect(() => {
    if (!open || !bot) {
      return;
    }
    if (!authenticated || !walletAddress) {
      setPreview(null);
      setError("Sign in with Privy and link the runtime wallet before previewing a bot copy.");
      return;
    }
    const previewBot = bot;

    async function loadPreview() {
      setStatus("loading");
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/api/copy/preview`, {
          method: "POST",
          headers: await getAuthHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            source_user_id: previewBot.user_id,
            follower_wallet_address: walletAddress,
            scale_bps: scaleBps,
          }),
        });
        const payload = (await response.json()) as PreviewResponse | { detail?: string };
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Preview failed" : "Preview failed");
        }
        setPreview(payload as PreviewResponse);
        setStatus("idle");
      } catch (loadError) {
        setStatus("error");
        setError(loadError instanceof Error ? loadError.message : "Preview failed");
      }
    }

    void loadPreview();
  }, [authenticated, getAuthHeaders, open, bot, walletAddress, scaleBps]);

  const scaleLabel = useMemo(() => `${(scaleBps / 100).toFixed(0)}%`, [scaleBps]);

  if (!open || !bot) {
    return null;
  }

  const activeBot = bot;

  async function confirmCopy() {
    if (!preview) {
      return;
    }
    if (!authenticated) {
      login();
      setStatus("error");
      setError("Sign in with Privy before activating bot copy.");
      return;
    }
    setStatus("confirming");
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/copy/confirm`, {
        method: "POST",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          source_user_id: activeBot.user_id,
          follower_wallet_address: walletAddress,
          follower_display_name: displayName,
          scale_bps: scaleBps,
          risk_ack_version: "v1",
          confirmation_phrase: confirmationText,
        }),
      });
      const payload = (await response.json()) as { detail?: string };
      if (!response.ok) {
        throw new Error(payload.detail ?? "Activation failed");
      }
      onConfirmed?.();
      onClose();
      setConfirmationText("");
      setStatus("idle");
    } catch (confirmError) {
      setStatus("error");
      setError(confirmError instanceof Error ? confirmError.message : "Activation failed");
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid overflow-y-auto bg-[color:var(--bg-overlay)] p-4 backdrop-blur-sm md:p-8">
      <div className="m-auto grid w-full max-w-3xl gap-0 border border-[rgba(255,255,255,0.12)] bg-[#090a0a] shadow-[0_32px_80px_oklch(0_0_0_/_0.5)]">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-[rgba(255,255,255,0.06)] p-6 md:p-8">
          <div className="grid gap-2">
            <span className="label text-[#dce85d]">bot copy consent</span>
            <h2 className="font-mono text-[clamp(1.6rem,4vw,2.8rem)] font-extrabold uppercase leading-[0.92] tracking-tight">
              Mirror bot {activeBot.display_name}
            </h2>
            <p className="max-w-lg text-sm leading-6 text-neutral-400">
              Live Pacifica bot relationship. You are approving automatic strategy mirroring at your chosen scale.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="label transition hover:text-neutral-50"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="grid gap-6 p-6 md:p-8">
          {/* Form fields */}
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-1.5 text-sm text-neutral-400">
              Copier wallet
              <input
                value={walletAddress}
                onChange={(event) => setWalletAddress(event.target.value)}
                readOnly={Boolean(authenticatedWallet)}
                className="border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
              />
            </label>
            <label className="grid gap-1.5 text-sm text-neutral-400">
              Copier alias
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                className="border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
              />
            </label>
          </div>

          <label className="grid gap-2 text-sm text-neutral-400">
            Scale {scaleLabel}
            <input
              type="range"
              min={500}
              max={25000}
              step={500}
              value={scaleBps}
              onChange={(event) => setScaleBps(Number(event.target.value))}
              className="accent-[#dce85d]"
            />
          </label>

          {/* Rank info */}
          <div className="flex items-baseline gap-4">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">preview</span>
            <span className="font-mono text-lg font-bold uppercase tracking-tight">
              Rank {preview?.source_rank ?? activeBot.rank} · streak {preview?.source_win_streak ?? activeBot.win_streak}
            </span>
          </div>

          {status === "loading" ? <p className="text-sm text-neutral-400">Building mirrored packet…</p> : null}
          {error ? <p className="text-sm text-[#dce85d]">{error}</p> : null}

          {/* Positions */}
          <div className="grid gap-1.5">
            {preview?.mirrored_positions.map((position) => (
              <div
                key={position.symbol}
                className="grid gap-2 bg-[#16181a] px-4 py-3 md:grid-cols-[0.6fr_1fr_0.6fr] md:items-center"
              >
                <div>
                  <div className="font-mono text-base font-bold uppercase tracking-tight">{position.symbol}</div>
                  <div className="label text-[0.58rem]">{position.side}</div>
                </div>
                <div className="text-sm text-neutral-400">
                  {position.size_source.toFixed(3)} → {position.size_mirrored.toFixed(3)}
                </div>
                <div className="text-right text-sm text-neutral-400">
                  est. ${position.notional_estimate.toLocaleString()}
                </div>
              </div>
            ))}
          </div>

          {/* Warnings */}
          <div className="grid gap-2 text-sm text-neutral-400">
            <span className="label text-[#dce85d]">risk acknowledgement</span>
            <p>
              Bot copy requires an active delegated Pacifica runtime wallet. Set it up in{" "}
              <Link href="/agent" className="text-neutral-50 underline decoration-[color:var(--line)] underline-offset-4 transition hover:text-[#dce85d]">
                Runtime Desk
              </Link>{" "}
              before arming copy.
            </p>
            {preview?.warnings.map((warning) => <p key={warning} className="text-[#dce85d]">{warning}</p>)}
          </div>

          {/* Confirmation */}
          <label className="grid gap-2 text-sm text-neutral-400">
            Type <span className="font-mono text-sm font-bold uppercase tracking-wider text-[#dce85d]">{preview?.confirmation_phrase ?? "..."}</span>
            <input
              value={confirmationText}
              onChange={(event) => setConfirmationText(event.target.value)}
              className="border border-[rgba(255,255,255,0.12)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
            />
          </label>

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={confirmCopy}
              disabled={status === "confirming" || !preview || !authenticated}
              className="inline-flex items-center justify-center bg-[#dce85d] px-6 py-3 font-mono text-sm font-semibold uppercase tracking-wider text-[#090a0a] transition-all duration-200 hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {status === "confirming" ? "arming bot copy" : "activate bot copy"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex items-center justify-center rounded-full border border-[rgba(255,255,255,0.12)] px-6 py-3 font-mono text-sm font-semibold uppercase tracking-wider text-neutral-400 transition-all duration-200 hover:border-neutral-50 hover:text-neutral-50"
            >
              back out
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
