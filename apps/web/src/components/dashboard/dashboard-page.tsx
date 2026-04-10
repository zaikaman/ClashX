"use client";

import Link from "next/link";
import { useMemo } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CircleAlert,
  Clock3,
  ShieldAlert,
  TrendingUp,
  WalletCards,
} from "lucide-react";

import {
  getBotOpenPositionCount,
  getFleetBotStatus,
  isLiveFleetStatus,
  useFleetObservability,
} from "@/lib/fleet-observability";

function formatUsd(value: number) {
  const absolute = Math.abs(value);
  return `${value < 0 ? "-" : ""}$${absolute.toFixed(2)}`;
}

function formatSignedUsd(value: number) {
  const absolute = Math.abs(value);
  return `${value < 0 ? "-" : "+"}$${absolute.toFixed(2)}`;
}

function formatSignedPct(value: number) {
  const absolute = Math.abs(value);
  const precision = absolute >= 1 ? 2 : absolute > 0 ? 3 : 2;
  return `${value < 0 ? "-" : "+"}${absolute.toFixed(precision)}%`;
}

function formatHeartbeat(seconds: number | null | undefined) {
  if (seconds == null) {
    return "--";
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}m`;
  }
  return `${Math.floor(seconds / 3600)}h`;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "No recent event";
  }
  return new Date(value).toLocaleString();
}

function statusTone(status: string) {
  if (status === "active") {
    return "border-[#74b97f]/30 bg-[#74b97f]/10 text-[#9fcca7]";
  }
  if (status === "paused") {
    return "border-[#dce85d]/30 bg-[#dce85d]/10 text-[#e4ed9d]";
  }
  if (status === "stopped") {
    return "border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.04)] text-neutral-300";
  }
  return "border-[rgba(255,255,255,0.08)] bg-[#111315] text-neutral-400";
}

function healthTone(health: string | null | undefined) {
  if (health === "healthy") {
    return "text-[#74b97f]";
  }
  if (health === "watch") {
    return "text-[#dce85d]";
  }
  if (health === "risk" || health === "critical") {
    return "text-[#f3b86b]";
  }
  return "text-neutral-300";
}

type AttentionItem = {
  key: string;
  label: string;
  detail: string;
  severity: number;
  botId?: string;
};

export function DashboardPage() {
  const {
    authenticated,
    bots,
    error,
    liveBots,
    loading,
    login,
    loadingOverviews,
    loadingPositions,
    openPositions,
    overviewByBot,
    overviewErrors,
    sessionActive,
  } = useFleetObservability();

  const summary = useMemo(() => {
    const totals = bots.reduce(
      (accumulator, bot) => {
        accumulator.netPnl += bot.performance?.pnl_total ?? 0;
        accumulator.realized += bot.performance?.pnl_realized ?? 0;
        accumulator.unrealized += bot.performance?.pnl_unrealized ?? 0;
        accumulator.openTrades += getBotOpenPositionCount(bot);
        if ((bot.performance?.pnl_total ?? 0) >= 0) {
          accumulator.winningBots += 1;
        }
        return accumulator;
      },
      { netPnl: 0, realized: 0, unrealized: 0, openTrades: 0, winningBots: 0 },
    );

    const actionTotals = Object.values(overviewByBot).reduce(
      (accumulator, overview) => {
        if (!overview) {
          return accumulator;
        }
        accumulator.total += overview.metrics.actions_total;
        accumulator.success += overview.metrics.actions_success;
        accumulator.error += overview.metrics.actions_error;
        return accumulator;
      },
      { total: 0, success: 0, error: 0 },
    );

    const attentionCount = bots.filter((bot) => {
      const status = getFleetBotStatus(bot);
      const overview = overviewByBot[bot.id];
      if (status === "paused") {
        return true;
      }
      if ((bot.performance?.pnl_total ?? 0) < 0) {
        return true;
      }
      if (!overview) {
        return false;
      }
      return (
        overview.health.health !== "healthy" ||
        (overview.health.heartbeat_age_seconds ?? 0) > 120 ||
        overview.metrics.actions_error > 0
      );
    }).length;

    return {
      ...totals,
      attentionCount,
      actionSuccessRate: actionTotals.total > 0 ? actionTotals.success / actionTotals.total : null,
      actionErrors: actionTotals.error,
    };
  }, [bots, overviewByBot]);

  const attentionItems = useMemo<AttentionItem[]>(() => {
    const items: AttentionItem[] = [];

    for (const bot of bots) {
      const status = getFleetBotStatus(bot);
      const overview = overviewByBot[bot.id];
      const openTradeCount = getBotOpenPositionCount(bot);

      if (status === "paused" && openTradeCount > 0) {
        items.push({
          key: `${bot.id}-paused-open`,
          label: `${bot.name} is paused with open exposure`,
          detail: `${openTradeCount} live trade${openTradeCount === 1 ? "" : "s"} still need watching.`,
          severity: 0,
          botId: bot.id,
        });
      }

      if (overview && (overview.health.heartbeat_age_seconds ?? 0) > 120) {
        items.push({
          key: `${bot.id}-heartbeat`,
          label: `${bot.name} heartbeat is stale`,
          detail: `Last healthy ping was ${formatHeartbeat(overview.health.heartbeat_age_seconds)} ago.`,
          severity: 0,
          botId: bot.id,
        });
      }

      if (overview && overview.metrics.actions_error > 0) {
        items.push({
          key: `${bot.id}-errors`,
          label: `${bot.name} logged action errors`,
          detail: `${overview.metrics.actions_error} runtime error${overview.metrics.actions_error === 1 ? "" : "s"} in the last 24h.`,
          severity: 1,
          botId: bot.id,
        });
      }

      if ((bot.performance?.pnl_total ?? 0) < 0) {
        items.push({
          key: `${bot.id}-pnl`,
          label: `${bot.name} is below water`,
          detail: `${formatSignedUsd(bot.performance?.pnl_total ?? 0)} net PnL right now.`,
          severity: 2,
          botId: bot.id,
        });
      }
    }

    for (const [botId, overviewError] of Object.entries(overviewErrors)) {
      const bot = bots.find((item) => item.id === botId);
      items.push({
        key: `${botId}-overview-error`,
        label: `${bot?.name ?? "A runtime"} is missing observability data`,
        detail: overviewError,
        severity: 1,
        botId,
      });
    }

    return items.sort((left, right) => left.severity - right.severity).slice(0, 8);
  }, [bots, overviewByBot, overviewErrors]);

  const runtimeRows = useMemo(
    () =>
      [...bots]
        .filter((bot) => bot.runtime)
        .sort((left, right) => {
          const leftStatus = getFleetBotStatus(left);
          const rightStatus = getFleetBotStatus(right);
          const leftLive = isLiveFleetStatus(leftStatus) ? 0 : 1;
          const rightLive = isLiveFleetStatus(rightStatus) ? 0 : 1;
          if (leftLive !== rightLive) {
            return leftLive - rightLive;
          }
          return (right.performance?.pnl_total ?? 0) - (left.performance?.pnl_total ?? 0);
        }),
    [bots],
  );

  const hottestPositions = useMemo(
    () =>
      [...openPositions]
        .sort(
          (left, right) =>
            Math.abs(right.position.unrealized_pnl) - Math.abs(left.position.unrealized_pnl),
        )
        .slice(0, 12),
    [openPositions],
  );

  return (
    <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">
      <section className="flex flex-wrap items-end justify-between gap-4 border-b border-[rgba(255,255,255,0.08)] pb-6 md:pb-8">
        <div className="grid gap-2">
          <h1 className="font-mono text-[clamp(2rem,4vw,2.8rem)] font-bold uppercase tracking-tight text-neutral-50">
            Dashboard
          </h1>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400">
            See live bots, open trades, and the runtime alerts worth your attention.
          </p>
        </div>
      </section>

      {!authenticated ? (
        <article className="flex flex-wrap items-center justify-between gap-4 rounded-[1.8rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-5">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">Sign in required</span>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400">
              Connect the trading wallet tied to your bots to load runtime state, open positions, and fleet-wide alerts.
            </p>
          </div>
          <button
            type="button"
            onClick={login}
            className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
          >
            Sign in to open dashboard
          </button>
        </article>
      ) : null}

      {error ? (
        <article className="rounded-[1.6rem] border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={<Bot className="h-4 w-4" />}
          label="Fleet coverage"
          value={`${liveBots.length}/${bots.length}`}
          detail="Bots currently running or paused"
          accent="text-[#74b97f]"
        />
        <MetricCard
          icon={<WalletCards className="h-4 w-4" />}
          label="Open trade count"
          value={loadingPositions ? "..." : `${summary.openTrades}`}
          detail={
            loadingPositions
              ? "Loading live position data for active runtimes"
              : `${openPositions.length} active positions tracked across the fleet`
          }
          accent="text-neutral-50"
        />
        <MetricCard
          icon={<TrendingUp className="h-4 w-4" />}
          label="Fleet net PnL"
          value={formatSignedUsd(summary.netPnl)}
          detail={`${summary.winningBots} bot${summary.winningBots === 1 ? "" : "s"} above breakeven`}
          accent={summary.netPnl >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}
        />
        <MetricCard
          icon={<ShieldAlert className="h-4 w-4" />}
          label="Needs attention"
          value={loadingOverviews ? "..." : `${summary.attentionCount}`}
          detail={
            loadingOverviews
              ? "Loading runtime health and failure data"
              : summary.actionSuccessRate != null
              ? `${(summary.actionSuccessRate * 100).toFixed(1)}% action success rate`
              : "No runtime actions recorded yet"
          }
          accent={summary.attentionCount > 0 || summary.actionErrors > 0 ? "text-[#dce85d]" : "text-[#74b97f]"}
        />
      </section>

      {sessionActive && !loading && bots.length === 0 ? (
        <article className="grid gap-3 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-6 py-8">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">Nothing to monitor yet</span>
          <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
            The dashboard wakes up once you have bot drafts or runtimes
          </h2>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            Start in Builder Studio, save a bot draft, and deploy it. After that this page will show fleet state, open trades, and runtime pressure in one place.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Link
              href="/builder"
              className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
            >
              Open builder
            </Link>
            <Link
              href="/marketplace"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50"
            >
              Browse marketplace
            </Link>
          </div>
        </article>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr] xl:items-start">
        <article className="grid self-start gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#74b97f]">
                Open trade radar
              </span>
              <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                What is actually open right now
              </h2>
            </div>
            <Link
              href="/analytics"
              className="inline-flex items-center gap-2 text-sm text-neutral-300 transition hover:text-[#dce85d]"
            >
              Deeper analytics
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          {loading || (loadingPositions && hottestPositions.length === 0) ? (
            <div className="grid gap-3">
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
            </div>
          ) : hottestPositions.length === 0 ? (
            <div className="rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-6 text-sm leading-7 text-neutral-400">
              No open positions right now. The fleet is flat, which is useful too: you know there is no active exposure without opening every bot.
            </div>
          ) : (
            <div className="grid gap-3">
              {hottestPositions.map(({ botId, botName, botStatus, position }) => (
                <article
                  key={`${botId}-${position.symbol}-${position.side}`}
                  className="grid gap-4 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4 md:grid-cols-[1.1fr_0.7fr_0.9fr_0.9fr_0.9fr] md:items-center"
                >
                  <div className="grid gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
                        {position.symbol}
                      </span>
                      <span className={`rounded-full border px-2 py-0.5 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${statusTone(botStatus)}`}>
                        {botStatus}
                      </span>
                    </div>
                    <div className="text-sm text-neutral-400">
                      {botName} • {position.side}
                    </div>
                  </div>
                  <PositionCell label="Size" value={position.amount.toFixed(4)} />
                  <PositionCell label="Entry" value={formatUsd(position.entry_price)} />
                  <PositionCell label="Mark" value={formatUsd(position.mark_price)} />
                  <PositionCell
                    label="Live PnL"
                    value={formatSignedUsd(position.unrealized_pnl)}
                    tone={position.unrealized_pnl >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}
                  />
                </article>
              ))}
            </div>
          )}
        </article>

        <article className="grid self-start gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">
              Attention queue
            </span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              Surface the problems first
            </h2>
          </div>

          {loading || (loadingOverviews && attentionItems.length === 0) ? (
            <div className="grid gap-3">
              <div className="skeleton h-20 w-full rounded-[1.5rem]" />
              <div className="skeleton h-20 w-full rounded-[1.5rem]" />
              <div className="skeleton h-20 w-full rounded-[1.5rem]" />
            </div>
          ) : attentionItems.length === 0 ? (
            <div className="rounded-[1.5rem] border border-[#74b97f]/20 bg-[#74b97f]/8 px-5 py-6 text-sm leading-7 text-neutral-300">
              No urgent runtime pressure right now. Nothing is paused with open trades, no stale heartbeats were found, and no recent action errors are standing out.
            </div>
          ) : (
            <div className="grid gap-3">
              {attentionItems.map((item) => (
                <article
                  key={item.key}
                  className="grid gap-2 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="inline-flex items-center gap-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d]">
                      {item.severity === 0 ? <AlertTriangle className="h-3.5 w-3.5" /> : <CircleAlert className="h-3.5 w-3.5" />}
                      Attention
                    </div>
                    {item.botId ? (
                      <Link href={`/bots/${item.botId}`} className="text-xs text-neutral-500 transition hover:text-[#dce85d]">
                        Open bot
                      </Link>
                    ) : null}
                  </div>
                  <div className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
                    {item.label}
                  </div>
                  <p className="text-sm leading-6 text-neutral-400">{item.detail}</p>
                </article>
              ))}
            </div>
          )}
        </article>
      </section>

      <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">
              Runtime board
            </span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              Every deployed bot at a glance
            </h2>
          </div>
          <span className="text-xs text-neutral-500">
            Active and paused runtimes are sorted first
          </span>
        </div>

        {loading ? (
          <div className="grid gap-3">
            <div className="skeleton h-28 w-full rounded-[1.6rem]" />
            <div className="skeleton h-28 w-full rounded-[1.6rem]" />
            <div className="skeleton h-28 w-full rounded-[1.6rem]" />
          </div>
        ) : runtimeRows.length === 0 ? (
          <div className="rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-6 text-sm leading-7 text-neutral-400">
            No deployed runtimes yet. Draft bots will appear in My Bots first, and they land here once deployed.
          </div>
        ) : (
          <div className="grid gap-3">
            {runtimeRows.map((bot) => {
              const status = getFleetBotStatus(bot);
              const overview = overviewByBot[bot.id];
              const successRate = overview ? overview.metrics.success_rate * 100 : null;
              const lastEventAt = overview?.metrics.last_event_at ?? bot.runtime?.updated_at ?? bot.updated_at;

              return (
                <article
                  key={bot.id}
                  className="grid gap-4 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4 xl:grid-cols-[1.1fr_0.9fr_0.8fr_0.8fr_0.8fr_auto] xl:items-center"
                >
                  <div className="grid gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/bots/${bot.id}`}
                        className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50 transition hover:text-[#dce85d]"
                      >
                        {bot.name}
                      </Link>
                      <span className={`rounded-full border px-2.5 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${statusTone(status)}`}>
                        {status}
                      </span>
                    </div>
                    <p className="text-sm text-neutral-400">
                      {bot.description || "No description added yet."}
                    </p>
                  </div>

                  <RuntimeCell
                    label="Health"
                    value={overview?.health.health ?? "--"}
                    tone={healthTone(overview?.health.health)}
                    sublabel={overview ? `Heartbeat ${formatHeartbeat(overview.health.heartbeat_age_seconds)}` : "Overview pending"}
                  />
                  <RuntimeCell
                    label="Open trades"
                    value={`${getBotOpenPositionCount(bot)}`}
                    sublabel={bot.performance ? formatSignedUsd(bot.performance.pnl_unrealized) : "No live exposure"}
                    tone={bot.performance && bot.performance.pnl_unrealized !== 0 ? (bot.performance.pnl_unrealized > 0 ? "text-[#74b97f]" : "text-[#dce85d]") : "text-neutral-50"}
                  />
                  <RuntimeCell
                    label="Net PnL"
                    value={bot.performance ? formatSignedUsd(bot.performance.pnl_total) : "--"}
                    sublabel={bot.performance ? formatSignedPct(bot.performance.pnl_total_pct) : "Waiting for performance"}
                    tone={bot.performance ? (bot.performance.pnl_total >= 0 ? "text-[#74b97f]" : "text-[#dce85d]") : "text-neutral-50"}
                  />
                  <RuntimeCell
                    label="Action quality"
                    value={successRate != null ? `${successRate.toFixed(1)}%` : "--"}
                    sublabel={overview ? `${overview.metrics.actions_total} actions / 24h` : "No metrics yet"}
                    tone={successRate != null && successRate >= 80 ? "text-[#74b97f]" : successRate != null && successRate < 60 ? "text-[#dce85d]" : "text-neutral-50"}
                  />
                  <RuntimeCell
                    label="Last event"
                    value={formatDateTime(lastEventAt)}
                    sublabel={overview?.metrics.actions_error ? `${overview.metrics.actions_error} recent error${overview.metrics.actions_error === 1 ? "" : "s"}` : "No fresh failures"}
                  />

                  <div className="flex flex-wrap gap-2 xl:justify-end">
                    <Link
                      href={`/bots/${bot.id}`}
                      className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50"
                    >
                      Open desk
                    </Link>
                    <Link
                      href={`/builder?botId=${encodeURIComponent(bot.id)}`}
                      className="rounded-full border border-[rgba(220,232,93,0.2)] px-4 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d] transition hover:border-[#dce85d] hover:bg-[#dce85d]/8"
                    >
                      Edit bot
                    </Link>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}

function MetricCard({
  accent,
  detail,
  icon,
  label,
  value,
}: {
  accent: string;
  detail: string;
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <article className="grid gap-3 rounded-[1.7rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">{label}</span>
        <div className="text-neutral-500">{icon}</div>
      </div>
      <div className={`font-mono text-3xl font-bold uppercase tracking-tight ${accent}`}>{value}</div>
      <p className="text-sm leading-6 text-neutral-400">{detail}</p>
    </article>
  );
}

function PositionCell({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: string;
  value: string;
}) {
  return (
    <div className="grid gap-1">
      <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</span>
      <span className={`font-mono text-sm font-bold uppercase tracking-tight ${tone ?? "text-neutral-50"}`}>
        {value}
      </span>
    </div>
  );
}

function RuntimeCell({
  label,
  sublabel,
  tone,
  value,
}: {
  label: string;
  sublabel: string;
  tone?: string;
  value: string;
}) {
  return (
    <div className="grid gap-1">
      <span className="inline-flex items-center gap-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
        {label === "Last event" ? <Clock3 className="h-3 w-3" /> : null}
        {label}
      </span>
      <span className={`font-mono text-sm font-bold uppercase tracking-tight ${tone ?? "text-neutral-50"}`}>
        {value}
      </span>
      <span className="text-xs leading-5 text-neutral-500">{sublabel}</span>
    </div>
  );
}
