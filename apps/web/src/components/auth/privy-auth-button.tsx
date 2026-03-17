"use client";

import { useClashxAuth } from "@/lib/clashx-auth";

function shortAddress(value: string | null) {
  if (!value) {
    return "No wallet connected";
  }
  return `${value.slice(0, 4)}...${value.slice(-4)}`;
}

export function PrivyAuthButton() {
  const { ready, authenticated, login, logout, walletAddress } = useClashxAuth();

  if (!ready) {
    return <div className="text-xs uppercase tracking-[0.16em] text-neutral-500">Checking wallet</div>;
  }

  if (!authenticated) {
    return (
      <button
        type="button"
        onClick={login}
        className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition-all duration-200 hover:border-[#dce85d] hover:text-[#dce85d]"
      >
        Connect wallet
      </button>
    );
  }

  return (
    <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
      <span className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2 text-sm font-medium text-neutral-50">
        {shortAddress(walletAddress)}
      </span>
      <button
        type="button"
        onClick={logout}
        className="rounded-full border border-[rgba(255,255,255,0.06)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
      >
        Sign out
      </button>
    </div>
  );
}
