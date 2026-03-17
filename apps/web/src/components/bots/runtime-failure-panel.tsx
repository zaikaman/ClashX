"use client";

import { useEffect, useState } from "react";

type RuntimeMetrics = {
  failure_reasons: Array<{ reason: string; count: number }>;
  recent_failures: Array<{
    id: string;
    event_type: string;
    error_reason: string;
    decision_summary: string;
    created_at: string;
  }>;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function RuntimeFailurePanel({
  botId,
  walletAddress,
  getAuthHeaders,
  refreshToken,
}: {
  botId: string;
  walletAddress: string;
  getAuthHeaders: (headersInit?: HeadersInit) => Promise<Headers>;
  refreshToken: number;
}) {
  const [metrics, setMetrics] = useState<RuntimeMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadFailureData() {
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/bots/${botId}/metrics?wallet_address=${encodeURIComponent(walletAddress)}`,
          { cache: "no-store", headers: await getAuthHeaders() },
        );
        const payload = (await response.json()) as RuntimeMetrics | { detail?: string };
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Could not load failure metrics" : "Could not load failure metrics");
        }
        setMetrics(payload as RuntimeMetrics);
        setError(null);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load failure metrics");
      }
    }

    void loadFailureData();
  }, [botId, walletAddress, getAuthHeaders, refreshToken]);

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
