"use client";

import { PortfolioBasketComposer } from "@/components/copy/portfolio-basket-composer";
import { PortfolioHealthPanel } from "@/components/copy/portfolio-health-panel";
import type { CopyTradingBasketSummary } from "@/lib/copy-dashboard";
import type { PortfolioBasket, PortfolioDraft } from "@/lib/copy-portfolios";
import type { LeaderboardCandidateRow } from "@/lib/public-bots";

function formatUsd(value: number) {
  return `$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

type CopyTradingAdvancedProps = {
  basketSummaries: CopyTradingBasketSummary[];
  portfolios: PortfolioBasket[];
  loadingPortfolios: boolean;
  candidateBots: LeaderboardCandidateRow[];
  candidateBotsLoading: boolean;
  portfolioDraft: PortfolioDraft;
  editingPortfolioId: string | null;
  savingPortfolio: boolean;
  busyPortfolioId: string | null;
  busyPortfolioAction: "rebalance" | "kill" | "resume" | "delete" | null;
  showComposer: boolean;
  onDraftChange: (draft: PortfolioDraft) => void;
  onOpenCreate: () => void;
  onCancelComposer: () => void;
  onSavePortfolio: () => void;
  onEditPortfolio: (portfolioId: string) => void;
  onRebalancePortfolio: (portfolioId: string) => void;
  onToggleKillSwitch: (portfolioId: string, engaged: boolean) => void;
  onDeletePortfolio: (portfolioId: string) => void;
};

export function CopyTradingAdvanced({
  basketSummaries,
  portfolios,
  loadingPortfolios,
  candidateBots,
  candidateBotsLoading,
  portfolioDraft,
  editingPortfolioId,
  savingPortfolio,
  busyPortfolioId,
  busyPortfolioAction,
  showComposer,
  onDraftChange,
  onOpenCreate,
  onCancelComposer,
  onSavePortfolio,
  onEditPortfolio,
  onRebalancePortfolio,
  onToggleKillSwitch,
  onDeletePortfolio,
}: CopyTradingAdvancedProps) {
  return (
    <div className="grid gap-6 md:gap-8">
      <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[linear-gradient(140deg,#16181a,#0d0f10)] p-6 md:p-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="grid gap-2">
            <span className="text-[0.64rem] font-semibold uppercase tracking-[0.18em] text-[#74b97f]">Advanced</span>
            <h1 className="font-mono text-[clamp(2rem,4vw,3rem)] font-bold uppercase tracking-tight text-neutral-50">Portfolio baskets</h1>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400">
              Use baskets when you want to layer a custom allocation model on top of your direct copy relationships.
            </p>
          </div>
          <button
            type="button"
            onClick={showComposer ? onCancelComposer : onOpenCreate}
            className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
          >
            {showComposer ? "Close editor" : "Create basket"}
          </button>
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {basketSummaries.length === 0 ? (
            <article className="rounded-[1.5rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#101214] px-4 py-5 text-sm leading-6 text-neutral-400 md:col-span-2 xl:col-span-4">
              No baskets yet. This area is only for more advanced allocation setups across multiple traders.
            </article>
          ) : (
            basketSummaries.map((basket) => (
              <article key={basket.id || basket.name} className="grid gap-1 rounded-[1.35rem] border border-[rgba(255,255,255,0.06)] bg-[#101214] px-4 py-4">
                <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{basket.health || basket.status || "basket"}</span>
                <span className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">{basket.name || "Unnamed basket"}</span>
                <span className="text-sm text-neutral-400">{basket.member_count} members · {formatUsd(basket.target_notional_usd)} target size</span>
                <span className="text-sm text-neutral-500">
                  {basket.alert_count > 0 ? `${basket.alert_count} alerts` : `${basket.aggregate_drawdown_pct.toFixed(1)}% drawdown`}
                </span>
              </article>
            ))
          )}
        </div>
      </section>

      {showComposer ? (
        <PortfolioBasketComposer
          draft={portfolioDraft}
          candidates={candidateBots}
          candidatesLoading={candidateBotsLoading}
          editingLabel={editingPortfolioId ? "Edit basket" : "Create basket"}
          submitting={savingPortfolio}
          onDraftChange={onDraftChange}
          onSubmit={onSavePortfolio}
          onCancelEdit={onCancelComposer}
        />
      ) : null}

      <section className="grid gap-4">
        {loadingPortfolios ? (
          <article className="rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-6 text-sm text-neutral-400">
            Loading basket details...
          </article>
        ) : portfolios.length === 0 ? (
          <article className="rounded-[1.75rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#16181a] px-5 py-6 text-sm leading-7 text-neutral-400">
            No baskets set up yet.
          </article>
        ) : (
          portfolios.map((portfolio) => (
            <PortfolioHealthPanel
              key={portfolio.id}
              portfolio={portfolio}
              busyAction={busyPortfolioId === portfolio.id ? busyPortfolioAction : null}
              onEdit={() => onEditPortfolio(portfolio.id)}
              onRebalance={() => onRebalancePortfolio(portfolio.id)}
              onKillSwitch={(engaged) => onToggleKillSwitch(portfolio.id, engaged)}
              onDelete={() => onDeletePortfolio(portfolio.id)}
            />
          ))
        )}
      </section>
    </div>
  );
}
