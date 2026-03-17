export type StreamStatus = "connecting" | "live" | "stale" | "offline";

export type StreamHandlers<T> = {
  onMessage: (payload: T) => void;
  onStatusChange?: (status: StreamStatus) => void;
};

export type UserStreamHandlers = {
  onRelationshipUpdate?: (payload: unknown) => void;
  onExecutionMirrored?: (payload: unknown) => void;
  onTradingAccountUpdate?: (payload: unknown) => void;
  onTradingOrderSubmitted?: (payload: unknown) => void;
  onTradingOrderCancelled?: (payload: unknown) => void;
  onStatusChange?: (status: StreamStatus) => void;
};

export function createLeagueStream<T>(url: string, handlers: StreamHandlers<T>) {
  const eventSource = new EventSource(url);
  handlers.onStatusChange?.("connecting");

  eventSource.addEventListener("leaderboard.update", (event) => {
    handlers.onStatusChange?.("live");
    handlers.onMessage(JSON.parse((event as MessageEvent).data) as T);
  });

  eventSource.addEventListener("heartbeat", () => {
    handlers.onStatusChange?.("live");
  });

  eventSource.onerror = () => {
    handlers.onStatusChange?.(eventSource.readyState === EventSource.CLOSED ? "offline" : "stale");
  };

  return () => eventSource.close();
}

export function createUserStream(url: string, handlers: UserStreamHandlers) {
  const eventSource = new EventSource(url);
  handlers.onStatusChange?.("connecting");

  eventSource.addEventListener("copy.relationship.updated", (event) => {
    handlers.onStatusChange?.("live");
    handlers.onRelationshipUpdate?.(JSON.parse((event as MessageEvent).data));
  });

  eventSource.addEventListener("copy.execution.mirrored", (event) => {
    handlers.onStatusChange?.("live");
    handlers.onExecutionMirrored?.(JSON.parse((event as MessageEvent).data));
  });

  eventSource.addEventListener("trading.account.updated", (event) => {
    handlers.onStatusChange?.("live");
    handlers.onTradingAccountUpdate?.(JSON.parse((event as MessageEvent).data));
  });

  eventSource.addEventListener("trading.order.submitted", (event) => {
    handlers.onStatusChange?.("live");
    handlers.onTradingOrderSubmitted?.(JSON.parse((event as MessageEvent).data));
  });

  eventSource.addEventListener("trading.order.cancelled", (event) => {
    handlers.onStatusChange?.("live");
    handlers.onTradingOrderCancelled?.(JSON.parse((event as MessageEvent).data));
  });

  eventSource.addEventListener("heartbeat", () => {
    handlers.onStatusChange?.("live");
  });

  eventSource.onerror = () => {
    handlers.onStatusChange?.(eventSource.readyState === EventSource.CLOSED ? "offline" : "stale");
  };

  return () => eventSource.close();
}
