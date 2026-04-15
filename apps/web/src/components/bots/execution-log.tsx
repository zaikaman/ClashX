import { useMemo } from "react";

import { formatRuntimeEventType } from "@/lib/runtime-events";

type BotExecutionEvent = {
  id: string;
  runtime_id: string;
  event_type: string;
  decision_summary: string;
  action_type?: string | null;
  symbol?: string | null;
  leverage?: number | null;
  size_usd?: number | null;
  status: string;
  error_reason?: string | null;
  outcome_summary: string;
  created_at: string;
};

type DisplayEvent = BotExecutionEvent & {
  grouped_count: number;
  grouped_until: string;
};

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

const currencyFormatter = new Intl.NumberFormat(undefined, {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function describeActionType(actionType: string, symbol: string | null) {
  const market = symbol ? ` on ${symbol}` : "";
  if (actionType === "open_long") {
    return `Open long${market}`;
  }
  if (actionType === "open_short") {
    return `Open short${market}`;
  }
  if (actionType === "set_tpsl") {
    return `Set TP/SL${market}`;
  }
  if (actionType === "close_position") {
    return `Close position${market}`;
  }
  if (actionType === "update_leverage") {
    return `Update leverage${market}`;
  }
  if (actionType === "place_market_order") {
    return `Place market order${market}`;
  }
  if (actionType === "place_limit_order") {
    return `Place limit order${market}`;
  }
  if (actionType === "place_twap_order") {
    return `Place TWAP order${market}`;
  }
  return actionType.replace(/_/g, " ");
}

function summarizeAction(event: BotExecutionEvent) {
  const actionType = typeof event.action_type === "string" ? event.action_type : null;
  if (!actionType) {
    return "";
  }
  const symbol = typeof event.symbol === "string" ? event.symbol : null;
  const actionLabel = describeActionType(actionType, symbol);
  const leverage = typeof event.leverage === "number" ? `${event.leverage}x leverage` : null;
  const sizeUsd = typeof event.size_usd === "number" ? `${currencyFormatter.format(event.size_usd)} notional` : null;
  return [actionLabel, leverage, sizeUsd].filter(Boolean).join(" • ");
}

function statusTone(status: string) {
  if (status === "success") {
    return "border-[#74b97f]/25 bg-[#74b97f]/10 text-[#a9d7b1]";
  }
  if (status === "skipped") {
    return "border-[#dce85d]/25 bg-[#dce85d]/10 text-[#f0f4be]";
  }
  if (status === "error") {
    return "border-[#ff8d7a]/25 bg-[#ff8d7a]/10 text-[#ffd0c7]";
  }
  return "border-[rgba(255,255,255,0.08)] bg-[#0f1112] text-neutral-300";
}

function buildEventSignature(event: BotExecutionEvent) {
  return [
    event.event_type,
    event.status,
    event.decision_summary,
    event.error_reason ?? "",
    event.action_type ?? "",
    event.symbol ?? "",
    event.leverage?.toString() ?? "",
    event.size_usd?.toString() ?? "",
    event.outcome_summary,
  ].join("|");
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
  const summary = event.outcome_summary;

  if (event.grouped_count <= 1) {
    return summary;
  }

  return `${summary} ${event.grouped_count} repeated evaluations were collapsed into this single entry.`;
}

function formatTimestamp(value: string) {
  return dateTimeFormatter.format(new Date(value));
}

export function ExecutionLog({ events }: { events: BotExecutionEvent[] }) {
  const displayEvents = useMemo(() => collapseEvents(events), [events]);

  if (!events.length) {
    return (
      <div className="rounded-[1.6rem] bg-[#16181a] px-5 py-6 text-sm leading-6 text-neutral-400">
        Runtime activity will appear here once the bot deploys, evaluates the market, and starts making decisions.
      </div>
    );
  }

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
              <div className="font-mono text-base font-bold uppercase tracking-tight text-neutral-50">{formatRuntimeEventType(event.event_type)}</div>
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
              <span className="text-[0.68rem] text-neutral-500">{formatTimestamp(event.created_at)}</span>
              {event.grouped_count > 1 ? (
                <span className="text-[0.68rem] text-neutral-600">through {formatTimestamp(event.grouped_until)}</span>
              ) : null}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-[minmax(0,1.3fr)_minmax(0,0.9fr)]">
            <div className="rounded-2xl bg-[#0f1112] px-4 py-3">
              <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
                {event.event_type.startsWith("action.") ? "Attempt" : "Decision"}
              </div>
              <div className="mt-2 break-all text-sm leading-6 text-neutral-300">
                {event.grouped_count > 1 ? `Repeated ${event.grouped_count} times. ` : ""}
                {event.decision_summary}
              </div>
            </div>

            <div className="rounded-2xl bg-[#0f1112] px-4 py-3">
              <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Outcome</div>
              <div className="mt-2 text-sm leading-6 text-neutral-300">{renderOutcome(event)}</div>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
