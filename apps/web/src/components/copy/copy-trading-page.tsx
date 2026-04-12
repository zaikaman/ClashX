"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CopyTradingAdvanced } from "@/components/copy/copy-trading-advanced";
import { CopyTradingOverview } from "@/components/copy/copy-trading-overview";
import {
  createEmptyPortfolioDraft,
  draftFromPortfolio,
  type PortfolioBasket,
  type PortfolioDraft,
} from "@/lib/copy-portfolios";
import {
  API_BASE_URL,
  type CopyTradingDashboard,
} from "@/lib/copy-dashboard";
import { useClashxAuth } from "@/lib/clashx-auth";
import {
  fetchLeaderboardCandidates,
  readCachedLeaderboardCandidates,
  type LeaderboardCandidateRow,
} from "@/lib/public-bots";

type ApiError = {
  detail?: string;
};

async function parseJson<T>(response: Response): Promise<T | ApiError> {
  try {
    return (await response.json()) as T | ApiError;
  } catch {
    return {};
  }
}

function detailMessage(payload: Record<string, unknown> | ApiError, fallback: string) {
  const detail = "detail" in payload ? payload.detail : undefined;
  return typeof detail === "string" && detail.length > 0 ? detail : fallback;
}

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

function LoadingShell() {
  return (
    <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">
      <section className="rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6 md:p-8">
        <div className="grid gap-3">
          <div className="skeleton h-4 w-36 rounded-sm" />
          <div className="skeleton h-14 w-full max-w-2xl rounded-lg" />
          <div className="skeleton h-4 w-full max-w-3xl rounded-sm" />
        </div>
      </section>
      <section className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="skeleton h-32 rounded-[1.35rem]" />
        ))}
      </section>
    </main>
  );
}

export function CopyTradingPage() {
  const { ready, authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();
  const [activeTab, setActiveTab] = useState<"overview" | "advanced">("overview");
  const [dashboard, setDashboard] = useState<CopyTradingDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingRelationshipId, setSavingRelationshipId] = useState<string | null>(null);
  const [scaleDrafts, setScaleDrafts] = useState<Record<string, number>>({});

  const [advancedLoaded, setAdvancedLoaded] = useState(false);
  const [loadingPortfolios, setLoadingPortfolios] = useState(false);
  const [candidateBots, setCandidateBots] = useState<LeaderboardCandidateRow[]>(() =>
    readCachedLeaderboardCandidates(24),
  );
  const [candidateBotsLoading, setCandidateBotsLoading] = useState(candidateBots.length === 0);
  const [portfolios, setPortfolios] = useState<PortfolioBasket[]>([]);
  const [portfolioDraft, setPortfolioDraft] = useState<PortfolioDraft>(createEmptyPortfolioDraft());
  const [editingPortfolioId, setEditingPortfolioId] = useState<string | null>(null);
  const [showComposer, setShowComposer] = useState(false);
  const [savingPortfolio, setSavingPortfolio] = useState(false);
  const [busyPortfolioId, setBusyPortfolioId] = useState<string | null>(null);
  const [busyPortfolioAction, setBusyPortfolioAction] = useState<"rebalance" | "kill" | "resume" | "delete" | null>(null);

  const loadDashboard = useCallback(
    async (silent = false) => {
      if (!authenticated || !walletAddress) {
        setDashboard(null);
        setScaleDrafts({});
        setLoading(false);
        setRefreshing(false);
        setError(null);
        return;
      }

      if (silent) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      try {
        const response = await fetch(
          `${API_BASE_URL}/api/bot-copy/dashboard?wallet_address=${encodeURIComponent(walletAddress)}`,
          {
            cache: "no-store",
            headers: await getAuthHeaders(),
          },
        );
        const payload = await parseJson<CopyTradingDashboard>(response);
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Could not load copy trading." : "Could not load copy trading.");
        }
        const nextDashboard = payload as CopyTradingDashboard;
        setDashboard(nextDashboard);
        setScaleDrafts((current) => {
          const next: Record<string, number> = {};
          for (const follow of nextDashboard.follows) {
            next[follow.id] = current[follow.id] ?? follow.scale_bps;
          }
          return next;
        });
        setError(null);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load copy trading.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [authenticated, getAuthHeaders, walletAddress],
  );

  const loadAdvanced = useCallback(async () => {
    if (!authenticated || !walletAddress) {
      setPortfolios([]);
      setAdvancedLoaded(true);
      return;
    }

    setLoadingPortfolios(true);
    setCandidateBotsLoading(readCachedLeaderboardCandidates(24).length === 0);
    try {
      const [portfoliosResponse, candidateRows] = await Promise.all([
        fetch(`${API_BASE_URL}/api/portfolios?wallet_address=${encodeURIComponent(walletAddress)}`, {
          cache: "no-store",
          headers: await getAuthHeaders(),
        }),
        fetchLeaderboardCandidates(24),
      ]);
      const portfoliosPayload = await parseJson<PortfolioBasket[]>(portfoliosResponse);
      if (!portfoliosResponse.ok) {
        throw new Error(
          "detail" in portfoliosPayload ? portfoliosPayload.detail ?? "Could not load baskets." : "Could not load baskets.",
        );
      }
      setPortfolios(portfoliosPayload as PortfolioBasket[]);
      setCandidateBots(candidateRows);
      setAdvancedLoaded(true);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Could not load advanced copy tools.");
    } finally {
      setLoadingPortfolios(false);
      setCandidateBotsLoading(false);
    }
  }, [authenticated, getAuthHeaders, walletAddress]);

  useEffect(() => {
    if (!ready) {
      return;
    }
    void loadDashboard();
  }, [loadDashboard, ready]);

  useEffect(() => {
    if (activeTab === "advanced" && !advancedLoaded) {
      void loadAdvanced();
    }
  }, [activeTab, advancedLoaded, loadAdvanced]);

  useEffect(() => {
    setAdvancedLoaded(false);
    setPortfolios([]);
    setEditingPortfolioId(null);
    setPortfolioDraft(createEmptyPortfolioDraft());
    setShowComposer(false);
  }, [walletAddress]);

  const resetPortfolioEditor = useCallback(() => {
    setEditingPortfolioId(null);
    setPortfolioDraft(createEmptyPortfolioDraft());
    setShowComposer(false);
  }, []);

  const refreshEverything = useCallback(async () => {
    await loadDashboard(true);
    if (advancedLoaded) {
      await loadAdvanced();
    }
  }, [advancedLoaded, loadAdvanced, loadDashboard]);

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
      const responsePayload = await parseJson<Record<string, unknown>>(response);
      if (!response.ok) {
        throw new Error(detailMessage(responsePayload, fallbackMessage));
      }
      await refreshEverything();
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
      const payload = await parseJson<Record<string, unknown>>(response);
      if (!response.ok) {
        throw new Error(detailMessage(payload, "Could not pause this follow."));
      }
      await refreshEverything();
    } catch (stopError) {
      setError(stopError instanceof Error ? stopError.message : "Could not pause this follow.");
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
      await loadAdvanced();
      await loadDashboard(true);
      resetPortfolioEditor();
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
                  reason: action === "kill" ? "Manual kill switch triggered from Copy Trading." : null,
                }),
        },
      );
      const payload = await parseJson<PortfolioBasket>(response);
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Portfolio action failed." : "Portfolio action failed.");
      }
      await loadAdvanced();
      await loadDashboard(true);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Portfolio action failed.");
    } finally {
      setBusyPortfolioId(null);
      setBusyPortfolioAction(null);
    }
  }

  async function deletePortfolio(portfolioId: string) {
    if (!walletAddress) {
      return;
    }

    setBusyPortfolioId(portfolioId);
    setBusyPortfolioAction("delete");
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/portfolios/${portfolioId}?wallet_address=${encodeURIComponent(walletAddress)}`,
        {
          method: "DELETE",
          headers: await getAuthHeaders(),
        },
      );
      if (!response.ok) {
        const payload = await parseJson<Record<string, unknown>>(response);
        throw new Error(detailMessage(payload, "Could not delete this basket."));
      }
      await loadAdvanced();
      await loadDashboard(true);
      if (editingPortfolioId === portfolioId) {
        resetPortfolioEditor();
      }
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Could not delete this basket.");
    } finally {
      setBusyPortfolioId(null);
      setBusyPortfolioAction(null);
    }
  }

  const portfolioById = useMemo(
    () => new Map(portfolios.map((portfolio) => [portfolio.id, portfolio])),
    [portfolios],
  );

  if (!ready) {
    return <LoadingShell />;
  }

  if (!authenticated) {
    return (
      <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">
        <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.14),transparent_28%),radial-gradient(circle_at_bottom_right,rgba(116,185,127,0.14),transparent_24%),linear-gradient(140deg,#16181a,#0d0f10)] p-6 md:p-8">
          <div className="grid gap-2">
            <span className="text-[0.64rem] font-semibold uppercase tracking-[0.2em] text-[#dce85d]">Copy trading</span>
            <h1 className="font-mono text-[clamp(2.2rem,5vw,4rem)] font-extrabold uppercase leading-[0.92] tracking-[-0.05em] text-neutral-50">
              Follow top bots with a clear view of every move
            </h1>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400 md:text-base">
              Connect your trading wallet to see open positions, live PnL, and execution status in one place.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={login}
              className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
            >
              Sign in to start copying
            </button>
            <Link
              href="/marketplace"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
            >
              Browse bots
            </Link>
          </div>
        </section>
      </main>
    );
  }

  if (loading) {
    return <LoadingShell />;
  }

  if (dashboard === null) {
    return (
      <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">
        {error ? (
          <article className="rounded-[1.5rem] border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-5 py-4 text-sm leading-6 text-neutral-50">
            {error}
          </article>
        ) : null}
        <section className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void loadDashboard()}
            className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
          >
            Try again
          </button>
          <Link
            href="/marketplace"
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
          >
            Browse bots
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">
      {error ? (
        <article className="rounded-[1.5rem] border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-5 py-4 text-sm leading-6 text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="flex flex-wrap gap-2">
        {[
          { id: "overview", label: "Overview" },
          { id: "advanced", label: "Portfolio baskets" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id as "overview" | "advanced")}
            className={`rounded-full px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] transition ${
              activeTab === tab.id
                ? "bg-[#dce85d] text-[#090a0a]"
                : "border border-[rgba(255,255,255,0.12)] text-neutral-300 hover:border-[#dce85d] hover:text-[#dce85d]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </section>

      {activeTab === "overview" ? (
        <CopyTradingOverview
          dashboard={dashboard}
          refreshing={refreshing}
          scaleDrafts={scaleDrafts}
          savingRelationshipId={savingRelationshipId}
          onRefresh={() => void refreshEverything()}
          onScaleChange={(relationshipId, value) =>
            setScaleDrafts((current) => ({
              ...current,
              [relationshipId]: value,
            }))
          }
          onSaveScale={(relationshipId, scaleBps) =>
            void updateRelationship(relationshipId, { scale_bps: scaleBps }, "Could not save the new copy scale.")
          }
          onResumeFollow={(relationshipId, scaleBps) =>
            void updateRelationship(relationshipId, { status: "active", scale_bps: scaleBps }, "Could not resume this follow.")
          }
          onStopFollow={(relationshipId) => void stopMirror(relationshipId)}
        />
      ) : (
        <CopyTradingAdvanced
          basketSummaries={dashboard.baskets_summary}
          portfolios={portfolios}
          loadingPortfolios={loadingPortfolios}
          candidateBots={candidateBots}
          candidateBotsLoading={candidateBotsLoading}
          portfolioDraft={portfolioDraft}
          editingPortfolioId={editingPortfolioId}
          savingPortfolio={savingPortfolio}
          busyPortfolioId={busyPortfolioId}
          busyPortfolioAction={busyPortfolioAction}
          showComposer={showComposer}
          onDraftChange={setPortfolioDraft}
          onOpenCreate={() => {
            setEditingPortfolioId(null);
            setPortfolioDraft(createEmptyPortfolioDraft());
            setShowComposer(true);
          }}
          onCancelComposer={resetPortfolioEditor}
          onSavePortfolio={() => void savePortfolio()}
          onEditPortfolio={(portfolioId) => {
            const portfolio = portfolioById.get(portfolioId);
            if (!portfolio) {
              return;
            }
            setEditingPortfolioId(portfolioId);
            setPortfolioDraft(draftFromPortfolio(portfolio));
            setShowComposer(true);
          }}
          onRebalancePortfolio={(portfolioId) => void runPortfolioAction(portfolioId, "rebalance")}
          onToggleKillSwitch={(portfolioId, engaged) => void runPortfolioAction(portfolioId, engaged ? "kill" : "resume")}
          onDeletePortfolio={(portfolioId) => void deletePortfolio(portfolioId)}
        />
      )}
    </main>
  );
}
