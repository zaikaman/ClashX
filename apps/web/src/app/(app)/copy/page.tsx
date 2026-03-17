"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

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

type ApiError = {
  detail?: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const SCALE_MIN_BPS = 500;
const SCALE_MAX_BPS = 30_000;
const SCALE_STEP_BPS = 500;

function formatWalletAddress(walletAddress: string | null) {
  if (!walletAddress) {
    return "Waiting for wallet";
  }
  return `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}`;
}

function formatScale(scaleBps: number) {
  return `${(scaleBps / 100).toFixed(0)}%`;
}

async function parseJson<T>(response: Response): Promise<T | ApiError> {
  try {
    return (await response.json()) as T | ApiError;
  } catch {
    return {};
  }
}

function LoadingCard() {
  return (
    <article className="grid gap-4 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-5">
      <div className="flex items-start justify-between gap-3">
        <div className="grid gap-2">
          <div className="skeleton h-5 w-40 rounded-md" />
          <div className="skeleton h-3 w-28 rounded-md" />
        </div>
        <div className="skeleton h-6 w-20 rounded-full" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1">
          <div className="skeleton h-3 w-16 rounded-sm" />
          <div className="skeleton h-5 w-24 rounded-md" />
        </div>
        <div className="grid gap-1">
          <div className="skeleton h-3 w-16 rounded-sm" />
          <div className="skeleton h-5 w-24 rounded-md" />
        </div>
      </div>
      <div className="skeleton h-10 w-full rounded-full" />
    </article>
  );
}

export default function CopyPage() {
  const { ready, authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();
  const [relationships, setRelationships] = useState<BotCopyRelationship[]>([]);
  const [clones, setClones] = useState<CloneListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [savingRelationshipId, setSavingRelationshipId] = useState<string | null>(null);
  const [scaleDrafts, setScaleDrafts] = useState<Record<string, number>>({});

  const loadManagementData = useCallback(
    async (silent = false) => {
      if (!authenticated || !walletAddress) {
        setRelationships([]);
        setClones([]);
        setError(null);
        setLastSyncedAt(null);
        setLoading(false);
        return;
      }

      if (silent) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      try {
        const headers = await getAuthHeaders();
        const [relationshipsResponse, clonesResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/bot-copy?wallet_address=${encodeURIComponent(walletAddress)}`, {
            cache: "no-store",
            headers,
          }),
          fetch(`${API_BASE_URL}/api/bot-copy/clones?wallet_address=${encodeURIComponent(walletAddress)}`, {
            cache: "no-store",
            headers,
          }),
        ]);

        const relationshipsPayload = await parseJson<BotCopyRelationship[]>(relationshipsResponse);
        const clonesPayload = await parseJson<CloneListItem[]>(clonesResponse);

        if (!relationshipsResponse.ok) {
          throw new Error(
            "detail" in relationshipsPayload ? relationshipsPayload.detail ?? "Could not load live follows." : "Could not load live follows.",
          );
        }

        if (!clonesResponse.ok) {
          throw new Error(
            "detail" in clonesPayload ? clonesPayload.detail ?? "Could not load cloned drafts." : "Could not load cloned drafts.",
          );
        }

        setRelationships(relationshipsPayload as BotCopyRelationship[]);
        setClones(clonesPayload as CloneListItem[]);
        setError(null);
        setLastSyncedAt(new Date().toISOString());
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load copy management data.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [authenticated, getAuthHeaders, walletAddress],
  );

  useEffect(() => {
    if (!ready) {
      return;
    }
    void loadManagementData();
  }, [loadManagementData, ready]);

  useEffect(() => {
    setScaleDrafts((current) => {
      const next: Record<string, number> = {};
      for (const relationship of relationships) {
        next[relationship.id] = current[relationship.id] ?? relationship.scale_bps;
      }
      return next;
    });
  }, [relationships]);

  const activeFollows = useMemo(
    () => relationships.filter((relationship) => relationship.status === "active").length,
    [relationships],
  );

  const pausedFollows = useMemo(
    () => relationships.filter((relationship) => relationship.status !== "active").length,
    [relationships],
  );

  async function updateRelationship(
    relationshipId: string,
    payload: { scale_bps?: number; status?: string },
    fallbackMessage: string,
  ) {
    setSavingRelationshipId(relationshipId);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/bot-copy/${relationshipId}`, {
        method: "PATCH",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      const responsePayload = await parseJson<BotCopyRelationship>(response);
      if (!response.ok) {
        throw new Error("detail" in responsePayload ? responsePayload.detail ?? fallbackMessage : fallbackMessage);
      }

      const updatedRelationship = responsePayload as BotCopyRelationship;
      setRelationships((current) =>
        current.map((relationship) => (relationship.id === relationshipId ? updatedRelationship : relationship)),
      );
      setScaleDrafts((current) => ({
        ...current,
        [relationshipId]: updatedRelationship.scale_bps,
      }));
      setLastSyncedAt(new Date().toISOString());
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : fallbackMessage);
    } finally {
      setSavingRelationshipId(null);
    }
  }

  async function stopMirror(relationshipId: string) {
    setSavingRelationshipId(relationshipId);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/bot-copy/${relationshipId}`, {
        method: "DELETE",
        headers: await getAuthHeaders(),
      });
      const payload = await parseJson<BotCopyRelationship>(response);
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Could not stop this live follow." : "Could not stop this live follow.");
      }

      const stoppedRelationship = payload as BotCopyRelationship;
      setRelationships((current) =>
        current.map((relationship) => (relationship.id === relationshipId ? stoppedRelationship : relationship)),
      );
      setLastSyncedAt(new Date().toISOString());
    } catch (stopError) {
      setError(stopError instanceof Error ? stopError.message : "Could not stop this live follow.");
    } finally {
      setSavingRelationshipId(null);
    }
  }

  if (!ready) {
    return (
      <main className="shell grid gap-8 pb-10 md:pb-12">
        <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.14),transparent_32%),#16181a] p-6 md:p-8">
          <div className="grid gap-3">
            <div className="skeleton h-4 w-32 rounded-sm" />
            <div className="skeleton h-12 w-80 rounded-lg" />
            <div className="skeleton h-4 w-full max-w-3xl rounded-sm" />
          </div>
        </section>
        <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="grid gap-4">
            {Array.from({ length: 2 }).map((_, index) => (
              <LoadingCard key={`loading-follow-${index}`} />
            ))}
          </div>
          <div className="grid gap-4">
            {Array.from({ length: 2 }).map((_, index) => (
              <LoadingCard key={`loading-clone-${index}`} />
            ))}
          </div>
        </section>
      </main>
    );
  }

  if (!authenticated) {
    return (
      <main className="shell grid gap-8 pb-10 md:pb-12">
        <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.16),transparent_32%),linear-gradient(135deg,#16181a,#0d0f10)] p-6 md:p-8">
          <span className="label text-[#dce85d]">Copy Center</span>
          <div className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
            <div className="grid gap-3">
              <h1 className="font-mono text-[clamp(2.25rem,5vw,4.5rem)] font-extrabold uppercase leading-[0.92] tracking-[-0.05em] text-neutral-50">
                Keep every live follow and every cloned draft in one place.
              </h1>
              <p className="max-w-3xl text-sm leading-7 text-neutral-400 md:text-base">
                Sign in to see the bots you mirror live, reopen the drafts you cloned for custom tuning, and move back to the public board when you want a new strategy to evaluate.
              </p>
            </div>
            <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-5">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Before you start</span>
              <p className="text-sm leading-7 text-neutral-400">
                Your connected wallet decides which follows and drafts appear here. Use your Privy session to unlock the management view.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={login}
              className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
            >
              Sign in
            </button>
            <Link
              href="/leaderboard"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
            >
              Browse the public board
            </Link>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(116,185,127,0.14),transparent_26%),radial-gradient(circle_at_bottom_right,rgba(220,232,93,0.12),transparent_24%),linear-gradient(135deg,#16181a,#0d0f10)] p-6 md:p-8">
        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
          <div className="grid gap-3">
            <span className="label text-[#74b97f]">Copy Center</span>
            <h1 className="font-mono text-[clamp(2.2rem,5vw,4.25rem)] font-extrabold uppercase leading-[0.92] tracking-[-0.05em] text-neutral-50">
              Run your follow book with real controls.
            </h1>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400 md:text-base">
              Adjust live follow sizing, pause or resume a mirror, and reopen cloned drafts without leaving the operating desk.
            </p>
          </div>

          <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-5">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Wallet in scope</span>
              <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">
                {refreshing ? "Refreshing" : "Live"}
              </span>
            </div>
            <span className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              {formatWalletAddress(walletAddress)}
            </span>
            <p className="text-sm leading-7 text-neutral-400">
              {lastSyncedAt ? `Last synced ${new Date(lastSyncedAt).toLocaleString()}.` : "Pull data from your linked wallet to see the latest follow state."}
            </p>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void loadManagementData(true)}
                disabled={loading || refreshing}
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {refreshing ? "Refreshing..." : "Refresh data"}
              </button>
              <Link
                href="/leaderboard"
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
              >
                Find strategies
              </Link>
            </div>
          </div>
        </div>
      </section>

      {error ? (
        <article className="rounded-[1.5rem] border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm leading-6 text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-4 md:grid-cols-4">
        <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
          <span className="label text-[#dce85d]">Active follows</span>
          <span className="font-mono text-4xl font-bold uppercase text-neutral-50">{loading ? "--" : activeFollows}</span>
          <p className="text-sm leading-6 text-neutral-400">Bots currently mirroring into your delegated wallet.</p>
        </article>
        <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
          <span className="label text-[#74b97f]">Inactive follows</span>
          <span className="font-mono text-4xl font-bold uppercase text-neutral-50">{loading ? "--" : pausedFollows}</span>
          <p className="text-sm leading-6 text-neutral-400">Relationships you can resume after reviewing risk and sizing.</p>
        </article>
        <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
          <span className="label text-[#dce85d]">Cloned drafts</span>
          <span className="font-mono text-4xl font-bold uppercase text-neutral-50">{loading ? "--" : clones.length}</span>
          <p className="text-sm leading-6 text-neutral-400">Private strategy copies ready for edits, deployment, or archive cleanup.</p>
        </article>
        <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Risk acknowledgement</span>
          <span className="font-mono text-xl font-bold uppercase text-neutral-50">Version v1</span>
          <p className="text-sm leading-6 text-neutral-400">Scale changes apply to future mirrored actions, not retroactive fills.</p>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.18fr_0.82fr]">
        <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <div className="flex items-center justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Live follows</span>
              <span className="text-sm text-neutral-400">Review status, resize exposure, or stop a relationship before the next mirrored action lands.</span>
            </div>
            <Link
              href="/leaderboard"
              className="whitespace-nowrap rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
            >
              Browse board
            </Link>
          </div>

          {loading ? (
            <div className="grid gap-4">
              {Array.from({ length: 2 }).map((_, index) => (
                <LoadingCard key={`relationship-skeleton-${index}`} />
              ))}
            </div>
          ) : relationships.length === 0 ? (
            <article className="grid gap-4 rounded-[1.5rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-5 py-6">
              <div className="grid gap-2">
                <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">No live follows yet</h2>
                <p className="max-w-2xl text-sm leading-7 text-neutral-400">
                  Start from the public board, inspect a runtime profile, and activate mirroring only after you are comfortable with the strategy and current positions.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Link
                  href="/leaderboard"
                  className="w-fit rounded-full bg-[#dce85d] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
                >
                  Explore the leaderboard
                </Link>
                <Link
                  href="/bots"
                  className="w-fit rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
                >
                  Open my bots
                </Link>
              </div>
            </article>
          ) : (
            relationships.map((relationship) => {
              const scaleDraft = scaleDrafts[relationship.id] ?? relationship.scale_bps;
              const scaleChanged = scaleDraft !== relationship.scale_bps;
              const isSaving = savingRelationshipId === relationship.id;

              return (
                <article
                  key={relationship.id}
                  className="grid gap-5 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-5"
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="grid gap-2">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                          {relationship.source_bot_name}
                        </span>
                        <span
                          className={`rounded-full px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${
                            relationship.status === "active"
                              ? "bg-[color:var(--mint-dim)] text-[#74b97f]"
                              : "bg-neutral-900 text-neutral-400"
                          }`}
                        >
                          {relationship.status}
                        </span>
                      </div>
                      <p className="text-sm leading-7 text-neutral-400">
                        Confirmed {new Date(relationship.confirmed_at).toLocaleString()} and last touched{" "}
                        {new Date(relationship.updated_at).toLocaleString()}.
                      </p>
                    </div>

                    <div className="grid gap-1 text-sm text-neutral-400 lg:text-right">
                      <span>{relationship.follower_display_name || "Privy account"}</span>
                      <span>{formatWalletAddress(relationship.follower_wallet_address)}</span>
                    </div>
                  </div>

                  <div className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
                    <div className="grid gap-3 rounded-[1.25rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4">
                      <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Position sizing</span>
                      <div className="flex items-end justify-between gap-3">
                        <span className="font-mono text-3xl font-bold uppercase tracking-tight text-neutral-50">
                          {formatScale(scaleDraft)}
                        </span>
                        <span className="text-xs text-neutral-500">Updates apply to upcoming mirrored orders.</span>
                      </div>
                      <input
                        type="range"
                        min={SCALE_MIN_BPS}
                        max={SCALE_MAX_BPS}
                        step={SCALE_STEP_BPS}
                        value={scaleDraft}
                        disabled={isSaving}
                        onChange={(event) =>
                          setScaleDrafts((current) => ({
                            ...current,
                            [relationship.id]: Number(event.target.value),
                          }))
                        }
                        className="accent-[#dce85d]"
                      />
                      <div className="flex flex-wrap gap-2 text-[0.62rem] uppercase tracking-[0.16em] text-neutral-500">
                        <span>Min 5%</span>
                        <span>Max 300%</span>
                      </div>
                    </div>

                    <div className="grid gap-3">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => void updateRelationship(relationship.id, { scale_bps: scaleDraft }, "Could not save the new follow scale.")}
                          disabled={!scaleChanged || isSaving}
                          className="rounded-full bg-[#dce85d] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {isSaving && scaleChanged ? "Saving..." : scaleChanged ? "Save scale" : "Scale saved"}
                        </button>

                        {relationship.status === "active" ? (
                          <button
                            type="button"
                            onClick={() => void stopMirror(relationship.id)}
                            disabled={isSaving}
                            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {isSaving ? "Stopping..." : "Stop follow"}
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() =>
                              void updateRelationship(
                                relationship.id,
                                { status: "active", scale_bps: scaleDraft },
                                "Could not resume this live follow.",
                              )
                            }
                            disabled={isSaving}
                            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {isSaving ? "Resuming..." : "Resume follow"}
                          </button>
                        )}

                        <Link
                          href={`/leaderboard/${relationship.source_runtime_id}`}
                          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-neutral-50 hover:text-neutral-50"
                        >
                          Open source bot
                        </Link>
                      </div>

                      <div className="grid gap-2 rounded-[1.25rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4 text-sm leading-6 text-neutral-400">
                        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Execution note</span>
                        <p>
                          This relationship mirrors source runtime actions under your current risk acknowledgement and linked Pacifica authorization.
                        </p>
                      </div>
                    </div>
                  </div>
                </article>
              );
            })
          )}
        </article>

        <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <div className="flex items-center justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Cloned drafts</span>
              <span className="text-sm text-neutral-400">Private copies you can reopen, tune, and deploy from your own bot workspace.</span>
            </div>
            <Link
              href="/bots"
              className="whitespace-nowrap rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
            >
              Open my bots
            </Link>
          </div>

          {loading ? (
            <div className="grid gap-4">
              {Array.from({ length: 3 }).map((_, index) => (
                <LoadingCard key={`clone-skeleton-${index}`} />
              ))}
            </div>
          ) : clones.length === 0 ? (
            <article className="grid gap-4 rounded-[1.5rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-5 py-6">
              <div className="grid gap-2">
                <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">No cloned drafts yet</h2>
                <p className="text-sm leading-7 text-neutral-400">
                  Clone a strong runtime when you want the idea, but still need room to change rules, markets, or deployment settings inside your own workspace.
                </p>
              </div>
              <Link
                href="/leaderboard"
                className="w-fit rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
              >
                Browse cloneable bots
              </Link>
            </article>
          ) : (
            clones.map((clone) => (
              <article
                key={clone.clone_id}
                className="grid gap-4 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-5"
              >
                <div className="grid gap-2">
                  <span className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">
                    {clone.new_bot_name}
                  </span>
                  <p className="text-sm leading-7 text-neutral-400">
                    Cloned from {clone.source_bot_name} on {new Date(clone.created_at).toLocaleString()}.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <Link
                    href={`/bots/${clone.new_bot_definition_id}`}
                    className="w-fit rounded-full bg-[#dce85d] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
                  >
                    Open draft
                  </Link>
                  <Link
                    href="/leaderboard"
                    className="w-fit rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
                  >
                    Clone another
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
