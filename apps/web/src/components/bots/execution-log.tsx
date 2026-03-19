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

type DisplayEvent = BotExecutionEvent & {
  grouped_count: number;
  grouped_until: string;
};

function summarizeAction(event: BotExecutionEvent) {
  const actionType = typeof event.request_payload.type === "string" ? event.request_payload.type : event.event_type;
  const symbol = typeof event.request_payload.symbol === "string" ? event.request_payload.symbol : null;
  const leverage = typeof event.request_payload.leverage === "number" ? `${event.request_payload.leverage}x` : null;
  const sizeUsd =
    typeof event.request_payload.size_usd === "number" ? `$${event.request_payload.size_usd.toFixed(0)}` : null;
  return [actionType, symbol, leverage, sizeUsd].filter(Boolean).join(" / ");
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

function buildEventSignature(event: BotExecutionEvent) {
  return JSON.stringify({
    event_type: event.event_type,
    status: event.status,
    decision_summary: event.decision_summary,
    error_reason: event.error_reason ?? null,
    request_payload: event.request_payload,
    result_payload: event.result_payload,
  });
}

function collapseEvents(events: BotExecutionEvent[]): DisplayEvent[] {
  const collapsed: DisplayEvent[] = [];

  for (const event of events) {
    const previous = collapsed[collapsed.length - 1];
    const isRepeatSkip =
      previous &&
      event.event_type === "action.skipped" &&
      previous.event_type === "action.skipped" &&
      buildEventSignature(previous) === buildEventSignature(event);

    if (isRepeatSkip) {
      previous.grouped_count += 1;
      previous.grouped_until = event.created_at;
      continue;
    }

    collapsed.push({
      ...event,
      grouped_count: 1,
      grouped_until: event.created_at,
    });
  }

  return collapsed;
}

function renderOutcome(event: DisplayEvent) {
  const summary =
    event.error_reason ??
    (Object.keys(event.result_payload).length > 0 ? JSON.stringify(event.result_payload) : "No additional payload recorded.");

  if (event.grouped_count <= 1) {
    return summary;
  }

  return `${summary} Collapsed ${event.grouped_count} repeated checks into one item.`;
}

export function ExecutionLog({ events }: { events: BotExecutionEvent[] }) {
  if (!events.length) {
    return (
      <div className="rounded-[1.6rem] bg-[#16181a] px-5 py-6 text-sm leading-6 text-neutral-400">
        Runtime activity will appear here once the bot deploys, evaluates the market, and starts making decisions.
      </div>
    );
  }

  const displayEvents = collapseEvents(events);

  return (
    <div className="grid gap-3">
      {displayEvents.map((event, index) => (
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
              {event.grouped_count > 1 ? (
                <span className="rounded-full border border-[rgba(220,232,93,0.18)] bg-[#dce85d]/10 px-2.5 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d]">
                  {event.grouped_count} similar checks
                </span>
              ) : null}
              <span className="text-[0.68rem] text-neutral-500">{new Date(event.created_at).toLocaleString()}</span>
              {event.grouped_count > 1 ? (
                <span className="text-[0.68rem] text-neutral-600">through {new Date(event.grouped_until).toLocaleString()}</span>
              ) : null}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-[minmax(0,1.3fr)_minmax(0,0.9fr)]">
            <div className="rounded-2xl bg-[#0f1112] px-4 py-3">
              <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Decision</div>
              <div className="mt-2 break-all text-sm leading-6 text-neutral-300">
                {event.grouped_count > 1 ? `Repeated ${event.grouped_count} times. ` : ""}
                {event.decision_summary}
              </div>
            </div>

            <div className="rounded-2xl bg-[#0f1112] px-4 py-3">
              <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Outcome</div>
              <div className="mt-2 break-all text-sm leading-6 text-neutral-300">{renderOutcome(event)}</div>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
