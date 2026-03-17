"use client";

import type { StreamStatus } from "@/lib/sse-client";

const labelMap: Record<StreamStatus, string> = {
  connecting: "dialing live feed",
  live: "live pulse",
  stale: "catching up",
  offline: "offline",
};

export function RealtimeBadge({ status }: { status: StreamStatus }) {
  return (
    <div className="inline-flex items-center gap-2.5 rounded-full bg-neutral-900 px-4 py-2 text-xs font-medium uppercase tracking-wider text-neutral-400">
      <span
        className={`h-2 w-2 rounded-full ${status === "live"
            ? "bg-[#74b97f] pulse-live"
            : status === "connecting"
              ? "bg-[color:var(--text-faint)] pulse-live"
              : status === "stale"
                ? "bg-amber-500"
                : "bg-[color:var(--text-faint)]"
          }`}
      />
      <span>{labelMap[status]}</span>
    </div>
  );
}
