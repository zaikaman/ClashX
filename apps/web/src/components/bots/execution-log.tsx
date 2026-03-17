type BotExecutionEvent = {
  id: string;
  runtime_id: string;
  event_type: string;
  decision_summary: string;
  request_payload: Record<string, unknown>;
  result_payload: Record<string, unknown>;
  status: string;
  error_reason?: string | null;
  created_at: string;
};

export function ExecutionLog({ events }: { events: BotExecutionEvent[] }) {
  if (!events.length) {
    return (
      <div className="bg-[#16181a] px-5 py-6 text-sm leading-6 text-neutral-400">
        No runtime events yet. Deploy or resume the bot to stream execution events.
      </div>
    );
  }

  return (
    <div className="grid gap-1.5">
      {events.map((event, index) => (
        <article
          key={event.id}
          className="stagger-in grid gap-2 bg-[#16181a] px-4 py-3.5 md:grid-cols-[0.7fr_1fr_0.6fr_1.2fr] md:items-center"
          style={{ animationDelay: `${index * 30}ms` }}
        >
          <div>
            <div className="font-mono text-base font-bold uppercase tracking-tight">{event.event_type}</div>
            <div className="label text-[0.58rem] truncate max-w-[180px]">{event.runtime_id}</div>
          </div>
          <div className="text-sm text-neutral-400 truncate">{event.decision_summary}</div>
          <span
            className={`inline-flex w-fit rounded-full px-2.5 py-0.5 text-[0.6rem] font-semibold uppercase tracking-wider ${
              event.status === "success"
                ? "bg-[color:var(--mint-dim)] text-[#74b97f]"
                : event.status === "error"
                  ? "bg-[color:oklch(0.30_0.08_28)] text-[#dce85d]"
                  : "bg-neutral-900 text-neutral-400"
            }`}
          >
            {event.status}
          </span>
          <div className="text-xs text-neutral-500">
            {event.error_reason ?? new Date(event.created_at).toLocaleString()}
          </div>
        </article>
      ))}
    </div>
  );
}
