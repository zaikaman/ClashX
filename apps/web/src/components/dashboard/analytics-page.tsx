"use client";

import Link from "next/link";
import { useMemo, type ReactNode } from "react";
import {
  Activity,
  Bot,
  Gauge,
  Layers3,
  ShieldAlert,
  TrendingUp,
  TriangleAlert,
} from "lucide-react";

import {
  getFleetBotStatus,
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

function percentWidth(value: number, total: number) {
  if (!Number.isFinite(value) || !Number.isFinite(total) || total <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, (value / total) * 100));
}

export function AnalyticsPage() {
  const {
    authenticated,
    bots,
    error,
    loading,
    login,
    loadingOverviews,
    loadingPositions,
    openPositions,
    overviewByBot,
    refresh,
    sessionActive,
  } = useFleetObservability();

  const aggregate = useMemo(() => {
    const base = {
      netPnl: 0,
      realized: 0,
      unrealized: 0,
      actionsTotal: 0,
      actionsSuccess: 0,
      actionsError: 0,
      actionsSkipped: 0,
      eventTypes: new Map<string, number>(),
      decisionStatuses: new Map<string, number>(),
    };

    for (const bot of bots) {
      base.netPnl += bot.performance?.pnl_total ?? 0;
      base.realized += bot.performance?.pnl_realized ?? 0;
      base.unrealized += bot.performance?.pnl_unrealized ?? 0;

      const overview = overviewByBot[bot.id];
      if (!overview) {
        continue;
      }

      base.actionsTotal += overview.metrics.actions_total;
      base.actionsSuccess += overview.metrics.actions_success;
      base.actionsError += overview.metrics.actions_error;
      base.actionsSkipped += overview.metrics.actions_skipped;

      for (const [eventType, count] of Object.entries(overview.metrics.event_type_counts)) {
        base.eventTypes.set(eventType, (base.eventTypes.get(eventType) ?? 0) + count);
      }

      for (const [status, count] of Object.entries(overview.metrics.status_counts)) {
        base.decisionStatuses.set(status, (base.decisionStatuses.get(status) ?? 0) + count);
      }
    }

    return base;
  }, [bots, overviewByBot]);

  const rankedBots = useMemo(() => {
    const performanceBots = bots.filter((bot) => bot.performance);
    return [...performanceBots].sort(
      (left, right) => (right.performance?.pnl_total_pct ?? 0) - (left.performance?.pnl_total_pct ?? 0),
    );
  }, [bots]);

  const maxAbsPnlPct = useMemo(
    () =>
      rankedBots.reduce(
        (maximum, bot) => Math.max(maximum, Math.abs(bot.performance?.pnl_total_pct ?? 0)),
        0,
      ) || 1,
    [rankedBots],
  );

  const exposureBySymbol = useMemo(() => {
    const symbols = new Map<
      string,
      {
        symbol: string;
        positions: number;
        bots: Set<string>;
        longs: number;
        shorts: number;
        approximateNotional: number;
        unrealizedPnl: number;
      }
    >();

    for (const entry of openPositions) {
      const current =
        symbols.get(entry.position.symbol) ??
        {
          symbol: entry.position.symbol,
          positions: 0,
          bots: new Set<string>(),
          longs: 0,
          shorts: 0,
          approximateNotional: 0,
          unrealizedPnl: 0,
        };

      current.positions += 1;
      current.bots.add(entry.botName);
      current.approximateNotional += Math.abs(entry.position.amount * entry.position.mark_price);
      current.unrealizedPnl += entry.position.unrealized_pnl;
      if (entry.position.side.toLowerCase().includes("short")) {
        current.shorts += 1;
      } else {
        current.longs += 1;
      }

      symbols.set(entry.position.symbol, current);
    }

    return [...symbols.values()]
      .sort((left, right) => right.approximateNotional - left.approximateNotional)
      .slice(0, 8);
  }, [openPositions]);

  const maxNotional = useMemo(
    () => exposureBySymbol.reduce((maximum, item) => Math.max(maximum, item.approximateNotional), 0) || 1,
    [exposureBySymbol],
  );

  const failurePressure = useMemo(() => {
    const reasons = new Map<string, { reason: string; count: number; bots: Set<string> }>();

    for (const bot of bots) {
      const overview = overviewByBot[bot.id];
      if (!overview) {
        continue;
      }

      for (const failure of overview.metrics.failure_reasons) {
        const current =
          reasons.get(failure.reason) ?? {
            reason: failure.reason,
            count: 0,
            bots: new Set<string>(),
          };
        current.count += failure.count;
        current.bots.add(bot.name);
        reasons.set(failure.reason, current);
      }
    }

    return [...reasons.values()].sort((left, right) => right.count - left.count).slice(0, 6);
  }, [bots, overviewByBot]);

  const maxFailureCount = useMemo(
    () => failurePressure.reduce((maximum, item) => Math.max(maximum, item.count), 0) || 1,
    [failurePressure],
  );

  const healthMatrix = useMemo(
    () =>
      bots
        .filter((bot) => bot.runtime)
        .map((bot) => {
          const overview = overviewByBot[bot.id];
          return {
            id: bot.id,
            name: bot.name,
            status: getFleetBotStatus(bot),
            health: overview?.health.health ?? "unknown",
            successRate: overview ? overview.metrics.success_rate * 100 : null,
            actions: overview?.metrics.actions_total ?? 0,
            errors: overview?.metrics.actions_error ?? 0,
            heartbeatAgeSeconds: overview?.health.heartbeat_age_seconds ?? null,
          };
        })
        .sort((left, right) => {
          const leftPenalty = (left.errors > 0 ? 2 : 0) + (left.heartbeatAgeSeconds && left.heartbeatAgeSeconds > 120 ? 1 : 0);
          const rightPenalty = (right.errors > 0 ? 2 : 0) + (right.heartbeatAgeSeconds && right.heartbeatAgeSeconds > 120 ? 1 : 0);
          if (leftPenalty !== rightPenalty) {
            return rightPenalty - leftPenalty;
          }
          return (right.actions ?? 0) - (left.actions ?? 0);
        }),
    [bots, overviewByBot],
  );

  const eventMix = useMemo(
    () => [...aggregate.eventTypes.entries()].sort((left, right) => right[1] - left[1]).slice(0, 8),
    [aggregate.eventTypes],
  );

  const decisionMix = useMemo(
    () => [...aggregate.decisionStatuses.entries()].sort((left, right) => right[1] - left[1]),
    [aggregate.decisionStatuses],
  );

  const maxEventCount = useMemo(
    () => eventMix.reduce((maximum, [, count]) => Math.max(maximum, count), 0) || 1,
    [eventMix],
  );

  const actionSuccessRate =
    aggregate.actionsTotal > 0 ? (aggregate.actionsSuccess / aggregate.actionsTotal) * 100 : null;

  return (
    <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">
      <section className="flex flex-wrap items-end justify-between gap-4 border-b border-[rgba(255,255,255,0.08)] pb-6 md:pb-8">
        <div className="grid gap-2">
          <h1 className="font-mono text-[clamp(2rem,4vw,2.8rem)] font-bold uppercase tracking-tight text-neutral-50">
            Analytics
          </h1>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400">
            Compare fleet performance, exposure concentration, action quality, and failure pressure.
          </p>
        </div>
      </section>

      {!authenticated ? (
        <article className="flex flex-wrap items-center justify-between gap-4 rounded-[1.8rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-5">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">Sign in required</span>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400">
              Connect the wallet tied to your bots to load cross-bot performance, action quality, and runtime observability analytics.
            </p>
          </div>
          <button
            type="button"
            onClick={login}
            className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
          >
            Sign in to open analytics
          </button>
        </article>
      ) : null}

      {error ? (
        <article className="rounded-[1.6rem] border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SignalCard
          icon={<TrendingUp className="h-4 w-4" />}
          label="Realized PnL"
          value={formatSignedUsd(aggregate.realized)}
          tone={aggregate.realized >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}
          detail="Closed trade contribution across the fleet"
        />
        <SignalCard
          icon={<Gauge className="h-4 w-4" />}
          label="Unrealized PnL"
          value={formatSignedUsd(aggregate.unrealized)}
          tone={aggregate.unrealized >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}
          detail="Live mark-to-market pressure"
        />
        <SignalCard
          icon={<Activity className="h-4 w-4" />}
          label="Errors"
          value={`${aggregate.actionsError}`}
          tone={aggregate.actionsError > 0 ? "text-[#dce85d]" : "text-[#74b97f]"}
          detail="Runtime action errors recorded in the 24h window"
        />
        <SignalCard
          icon={<Layers3 className="h-4 w-4" />}
          label="Skipped"
          value={`${aggregate.actionsSkipped}`}
          tone="text-neutral-50"
          detail="Deliberate non-actions in the current window"
        />
      </section>

      {sessionActive && !loading && bots.length === 0 ? (
        <article className="grid gap-3 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-6 py-8">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">Analytics need data</span>
          <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
            There are no bots or runtimes to analyze yet
          </h2>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            Create or deploy at least one bot first. Once the system has runtime and trade data, this page will light up with ranked performance and observability signals.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Link
              href="/builder"
              className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
            >
              Open builder
            </Link>
            <Link
              href="/dashboard"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50"
            >
              Open dashboard
            </Link>
          </div>
        </article>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)] xl:items-start">
        <div className="grid gap-6">
        <article className="grid gap-4 self-start rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#74b97f]">
                Performance ladder
              </span>
              <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                Rank every bot by return
              </h2>
            </div>
            <button
              type="button"
              onClick={refresh}
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
            >
              Refresh
            </button>
          </div>

          {loading || (loadingPositions && rankedBots.length === 0) ? (
            <div className="grid gap-3">
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
            </div>
          ) : rankedBots.length === 0 ? (
            <div className="rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-6 text-sm leading-7 text-neutral-400">
              No performance data yet. Bots will show up here once they have runtime PnL or position data attached.
            </div>
          ) : (
            <div className="grid gap-3">
              {rankedBots.slice(0, 10).map((bot, index) => {
                const percent = bot.performance?.pnl_total_pct ?? 0;
                const width = percentWidth(Math.abs(percent), maxAbsPnlPct);
                return (
                  <article
                    key={bot.id}
                    className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="grid gap-1">
                        <div className="flex items-center gap-2">
                          <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-2 py-0.5 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
                            #{index + 1}
                          </span>
                          <Link
                            href={`/bots/${bot.id}`}
                            className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50 transition hover:text-[#dce85d]"
                          >
                            {bot.name}
                          </Link>
                        </div>
                        <div className="text-sm text-neutral-400">
                          {bot.performance?.positions.length ?? 0} open trades • {getFleetBotStatus(bot)}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`font-mono text-xl font-bold uppercase tracking-tight ${percent >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}`}>
                          {formatSignedPct(percent)}
                        </div>
                        <div className="text-sm text-neutral-400">{formatSignedUsd(bot.performance?.pnl_total ?? 0)}</div>
                      </div>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
                      <div
                        className={`h-full rounded-full ${percent >= 0 ? "bg-[#74b97f]" : "bg-[#dce85d]"}`}
                        style={{ width: `${width}%` }}
                      />
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </article>

        <article className="grid gap-4 self-start rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">
              Action quality
            </span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              Fleet decision mix
            </h2>
          </div>

          <ActionStrip
            label="Success"
            tone="bg-[#74b97f]"
            value={aggregate.actionsSuccess}
            total={aggregate.actionsTotal}
          />
          <ActionStrip
            label="Errors"
            tone="bg-[#dce85d]"
            value={aggregate.actionsError}
            total={aggregate.actionsTotal}
          />
          <ActionStrip
            label="Skipped"
            tone="bg-[#7f8790]"
            value={aggregate.actionsSkipped}
            total={aggregate.actionsTotal}
          />

          <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
            <div className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">
              Status distribution
            </div>
            {decisionMix.length === 0 ? (
              <div className="text-sm leading-6 text-neutral-400">
                No decision status data yet.
              </div>
            ) : (
              <div className="grid gap-2">
                {decisionMix.map(([status, count]) => (
                  <div key={status} className="flex items-center justify-between gap-3 text-sm text-neutral-300">
                    <span className="uppercase tracking-[0.12em] text-neutral-500">{status}</span>
                    <span className="font-mono font-bold">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
            <div className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">
              Event mix
            </div>
            {eventMix.length === 0 ? (
              <div className="text-sm leading-6 text-neutral-400">
                No event type data yet.
              </div>
            ) : (
              <div className="grid gap-2">
                {eventMix.map(([eventType, count]) => (
                  <div key={eventType} className="grid gap-1">
                    <div className="flex items-center justify-between gap-3 text-sm text-neutral-300">
                      <span className="uppercase tracking-[0.12em] text-neutral-500">{eventType}</span>
                      <span className="font-mono font-bold">{count}</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
                      <div
                        className="h-full rounded-full bg-[#74b97f]"
                        style={{ width: `${percentWidth(count, maxEventCount)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </article>

        <article className="grid gap-4 self-start rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">
              Failure pressure
            </span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              Most common failure reasons
            </h2>
          </div>

          {loading || (loadingOverviews && failurePressure.length === 0) ? (
            <div className="grid gap-3">
              <div className="skeleton h-20 w-full rounded-[1.5rem]" />
              <div className="skeleton h-20 w-full rounded-[1.5rem]" />
              <div className="skeleton h-20 w-full rounded-[1.5rem]" />
            </div>
          ) : failurePressure.length === 0 ? (
            <div className="rounded-[1.5rem] border border-[#74b97f]/20 bg-[#74b97f]/8 px-5 py-6 text-sm leading-7 text-neutral-300">
              No recurring runtime failures are showing up in the current observability window.
            </div>
          ) : (
            <div className="grid gap-3">
              {failurePressure.map((item) => (
                <article
                  key={item.reason}
                  className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="grid gap-1">
                      <div className="inline-flex items-center gap-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d]">
                        <TriangleAlert className="h-3.5 w-3.5" />
                        Failure reason
                      </div>
                      <div className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
                        {item.reason}
                      </div>
                    </div>
                    <div className="font-mono text-lg font-bold uppercase tracking-tight text-[#dce85d]">
                      {item.count}
                    </div>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
                    <div
                      className="h-full rounded-full bg-[#dce85d]"
                      style={{ width: `${percentWidth(item.count, maxFailureCount)}%` }}
                    />
                  </div>
                  <div className="text-sm text-neutral-400">
                    Affecting {item.bots.size} bot{item.bots.size === 1 ? "" : "s"}: {[...item.bots].slice(0, 3).join(", ")}
                    {item.bots.size > 3 ? ` +${item.bots.size - 3} more` : ""}
                  </div>
                </article>
              ))}
            </div>
          )}
        </article>
        </div>

        <div className="grid gap-6">
        <article className="grid gap-4 self-start rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">
              Exposure concentration
            </span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              Which markets dominate current risk
            </h2>
          </div>

          {loading || (loadingPositions && exposureBySymbol.length === 0) ? (
            <div className="grid gap-3">
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
            </div>
          ) : exposureBySymbol.length === 0 ? (
            <div className="rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-6 text-sm leading-7 text-neutral-400">
              No open symbol exposure right now. Once bots are holding trades, this section will rank concentration by approximate notional and current live PnL.
            </div>
          ) : (
            <div className="grid gap-3">
              {exposureBySymbol.map((item) => (
                <article
                  key={item.symbol}
                  className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4"
                >
                  <div className="flex flex-wrap items-end justify-between gap-3">
                    <div className="grid gap-1">
                      <div className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
                        {item.symbol}
                      </div>
                      <div className="text-sm text-neutral-400">
                        {item.positions} position{item.positions === 1 ? "" : "s"} across {item.bots.size} bot{item.bots.size === 1 ? "" : "s"}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
                        {formatUsd(item.approximateNotional)}
                      </div>
                      <div className={`text-sm ${item.unrealizedPnl >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}`}>
                        {formatSignedUsd(item.unrealizedPnl)}
                      </div>
                    </div>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
                    <div
                      className="h-full rounded-full bg-[linear-gradient(90deg,#dce85d_0%,#74b97f_100%)]"
                      style={{ width: `${percentWidth(item.approximateNotional, maxNotional)}%` }}
                    />
                  </div>
                  <div className="flex flex-wrap gap-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
                    <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-2.5 py-1">
                      long {item.longs}
                    </span>
                    <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-2.5 py-1">
                      short {item.shorts}
                    </span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </article>

        <article className="grid gap-4 self-start rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#74b97f]">
              Runtime health matrix
            </span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              Which bots are clean and which are noisy
            </h2>
          </div>

          {loading || (loadingOverviews && healthMatrix.length === 0) ? (
            <div className="grid gap-3">
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
              <div className="skeleton h-24 w-full rounded-[1.5rem]" />
            </div>
          ) : healthMatrix.length === 0 ? (
            <div className="rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-6 text-sm leading-7 text-neutral-400">
              No runtime health data yet. Deploy a bot to start building the observability matrix.
            </div>
          ) : (
            <div className="grid gap-3">
              {healthMatrix.map((row) => (
                <article
                  key={row.id}
                  className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="grid gap-1">
                      <Link
                        href={`/bots/${row.id}`}
                        className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50 transition hover:text-[#dce85d]"
                      >
                        {row.name}
                      </Link>
                      <div className="text-sm text-neutral-400">
                        {row.status} • {row.health}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-mono text-lg font-bold uppercase tracking-tight ${row.errors > 0 ? "text-[#dce85d]" : "text-[#74b97f]"}`}>
                        {row.successRate != null ? `${row.successRate.toFixed(1)}%` : "--"}
                      </div>
                      <div className="text-sm text-neutral-400">{row.actions} actions</div>
                    </div>
                  </div>
                  <div className="grid gap-3 md:grid-cols-3">
                    <MatrixCell label="Heartbeat" value={formatHeartbeat(row.heartbeatAgeSeconds)} />
                    <MatrixCell label="Errors" value={`${row.errors}`} tone={row.errors > 0 ? "text-[#dce85d]" : "text-neutral-50"} />
                    <MatrixCell label="Success" value={row.successRate != null ? `${row.successRate.toFixed(1)}%` : "--"} tone={row.successRate != null && row.successRate >= 80 ? "text-[#74b97f]" : "text-neutral-50"} />
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
                    <div
                      className={`h-full rounded-full ${row.errors > 0 ? "bg-[#dce85d]" : "bg-[#74b97f]"}`}
                      style={{ width: `${row.successRate != null ? Math.max(6, Math.min(100, row.successRate)) : 6}%` }}
                    />
                  </div>
                </article>
              ))}
            </div>
          )}
        </article>

        <article className="grid gap-4 self-start rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">
              Reading guide
            </span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              What these analytics are telling you
            </h2>
          </div>

          <div className="grid gap-3">
            <GuideCard
              icon={<Bot className="h-4 w-4" />}
              title="Performance ladder"
              body="Ranks bots by current return, so you can see whether one runtime is carrying the fleet or multiple bots are performing consistently."
            />
            <GuideCard
              icon={<ShieldAlert className="h-4 w-4" />}
              title="Health matrix"
              body="Puts success rate, action volume, error counts, and heartbeat freshness in one line per bot. A noisy runtime becomes obvious fast."
            />
            <GuideCard
              icon={<Layers3 className="h-4 w-4" />}
              title="Exposure concentration"
              body="Shows where current risk is clustering by symbol. If several bots are leaning into the same market, you can see that concentration immediately."
            />
          </div>
        </article>
        </div>
      </section>
    </main>
  );
}

function SignalCard({
  detail,
  icon,
  label,
  tone,
  value,
}: {
  detail: string;
  icon: ReactNode;
  label: string;
  tone: string;
  value: string;
}) {
  return (
    <article className="grid gap-3 rounded-[1.7rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">{label}</span>
        <div className="text-neutral-500">{icon}</div>
      </div>
      <div className={`font-mono text-3xl font-bold uppercase tracking-tight ${tone}`}>{value}</div>
      <p className="text-sm leading-6 text-neutral-400">{detail}</p>
    </article>
  );
}

function ActionStrip({
  label,
  tone,
  total,
  value,
}: {
  label: string;
  tone: string;
  total: number;
  value: number;
}) {
  return (
    <div className="grid gap-2 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">{label}</span>
        <span className="font-mono text-sm font-bold uppercase tracking-tight text-neutral-50">
          {value} / {total}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${percentWidth(value, total)}%` }} />
      </div>
    </div>
  );
}

function MatrixCell({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: string;
  value: string;
}) {
  return (
    <div className="grid gap-1 rounded-[1rem] border border-[rgba(255,255,255,0.06)] bg-[#111315] px-3 py-3">
      <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</div>
      <div className={`font-mono text-sm font-bold uppercase tracking-tight ${tone ?? "text-neutral-50"}`}>
        {value}
      </div>
    </div>
  );
}

function GuideCard({
  body,
  icon,
  title,
}: {
  body: string;
  icon: ReactNode;
  title: string;
}) {
  return (
    <article className="grid gap-2 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4">
      <div className="inline-flex items-center gap-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d]">
        {icon}
        {title}
      </div>
      <p className="text-sm leading-7 text-neutral-400">{body}</p>
    </article>
  );
}
