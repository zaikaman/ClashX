"use client";

import type { RuntimeMetrics } from "@/lib/runtime-overview";

export function RuntimeFailurePanel({
  metrics,
  error,
}: {
  metrics: RuntimeMetrics | null;
  error?: string | null;
}) {
  return (
    <section className="grid gap-4 border-l-2 border-[#dce85d] bg-[#16181a] p-6">
      <div className="flex items-center justify-between">
        <span className="label text-[#dce85d]">failure review + recovery</span>
        <span className="text-xs text-neutral-500">latest errors</span>
      </div>

      {error ? <p className="text-sm text-[#dce85d]">{error}</p> : null}

      <article className="grid gap-2 bg-[#090a0a] p-4">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">top failure reasons</span>
        {metrics?.failure_reasons?.length ? (
          metrics.failure_reasons.map((item) => (
            <div key={item.reason} className="flex items-center justify-between text-sm text-neutral-400">
              <span className="truncate pr-3">{item.reason}</span>
              <span className="font-semibold text-[#dce85d]">{item.count}</span>
            </div>
          ))
        ) : (
          <p className="text-sm text-neutral-400">No failure reasons recorded in the current window.</p>
        )}
      </article>

      <article className="grid gap-2 bg-[#090a0a] p-4">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">recent failure events</span>
        {metrics?.recent_failures?.length ? (
          metrics.recent_failures.slice(0, 6).map((failure) => (
            <div key={failure.id} className="grid gap-1 border-b border-[rgba(255,255,255,0.06)] pb-2 text-sm text-neutral-400 last:border-b-0">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs font-bold uppercase tracking-wider">{failure.event_type}</span>
                <span className="text-[0.68rem] text-neutral-500">{new Date(failure.created_at).toLocaleString()}</span>
              </div>
              <div className="text-[#dce85d]">{failure.error_reason}</div>
              <div className="text-xs text-neutral-500 truncate">{failure.decision_summary}</div>
            </div>
          ))
        ) : (
          <p className="text-sm text-neutral-400">No recent runtime failures.</p>
        )}
      </article>
    </section>
  );
}
