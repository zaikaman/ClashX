"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useClashxAuth } from "@/lib/clashx-auth";

type BotCopyRelationship = {
  id: string;
  source_runtime_id: string;
  source_bot_definition_id: string;
  source_bot_name: string;
  follower_user_id: string;
  follower_wallet_address: string;
  mode: string;
  scale_bps: number;
  status: string;
  risk_ack_version: string;
  confirmed_at: string;
  updated_at: string;
  follower_display_name?: string | null;
};

type CloneListItem = {
  clone_id: string;
  source_bot_definition_id: string;
  source_bot_name: string;
  new_bot_definition_id: string;
  new_bot_name: string;
  created_at: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function CopyPage() {
  const { authenticated, login, walletAddress: authenticatedWallet, getAuthHeaders } = useClashxAuth();
  const [walletAddress, setWalletAddress] = useState("");
  const [relationships, setRelationships] = useState<BotCopyRelationship[]>([]);
  const [clones, setClones] = useState<CloneListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authenticatedWallet) {
      setWalletAddress(authenticatedWallet);
    }
  }, [authenticatedWallet]);

  useEffect(() => {
    if (!authenticated || !walletAddress) {
      setRelationships([]);
      setClones([]);
      setLoading(false);
      setError(null);
      return;
    }

    async function loadManagementData() {
      setLoading(true);
      try {
        const headers = await getAuthHeaders();
        const [relationshipsResponse, clonesResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/bot-copy?wallet_address=${encodeURIComponent(walletAddress)}`, { cache: "no-store", headers }),
          fetch(`${API_BASE_URL}/api/bot-copy/clones?wallet_address=${encodeURIComponent(walletAddress)}`, { cache: "no-store", headers }),
        ]);

        const relationshipsPayload = (await relationshipsResponse.json()) as BotCopyRelationship[] | { detail?: string };
        const clonesPayload = (await clonesResponse.json()) as CloneListItem[] | { detail?: string };

        if (!relationshipsResponse.ok) {
          throw new Error("detail" in relationshipsPayload ? relationshipsPayload.detail ?? "Could not load follows" : "Could not load follows");
        }
        if (!clonesResponse.ok) {
          throw new Error("detail" in clonesPayload ? clonesPayload.detail ?? "Could not load cloned drafts" : "Could not load cloned drafts");
        }

        setRelationships(relationshipsPayload as BotCopyRelationship[]);
        setClones(clonesPayload as CloneListItem[]);
        setError(null);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load copy management data");
      } finally {
        setLoading(false);
      }
    }

    void loadManagementData();
  }, [authenticated, getAuthHeaders, walletAddress]);

  async function stopMirror(relationshipId: string) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/bot-copy/${relationshipId}`, {
        method: "DELETE",
        headers: await getAuthHeaders(),
      });
      const payload = (await response.json()) as BotCopyRelationship | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Could not stop follow" : "Could not stop follow");
      }
      setRelationships((current) =>
        current.map((relationship) =>
          relationship.id === relationshipId ? { ...relationship, status: "stopped", updated_at: new Date().toISOString() } : relationship,
        ),
      );
    } catch (stopError) {
      setError(stopError instanceof Error ? stopError.message : "Could not stop follow");
    }
  }

  const activeFollows = useMemo(
    () => relationships.filter((relationship) => relationship.status === "active").length,
    [relationships],
  );

  if (!authenticated) {
    return (
      <main className="shell grid gap-8 pb-10 md:pb-12">
        <article className="grid gap-4 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6 md:p-8">
          <span className="label text-[#dce85d]">Sign in to use Copy Center</span>
          <h2 className="font-mono text-[clamp(2rem,5vw,3rem)] font-bold uppercase tracking-tight text-neutral-50">
            Manage live follows and cloned drafts
          </h2>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            This desk shows every bot you currently follow, the cloned drafts you can edit, and the quickest route back to the public board when you want new candidates.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={login}
              className="rounded-full bg-[#dce85d] px-5 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
            >
              Sign in
            </button>
            <Link
              href="/leaderboard"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
            >
              Browse the public board
            </Link>
          </div>
        </article>
      </main>
    );
  }

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      {error ? (
        <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-4 md:grid-cols-3">
        <article className="grid gap-1 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
          <span className="label text-[#dce85d]">Active follows</span>
          <span className="font-mono text-4xl font-bold uppercase text-neutral-50">
            {loading ? "--" : activeFollows}
          </span>
          <p className="text-sm leading-6 text-neutral-400">
            Bots currently being mirrored into your account.
          </p>
        </article>
        <article className="grid gap-1 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
          <span className="label text-[#74b97f]">Cloned drafts</span>
          <span className="font-mono text-4xl font-bold uppercase text-neutral-50">
            {loading ? "--" : clones.length}
          </span>
          <p className="text-sm leading-6 text-neutral-400">
            Editable copies you can reopen and tune.
          </p>
        </article>
        <article className="grid gap-1 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Wallet in scope</span>
          <span className="font-mono text-xl font-bold uppercase text-neutral-50">
            {walletAddress ? `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}` : "Waiting"}
          </span>
          <p className="text-sm leading-6 text-neutral-400">
            The connected wallet determines which follow relationships and drafts are shown here.
          </p>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="grid gap-4 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <div className="flex items-center justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Live follows</span>
              <span className="text-sm text-neutral-400">Bots you are actively mirroring.</span>
            </div>
            <Link
              href="/leaderboard"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
            >
              Browse board
            </Link>
          </div>

          {loading ? (
              <div className="grid gap-4">
                
<div className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4">
  <div className="flex items-center justify-between">
    <div className="skeleton h-5 w-32 rounded-md"></div>
    <div className="skeleton h-5 w-16 rounded-full"></div>
  </div>
  <div className="flex gap-4 mt-2">
    <div className="grid gap-1">
      <div className="skeleton h-3 w-16 rounded-sm"></div>
      <div className="skeleton h-6 w-20 rounded-md"></div>
    </div>
    <div className="grid gap-1">
      <div className="skeleton h-3 w-16 rounded-sm"></div>
      <div className="skeleton h-6 w-20 rounded-md"></div>
    </div>
  </div>
</div>

                
<div className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4">
  <div className="flex items-center justify-between">
    <div className="skeleton h-5 w-32 rounded-md"></div>
    <div className="skeleton h-5 w-16 rounded-full"></div>
  </div>
  <div className="flex gap-4 mt-2">
    <div className="grid gap-1">
      <div className="skeleton h-3 w-16 rounded-sm"></div>
      <div className="skeleton h-6 w-20 rounded-md"></div>
    </div>
    <div className="grid gap-1">
      <div className="skeleton h-3 w-16 rounded-sm"></div>
      <div className="skeleton h-6 w-20 rounded-md"></div>
    </div>
  </div>
</div>

              </div>
            ) : relationships.length === 0 ? (
            <p className="rounded-2xl bg-[#090a0a] px-4 py-4 text-sm leading-7 text-neutral-400">
              {loading ? "Loading current follows..." : "You are not following any bots yet. Open the public board to compare candidates first."}
            </p>
          ) : (
            relationships.map((relationship) => (
              <article key={relationship.id} className="grid gap-3 rounded-2xl bg-[#090a0a] px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
                    {relationship.source_bot_name}
                  </span>
                  <span className={`text-xs font-semibold uppercase tracking-[0.16em] ${relationship.status === "active" ? "text-[#74b97f]" : "text-neutral-500"}`}>
                    {relationship.status}
                  </span>
                </div>
                <p className="text-sm leading-7 text-neutral-400">
                  Following at {(relationship.scale_bps / 100).toFixed(0)}% scale. Last updated {new Date(relationship.updated_at).toLocaleString()}.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Link
                    href={`/leaderboard/${relationship.source_runtime_id}`}
                    className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
                  >
                    Open source bot
                  </Link>
                  <button
                    type="button"
                    onClick={() => void stopMirror(relationship.id)}
                    disabled={relationship.status !== "active"}
                    className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Stop following
                  </button>
                </div>
              </article>
            ))
          )}
        </article>

        <article className="grid gap-4 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <div className="flex items-center justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Cloned drafts</span>
              <span className="text-sm text-neutral-400">Private copies you can edit and run yourself.</span>
            </div>
            <Link
              href="/bots"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
            >
              Open my bots
            </Link>
          </div>

          {loading ? (
              <div className="grid gap-3 mt-4">
                
<div className="flex items-center justify-between rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-3">
  <div className="grid gap-1">
    <div className="skeleton h-5 w-24 rounded-md"></div>
    <div className="skeleton h-3 w-32 rounded-sm"></div>
  </div>
  <div className="skeleton h-8 w-20 rounded-full"></div>
</div>

                
<div className="flex items-center justify-between rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-3">
  <div className="grid gap-1">
    <div className="skeleton h-5 w-24 rounded-md"></div>
    <div className="skeleton h-3 w-32 rounded-sm"></div>
  </div>
  <div className="skeleton h-8 w-20 rounded-full"></div>
</div>

                
<div className="flex items-center justify-between rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-3">
  <div className="grid gap-1">
    <div className="skeleton h-5 w-24 rounded-md"></div>
    <div className="skeleton h-3 w-32 rounded-sm"></div>
  </div>
  <div className="skeleton h-8 w-20 rounded-full"></div>
</div>

              </div>
            ) : clones.length === 0 ? (
            <p className="rounded-2xl bg-[#090a0a] px-4 py-4 text-sm leading-7 text-neutral-400">
              {loading ? "Loading cloned drafts..." : "No cloned drafts yet. Clone a bot from the public board when you want to customize a winning idea."}
            </p>
          ) : (
            clones.map((clone) => (
              <article key={clone.clone_id} className="grid gap-3 rounded-2xl bg-[#090a0a] px-4 py-4">
                <div className="grid gap-1">
                  <span className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
                    {clone.new_bot_name}
                  </span>
                  <span className="text-sm leading-7 text-neutral-400">
                    Cloned from {clone.source_bot_name} on {new Date(clone.created_at).toLocaleString()}.
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link
                    href={`/bots/${clone.new_bot_definition_id}`}
                    className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
                  >
                    Open draft
                  </Link>
                </div>
              </article>
            ))
          )}
        </article>
      </section>
    </main>
  );
}
