"use client";

import type { RuntimeHealth, RuntimeMetrics } from "@/lib/runtime-overview";

export function RuntimeHealthCard({
  health,
  metrics,
  error,
}: {
  health: RuntimeHealth | null;
  metrics: RuntimeMetrics | null;
  error?: string | null;
}) {
  return (
    <section className="grid gap-4 border-l-2 border-[#74b97f] bg-[#16181a] p-6">
      <div className="flex items-center justify-between">
        <span className="label text-[#74b97f]">runtime health + metrics</span>
        <span className="text-xs text-neutral-500">window: 24h</span>
      </div>

      {error ? <p className="text-sm text-[#dce85d]">{error}</p> : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <article className="grid gap-1 bg-[#090a0a] p-4">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">health state</span>
          <span className="font-mono text-2xl font-bold uppercase">{health?.health ?? "--"}</span>
          <span className="text-xs text-neutral-500">
            heartbeat {health?.heartbeat_age_seconds != null ? `${health.heartbeat_age_seconds}s` : "--"}
          </span>
        </article>
        <article className="grid gap-1 bg-[#090a0a] p-4">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">success rate</span>
          <span className="font-mono text-2xl font-bold uppercase">
            {metrics ? `${(metrics.success_rate * 100).toFixed(1)}%` : "--"}
          </span>
          <span className="text-xs text-neutral-500">{metrics?.actions_success ?? 0}/{metrics?.actions_total ?? 0} actions</span>
        </article>
      </div>

      <div className="grid gap-2 text-sm text-neutral-400">
        <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.06)] pb-2">
          <span>status</span>
          <span className="uppercase">{health?.status ?? "--"}</span>
        </div>
        <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.06)] pb-2">
          <span>events (24h)</span>
          <span>{metrics?.events_total ?? 0}</span>
        </div>
        <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.06)] pb-2">
          <span>errors (24h)</span>
          <span>{metrics?.actions_error ?? 0}</span>
        </div>
        <div className="flex items-center justify-between">
          <span>uptime</span>
          <span>{metrics?.uptime_seconds != null ? `${Math.floor(metrics.uptime_seconds / 60)}m` : "--"}</span>
        </div>
      </div>

      <div className="grid gap-1 text-xs text-neutral-500">
        {(health?.reasons ?? []).slice(0, 2).map((reason) => (
          <p key={reason}>- {reason}</p>
        ))}
      </div>
    </section>
  );
}
