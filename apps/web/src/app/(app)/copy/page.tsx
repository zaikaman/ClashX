"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createEmptyPortfolioDraft,
  draftFromPortfolio,
  type PortfolioBasket,
  type PortfolioDraft,
} from "@/lib/copy-portfolios";
import { useClashxAuth } from "@/lib/clashx-auth";
import {
  fetchLeaderboardCandidates,
  readCachedLeaderboardCandidates,
  type LeaderboardCandidateRow,
} from "@/lib/public-bots";

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
const CANDIDATE_LIMIT = 24;

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

function BasketComposerSkeleton() {
  return (
    <article className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-3">
          <div className="skeleton h-4 w-28 rounded-sm" />
          <div className="skeleton h-12 w-80 rounded-lg" />
          <div className="skeleton h-4 w-full max-w-3xl rounded-sm" />
          <div className="skeleton h-4 w-72 rounded-sm" />
        </div>
        <div className="skeleton h-10 w-32 rounded-full" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="grid gap-4">
          <div className="grid gap-2">
            <div className="skeleton h-4 w-24 rounded-sm" />
            <div className="skeleton h-12 w-full rounded-2xl" />
          </div>
          <div className="grid gap-2">
            <div className="skeleton h-4 w-40 rounded-sm" />
            <div className="skeleton h-28 w-full rounded-2xl" />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={`basket-input-skeleton-${index}`} className="grid gap-2">
                <div className="skeleton h-4 w-28 rounded-sm" />
                <div className="skeleton h-12 w-full rounded-2xl" />
              </div>
            ))}
          </div>
          <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
            <div className="grid gap-2">
              <div className="skeleton h-4 w-24 rounded-sm" />
              <div className="skeleton h-4 w-full rounded-sm" />
              <div className="skeleton h-4 w-4/5 rounded-sm" />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={`basket-risk-skeleton-${index}`} className="grid gap-2">
                  <div className="skeleton h-4 w-28 rounded-sm" />
                  <div className="skeleton h-12 w-full rounded-2xl" />
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="grid gap-4">
          <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="grid gap-2">
                <div className="skeleton h-4 w-32 rounded-sm" />
                <div className="skeleton h-4 w-56 rounded-sm" />
              </div>
              <div className="skeleton h-8 w-28 rounded-full" />
            </div>
            <div className="skeleton h-28 w-full rounded-[1.5rem]" />
          </div>

          <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
            <div className="grid gap-2">
              <div className="skeleton h-4 w-28 rounded-sm" />
              <div className="skeleton h-4 w-full rounded-sm" />
              <div className="skeleton h-4 w-5/6 rounded-sm" />
            </div>
            <div className="grid gap-3">
              {Array.from({ length: 2 }).map((_, index) => (
                <div
                  key={`basket-candidate-skeleton-${index}`}
                  className="grid gap-3 rounded-[1.25rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4 md:grid-cols-[1fr_auto]"
                >
                  <div className="grid gap-2">
                    <div className="skeleton h-5 w-40 rounded-md" />
                    <div className="skeleton h-4 w-56 rounded-sm" />
                  </div>
                  <div className="skeleton h-10 w-32 rounded-full" />
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
            <div className="skeleton h-12 w-40 rounded-full" />
            <div className="skeleton h-12 w-36 rounded-full" />
          </div>
        </div>
      </div>
    </article>
  );
}

const PortfolioBasketComposer = dynamic(
  () => import("@/components/copy/portfolio-basket-composer").then((module) => module.PortfolioBasketComposer),
  {
    loading: () => <BasketComposerSkeleton />,
  },
);

const PortfolioHealthPanel = dynamic(
  () => import("@/components/copy/portfolio-health-panel").then((module) => module.PortfolioHealthPanel),
  {
    loading: () => <LoadingCard />,
  },
);

function serializePortfolioDraft(draft: PortfolioDraft) {
  return {
    name: draft.name,
    description: draft.description,
    rebalance_mode: draft.rebalance_mode,
    rebalance_interval_minutes: draft.rebalance_interval_minutes,
    drift_threshold_pct: draft.drift_threshold_pct,
    target_notional_usd: draft.target_notional_usd,
    activate_on_create: draft.activate_on_create,
    risk_policy: draft.risk_policy,
    members: draft.members.map((member) => ({
      source_runtime_id: member.source_runtime_id,
      target_weight_pct: member.target_weight_pct,
      max_scale_bps: member.max_scale_bps,
    })),
  };
}

export default function CopyPage() {
  const { ready, authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();
  const [relationships, setRelationships] = useState<BotCopyRelationship[]>([]);
  const [clones, setClones] = useState<CloneListItem[]>([]);
  const [portfolios, setPortfolios] = useState<PortfolioBasket[]>([]);
  const [candidateBots, setCandidateBots] = useState<LeaderboardCandidateRow[]>(() =>
    readCachedLeaderboardCandidates(CANDIDATE_LIMIT),
  );
  const [loading, setLoading] = useState(true);
  const [candidateBotsLoading, setCandidateBotsLoading] = useState(candidateBots.length === 0);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [savingRelationshipId, setSavingRelationshipId] = useState<string | null>(null);
  const [scaleDrafts, setScaleDrafts] = useState<Record<string, number>>({});
  const [portfolioDraft, setPortfolioDraft] = useState<PortfolioDraft>(createEmptyPortfolioDraft());
  const [editingPortfolioId, setEditingPortfolioId] = useState<string | null>(null);
  const [savingPortfolio, setSavingPortfolio] = useState(false);
  const [busyPortfolioId, setBusyPortfolioId] = useState<string | null>(null);
  const [busyPortfolioAction, setBusyPortfolioAction] = useState<"rebalance" | "kill" | "resume" | null>(null);

  const loadManagementData = useCallback(
    async (silent = false) => {
      if (!authenticated || !walletAddress) {
        setRelationships([]);
        setClones([]);
        setPortfolios([]);
        setError(null);
        setLastSyncedAt(null);
        setLoading(false);
        setCandidateBotsLoading(false);
        return;
      }

      if (silent) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      try {
        const headers = await getAuthHeaders();
        const [relationshipsResponse, clonesResponse, portfoliosResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/bot-copy?wallet_address=${encodeURIComponent(walletAddress)}`, {
            cache: "no-store",
            headers,
          }),
          fetch(`${API_BASE_URL}/api/bot-copy/clones?wallet_address=${encodeURIComponent(walletAddress)}`, {
            cache: "no-store",
            headers,
          }),
          fetch(`${API_BASE_URL}/api/portfolios?wallet_address=${encodeURIComponent(walletAddress)}`, {
            cache: "no-store",
            headers,
          }),
        ]);

        const relationshipsPayload = await parseJson<BotCopyRelationship[]>(relationshipsResponse);
        const clonesPayload = await parseJson<CloneListItem[]>(clonesResponse);
        const portfoliosPayload = await parseJson<PortfolioBasket[]>(portfoliosResponse);

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

        if (!portfoliosResponse.ok) {
          throw new Error(
            "detail" in portfoliosPayload ? portfoliosPayload.detail ?? "Could not load portfolio baskets." : "Could not load portfolio baskets.",
          );
        }

        setRelationships(relationshipsPayload as BotCopyRelationship[]);
        setClones(clonesPayload as CloneListItem[]);
        setPortfolios(portfoliosPayload as PortfolioBasket[]);
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

  const loadCandidateBots = useCallback(async () => {
    if (!authenticated) {
      setCandidateBots([]);
      setCandidateBotsLoading(false);
      return;
    }

    setCandidateBotsLoading(readCachedLeaderboardCandidates(CANDIDATE_LIMIT).length === 0);

    try {
      const rows = await fetchLeaderboardCandidates(CANDIDATE_LIMIT);
      setCandidateBots(rows);
    } catch {
      // Keep the rest of the page interactive if the public candidate feed is slow.
    } finally {
      setCandidateBotsLoading(false);
    }
  }, [authenticated]);

  useEffect(() => {
    if (!ready) {
      return;
    }
    void loadManagementData();
    void loadCandidateBots();
  }, [loadCandidateBots, loadManagementData, ready]);

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

  const activePortfolios = useMemo(
    () => portfolios.filter((portfolio) => portfolio.status === "active").length,
    [portfolios],
  );

  const totalPortfolioCapital = useMemo(
    () => portfolios.reduce((sum, portfolio) => sum + portfolio.target_notional_usd, 0),
    [portfolios],
  );

  function resetPortfolioEditor() {
    setEditingPortfolioId(null);
    setPortfolioDraft(createEmptyPortfolioDraft());
  }

  function upsertPortfolio(nextPortfolio: PortfolioBasket) {
    setPortfolios((current) => {
      const exists = current.some((portfolio) => portfolio.id === nextPortfolio.id);
      if (!exists) {
        return [nextPortfolio, ...current];
      }
      return current.map((portfolio) => (portfolio.id === nextPortfolio.id ? nextPortfolio : portfolio));
    });
  }

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

  async function savePortfolio() {
    if (!walletAddress) {
      return;
    }

    setSavingPortfolio(true);
    setError(null);

    try {
      const isEditing = Boolean(editingPortfolioId);
      const response = await fetch(
        isEditing
          ? `${API_BASE_URL}/api/portfolios/${editingPortfolioId}?wallet_address=${encodeURIComponent(walletAddress)}`
          : `${API_BASE_URL}/api/portfolios`,
        {
          method: isEditing ? "PATCH" : "POST",
          headers: await getAuthHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(
            isEditing
              ? serializePortfolioDraft(portfolioDraft)
              : {
                  wallet_address: walletAddress,
                  ...serializePortfolioDraft(portfolioDraft),
                },
          ),
        },
      );
      const payload = await parseJson<PortfolioBasket>(response);
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Could not save the basket." : "Could not save the basket.");
      }
      upsertPortfolio(payload as PortfolioBasket);
      resetPortfolioEditor();
      setLastSyncedAt(new Date().toISOString());
      void loadManagementData(true);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save the basket.");
    } finally {
      setSavingPortfolio(false);
    }
  }

  async function runPortfolioAction(portfolioId: string, action: "rebalance" | "kill" | "resume") {
    if (!walletAddress) {
      return;
    }

    setBusyPortfolioId(portfolioId);
    setBusyPortfolioAction(action);
    setError(null);

    try {
      const response = await fetch(
        action === "rebalance"
          ? `${API_BASE_URL}/api/portfolios/${portfolioId}/rebalance?wallet_address=${encodeURIComponent(walletAddress)}`
          : `${API_BASE_URL}/api/portfolios/${portfolioId}/kill-switch?wallet_address=${encodeURIComponent(walletAddress)}`,
        {
          method: "POST",
          headers: await getAuthHeaders({ "Content-Type": "application/json" }),
          body:
            action === "rebalance"
              ? undefined
              : JSON.stringify({
                  engaged: action === "kill",
                  reason: action === "kill" ? "Manual kill switch triggered from Copy Center." : null,
                }),
        },
      );
      const payload = await parseJson<PortfolioBasket>(response);
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Portfolio action failed." : "Portfolio action failed.");
      }
      upsertPortfolio(payload as PortfolioBasket);
      setLastSyncedAt(new Date().toISOString());
      void loadManagementData(true);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Portfolio action failed.");
    } finally {
      setBusyPortfolioId(null);
      setBusyPortfolioAction(null);
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
        <section className="grid gap-4">
          {Array.from({ length: 3 }).map((_, index) => (
            <LoadingCard key={`loading-portfolio-${index}`} />
          ))}
        </section>
      </main>
    );
  }

  if (!authenticated) {
    return (
      <main className="shell grid gap-8 pb-10 md:pb-12">
        <section className="grid gap-4 border-b border-[rgba(255,255,255,0.08)] pb-6 md:pb-8">
          <div className="grid gap-2">
            <h1 className="font-mono text-[clamp(2rem,4vw,2.8rem)] font-bold uppercase tracking-tight text-neutral-50">
              Copy Center
            </h1>
            <p className="max-w-2xl text-sm leading-7 text-neutral-400">
              Follow live bots and manage cloned drafts.
            </p>
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
              href="/marketplace"
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
      <section className="flex flex-wrap items-end justify-between gap-4 border-b border-[rgba(255,255,255,0.08)] pb-6 md:pb-8">
        <div className="grid gap-2">
          <h1 className="font-mono text-[clamp(2rem,4vw,2.8rem)] font-bold uppercase tracking-tight text-neutral-50">
            Copy Center
          </h1>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400">
            Manage follows, cloned drafts, and portfolio baskets.
          </p>
        </div>
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
            href="/marketplace"
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
          >
            Find strategies
          </Link>
        </div>
      </section>

      {error ? (
        <article className="rounded-[1.5rem] border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm leading-6 text-neutral-50">
          {error}
        </article>
      ) : null}


      {loading ? (
        <BasketComposerSkeleton />
      ) : (
        <PortfolioBasketComposer
          draft={portfolioDraft}
          candidates={candidateBots}
          candidatesLoading={candidateBotsLoading}
          editingLabel={editingPortfolioId ? "Editing basket" : null}
          submitting={savingPortfolio}
          onDraftChange={setPortfolioDraft}
          onSubmit={() => void savePortfolio()}
          onCancelEdit={editingPortfolioId ? resetPortfolioEditor : undefined}
        />
      )}

      <section className="grid gap-4">
        {loading ? (
          Array.from({ length: 2 }).map((_, index) => <LoadingCard key={`portfolio-panel-${index}`} />)
        ) : portfolios.length === 0 ? (
          <article className="grid gap-4 rounded-[2rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#16181a] px-6 py-7">
            <div className="grid gap-2">
              <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">No baskets yet</h2>
              <p className="max-w-3xl text-sm leading-7 text-neutral-400">
                Create a basket when one mirrored bot is too concentrated. Blend a few public leaders, set the portfolio drawdown line, and let the basket worker keep the mix aligned.
              </p>
            </div>
          </article>
        ) : (
          portfolios.map((portfolio) => (
            <PortfolioHealthPanel
              key={portfolio.id}
              portfolio={portfolio}
              busyAction={busyPortfolioId === portfolio.id ? busyPortfolioAction : null}
              onEdit={() => {
                setEditingPortfolioId(portfolio.id);
                setPortfolioDraft(draftFromPortfolio(portfolio));
              }}
              onRebalance={() => void runPortfolioAction(portfolio.id, "rebalance")}
              onKillSwitch={(engaged) => void runPortfolioAction(portfolio.id, engaged ? "kill" : "resume")}
            />
          ))
        )}
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.18fr_0.82fr]">
        <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <div className="flex items-center justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Live follows</span>
              <span className="text-sm text-neutral-400">Review status, resize exposure, or stop a relationship before the next mirrored action lands.</span>
            </div>
            <Link
              href="/marketplace"
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
                  href="/marketplace"
                  className="w-fit rounded-full bg-[#dce85d] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
                >
                  Explore the marketplace
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
                <article key={relationship.id} className="grid gap-5 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="grid gap-2">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                          {relationship.source_bot_name}
                        </span>
                        <span
                          className={`rounded-full px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${
                            relationship.status === "active" ? "bg-[color:var(--mint-dim)] text-[#74b97f]" : "bg-neutral-900 text-neutral-400"
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
                              void updateRelationship(relationship.id, { status: "active", scale_bps: scaleDraft }, "Could not resume this live follow.")
                            }
                            disabled={isSaving}
                            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {isSaving ? "Resuming..." : "Resume follow"}
                          </button>
                        )}

                        <Link
                          href={`/marketplace/${relationship.source_runtime_id}`}
                          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-neutral-50 hover:text-neutral-50"
                        >
                          Open source bot
                        </Link>
                      </div>

                      <div className="grid gap-2 rounded-[1.25rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4 text-sm leading-6 text-neutral-400">
                        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Execution note</span>
                        <p>This relationship mirrors source runtime actions under your current risk acknowledgement and linked Pacifica authorization.</p>
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
                href="/marketplace"
                className="w-fit rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
              >
                Browse cloneable bots
              </Link>
            </article>
          ) : (
            clones.map((clone) => (
              <article key={clone.clone_id} className="grid gap-4 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-5">
                <div className="grid gap-2">
                  <span className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">{clone.new_bot_name}</span>
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
                    href="/marketplace"
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
