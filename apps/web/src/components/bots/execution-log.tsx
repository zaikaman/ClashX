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

function summarizeAction(event: BotExecutionEvent) {
  const actionType = typeof event.request_payload.type === "string" ? event.request_payload.type : event.event_type;
  const symbol = typeof event.request_payload.symbol === "string" ? event.request_payload.symbol : null;
  const leverage = typeof event.request_payload.leverage === "number" ? `${event.request_payload.leverage}x` : null;
  const sizeUsd =
    typeof event.request_payload.size_usd === "number" ? `$${event.request_payload.size_usd.toFixed(0)}` : null;
  return [actionType, symbol, leverage, sizeUsd].filter(Boolean).join(" • ");
}

function statusTone(status: string) {
  if (status === "success") {
    return "border-[#74b97f]/25 bg-[#74b97f]/10 text-[#a9d7b1]";
  }
  if (status === "error") {
    return "border-[#dce85d]/25 bg-[#dce85d]/10 text-[#f0f4be]";
  }
  return "border-[rgba(255,255,255,0.08)] bg-[#0f1112] text-neutral-300";
}

export function ExecutionLog({ events }: { events: BotExecutionEvent[] }) {
  if (!events.length) {
    return (
      <div className="rounded-[1.6rem] bg-[#16181a] px-5 py-6 text-sm leading-6 text-neutral-400">
        Runtime activity will appear here once the bot deploys, evaluates the market, and starts making decisions.
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {events.map((event, index) => (
        <article
          key={event.id}
          className="stagger-in grid gap-4 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-4"
          style={{ animationDelay: `${index * 30}ms` }}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="grid gap-1">
              <div className="font-mono text-base font-bold uppercase tracking-tight text-neutral-50">{event.event_type}</div>
              <div className="text-sm text-neutral-400">{summarizeAction(event) || event.decision_summary}</div>
            </div>
            <div className="grid justify-items-end gap-2">
              <span
                className={`inline-flex rounded-full border px-2.5 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${statusTone(event.status)}`}
              >
                {event.status}
              </span>
              <span className="text-[0.68rem] text-neutral-500">{new Date(event.created_at).toLocaleString()}</span>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-[minmax(0,1.3fr)_minmax(0,0.9fr)]">
            <div className="rounded-2xl bg-[#0f1112] px-4 py-3">
              <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Decision</div>
              <div className="mt-2 break-all text-sm leading-6 text-neutral-300">{event.decision_summary}</div>
            </div>

            <div className="rounded-2xl bg-[#0f1112] px-4 py-3">
              <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Outcome</div>
              <div className="mt-2 break-all text-sm leading-6 text-neutral-300">
                {event.error_reason ??
                  (Object.keys(event.result_payload).length > 0
                    ? JSON.stringify(event.result_payload)
                    : "No additional payload recorded.")}
              </div>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
