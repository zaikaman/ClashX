"use client";

import type { ChangeEvent } from "react";
import { useEffect, useState } from "react";

import { useClashxAuth } from "@/lib/clashx-auth";

export function JoinButton({
  leagueId,
  disabled,
  onJoined,
}: {
  leagueId: string;
  disabled?: boolean;
  onJoined?: () => void;
}) {
  const { authenticated, login, walletAddress: authenticatedWallet, getAuthHeaders } = useClashxAuth();
  const [walletAddress, setWalletAddress] = useState("");
  const [displayName, setDisplayName] = useState("Velvet Signal");
  const [status, setStatus] = useState<"idle" | "pending" | "joined" | "error">("idle");
  const [message, setMessage] = useState("One tap registers your bot on the live split.");

  useEffect(() => {
    if (authenticatedWallet) {
      setWalletAddress(authenticatedWallet);
    }
  }, [authenticatedWallet]);

  async function registerBot() {
    if (disabled || status === "pending") {
      return;
    }
    if (!authenticated) {
      login();
      setStatus("error");
      setMessage("Sign in with Privy before registering a bot.");
      return;
    }
    setStatus("pending");
    setMessage("Registering bot…");

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/leagues/${leagueId}/register-bot`, {
        method: "POST",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ wallet_address: walletAddress, display_name: displayName }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(payload.detail ?? "Could not register bot in competition.");
      }

      setStatus("joined");
      setMessage("Your bot is on the board. Keep the streak alive.");
      onJoined?.();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Registration failed");
    }
  }

  return (
    <div className="grid gap-3 bg-[#16181a] p-5">
      <label className="grid gap-1.5 text-sm text-neutral-400">
        Runtime wallet
        <input
          value={walletAddress}
          onChange={(event: ChangeEvent<HTMLInputElement>) => setWalletAddress(event.target.value)}
          readOnly={Boolean(authenticatedWallet)}
          className="border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
        />
      </label>
      <label className="grid gap-1.5 text-sm text-neutral-400">
        Bot name
        <input
          value={displayName}
          onChange={(event: ChangeEvent<HTMLInputElement>) => setDisplayName(event.target.value)}
          className="border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
        />
      </label>
      <button
        type="button"
        onClick={registerBot}
        disabled={disabled || status === "pending"}
        className="inline-flex items-center justify-center bg-[#dce85d] px-5 py-3 font-mono text-sm font-semibold uppercase tracking-wider text-[#090a0a] transition-all duration-200 hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {status === "pending" ? "registering" : status === "joined" ? "registered ✓" : "register bot"}
      </button>
      <p className="text-xs text-neutral-500">{message}</p>
    </div>
  );
}
