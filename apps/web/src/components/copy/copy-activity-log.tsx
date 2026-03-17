type CopyActivity = {
  id?: string;
  symbol: string;
  side: string;
  size_source: number;
  size_mirrored: number;
  status: string;
  error_reason?: string | null;
  created_at?: string | null;
};

export function CopyActivityLog({ events }: { events: CopyActivity[] }) {
  if (!events.length) {
    return (
      <div className="bg-[#16181a] px-5 py-6 text-sm leading-6 text-neutral-400">
        No mirrored actions yet. Once the source bot moves, copy events will appear here.
      </div>
    );
  }

  return (
    <div className="grid gap-1.5">
      {events.map((event, index) => (
        <article
          key={event.id ?? `${event.symbol}-${index}`}
          className="stagger-in grid gap-3 bg-[#16181a] px-4 py-3.5 md:grid-cols-[0.8fr_1fr_0.5fr_1.2fr] md:items-center"
          style={{ animationDelay: `${index * 40}ms` }}
        >
          <div>
            <div className="font-mono text-lg font-bold uppercase tracking-tight">{event.symbol}</div>
            <div className="label text-[0.58rem]">{event.side}</div>
          </div>
          <div className="text-sm text-neutral-400">
            {event.size_source.toFixed(3)} → {event.size_mirrored.toFixed(3)}
          </div>
          <span className={`inline-flex w-fit rounded-full px-2.5 py-0.5 text-[0.6rem] font-semibold uppercase tracking-wider ${event.status === "filled" || event.status === "mirrored"
              ? "bg-[color:var(--mint-dim)] text-[#74b97f]"
              : event.status === "failed"
                ? "bg-[color:oklch(0.30_0.08_28)] text-[#dce85d]"
                : "bg-neutral-900 text-neutral-400"
            }`}>
            {event.status}
          </span>
          <div className="text-xs text-neutral-500">
            {event.error_reason ?? (event.created_at ? new Date(event.created_at).toLocaleString() : "Awaiting timestamp")}
          </div>
        </article>
      ))}
    </div>
  );
}
