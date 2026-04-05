"use client";

import type { PortfolioBasket } from "@/lib/copy-portfolios";

type PortfolioHealthPanelProps = {
  portfolio: PortfolioBasket;
  busyAction?: "rebalance" | "kill" | "resume" | null;
  onEdit: () => void;
  onRebalance: () => void;
  onKillSwitch: (engaged: boolean) => void;
};

function toneClasses(health: string) {
  if (health === "healthy") {
    return "border-[#74b97f]/30 bg-[#74b97f]/10 text-[#b9efc5]";
  }
  if (health === "watch") {
    return "border-[#dce85d]/30 bg-[#dce85d]/10 text-[#eef4b0]";
  }
  if (health === "risk" || health === "killed") {
    return "border-[#ff8a9b]/30 bg-[#ff8a9b]/10 text-[#ffc0c9]";
  }
  return "border-white/10 bg-white/5 text-neutral-300";
}

export function PortfolioHealthPanel({
  portfolio,
  busyAction = null,
  onEdit,
  onRebalance,
  onKillSwitch,
}: PortfolioHealthPanelProps) {
  const killSwitchEngaged = portfolio.status === "killed";

  return (
    <article className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <span className="label text-[#74b97f]">Portfolio health</span>
          <h3 className="font-mono text-[clamp(1.4rem,2.4vw,2rem)] font-bold uppercase tracking-tight text-neutral-50">
            {portfolio.name}
          </h3>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            {portfolio.description || "A live basket that spreads follower risk across multiple public bot legs."}
          </p>
        </div>
        <span className={`rounded-full border px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${toneClasses(portfolio.health.health)}`}>
          {portfolio.health.health}
        </span>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Target capital</span>
          <span className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">${portfolio.target_notional_usd.toLocaleString()}</span>
          <p className="text-sm leading-6 text-neutral-400">{portfolio.members.length} source bots in the basket.</p>
        </article>
        <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Projected PnL</span>
          <span className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
            {portfolio.health.aggregate_live_pnl_usd >= 0 ? "+" : "-"}${Math.abs(portfolio.health.aggregate_live_pnl_usd).toLocaleString()}
          </span>
          <p className="text-sm leading-6 text-neutral-400">Weighted from the member runtimes currently in the mix.</p>
        </article>
        <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Aggregate drawdown</span>
          <span className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">{portfolio.health.aggregate_drawdown_pct.toFixed(1)}%</span>
          <p className="text-sm leading-6 text-neutral-400">{portfolio.health.risk_budget_used_pct.toFixed(0)}% of the basket drawdown budget is currently in use.</p>
        </article>
        <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Last rebalance</span>
          <span className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
            {portfolio.last_rebalanced_at ? new Date(portfolio.last_rebalanced_at).toLocaleString() : "Pending"}
          </span>
          <p className="text-sm leading-6 text-neutral-400">{portfolio.rebalance_mode} mode · every {portfolio.rebalance_interval_minutes} minutes.</p>
        </article>
      </div>

      <div className="flex flex-col items-start gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <button
          type="button"
          onClick={onEdit}
          className="inline-flex min-h-11 self-start items-center justify-center rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-neutral-50 hover:text-neutral-50"
        >
          Edit mix
        </button>
        <button
          type="button"
          onClick={onRebalance}
          disabled={busyAction !== null}
          className="inline-flex min-h-11 self-start items-center justify-center rounded-full bg-[#dce85d] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busyAction === "rebalance" ? "Rebalancing..." : "Rebalance now"}
        </button>
        <button
          type="button"
          onClick={() => onKillSwitch(!killSwitchEngaged)}
          disabled={busyAction !== null}
          className="inline-flex min-h-11 self-start items-center justify-center rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#ff8a9b] hover:text-[#ff8a9b] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {killSwitchEngaged
            ? busyAction === "resume"
              ? "Restarting..."
              : "Release kill switch"
            : busyAction === "kill"
              ? "Cutting risk..."
              : "Trigger kill switch"}
        </button>
      </div>

      {portfolio.kill_switch_reason ? (
        <article className="rounded-[1.5rem] border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-4 py-4 text-sm leading-6 text-[#ffd3da]">
          {portfolio.kill_switch_reason}
        </article>
      ) : null}

      {portfolio.health.alerts.length > 0 ? (
        <div className="grid gap-2 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Risk alerts</span>
          {portfolio.health.alerts.map((alert) => (
            <p key={alert} className="text-sm leading-6 text-neutral-300">
              {alert}
            </p>
          ))}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <div className="grid gap-3">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Allocation legs</span>
          <div className="grid gap-3">
            {portfolio.members.map((member) => (
              <article key={member.id} className="grid gap-3 rounded-[1.25rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="grid gap-1">
                    <span className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">{member.source_bot_name}</span>
                    <span className="text-sm text-neutral-400">
                      {member.target_weight_pct.toFixed(1)}% · ${member.target_notional_usd.toLocaleString()} · target {member.target_scale_bps / 100}%
                    </span>
                  </div>
                  <span className={`rounded-full border px-2.5 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${toneClasses(member.status === "paused" ? "watch" : member.relationship_status ?? member.status)}`}>
                    {member.status}
                  </span>
                </div>
                <div className="grid gap-3 md:grid-cols-4">
                  <div className="grid gap-1">
                    <span className="text-[0.58rem] uppercase tracking-[0.16em] text-neutral-500">Trust</span>
                    <span className="text-sm text-neutral-300">{member.trust_score}/100</span>
                  </div>
                  <div className="grid gap-1">
                    <span className="text-[0.58rem] uppercase tracking-[0.16em] text-neutral-500">Drawdown</span>
                    <span className="text-sm text-neutral-300">{member.member_drawdown_pct.toFixed(1)}%</span>
                  </div>
                  <div className="grid gap-1">
                    <span className="text-[0.58rem] uppercase tracking-[0.16em] text-neutral-500">Drift</span>
                    <span className="text-sm text-neutral-300">{member.scale_drift_pct.toFixed(1)}%</span>
                  </div>
                  <div className="grid gap-1">
                    <span className="text-[0.58rem] uppercase tracking-[0.16em] text-neutral-500">Live PnL</span>
                    <span className="text-sm text-neutral-300">{member.member_live_pnl_pct.toFixed(1)}%</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="grid gap-3">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Rebalance tape</span>
          <div className="grid gap-3">
            {portfolio.rebalance_history.length === 0 ? (
              <div className="rounded-[1.25rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-5 text-sm leading-6 text-neutral-400">
                No portfolio events yet. The first rebalance will stamp the basket state here.
              </div>
            ) : (
              portfolio.rebalance_history.map((event) => (
                <article key={event.id} className="grid gap-2 rounded-[1.25rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="font-mono text-sm font-bold uppercase tracking-tight text-neutral-50">{event.trigger.replaceAll("_", " ")}</span>
                    <span className="text-[0.58rem] uppercase tracking-[0.16em] text-neutral-500">{new Date(event.created_at).toLocaleString()}</span>
                  </div>
                  <p className="text-sm leading-6 text-neutral-400">Status: {event.status}</p>
                </article>
              ))
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
