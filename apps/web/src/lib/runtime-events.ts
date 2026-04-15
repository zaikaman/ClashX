type RuntimeEventDescriptor = {
  decision_summary?: string | null;
  event_type: string;
  status?: string | null;
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  "action.executed": "Action executed",
  "action.failed": "Action failed",
  "action.skipped": "Action skipped",
  "runtime.active": "Runtime activated",
  "runtime.paused": "Runtime paused",
  "runtime.stopped": "Runtime stopped",
};

const TECHNICAL_SUMMARY_PATTERN = /^(idem:|[\w-]+:(?:[\w-]+:){2,}[\w-]+$)/i;

function toTitleCase(value: string) {
  return value
    .split(/[._-]+/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1).toLowerCase())
    .join(" ");
}

function normalizeEventType(eventType: string) {
  return eventType.trim().toLowerCase();
}

export function formatRuntimeEventType(eventType: string) {
  const normalized = normalizeEventType(eventType);
  if (EVENT_TYPE_LABELS[normalized]) {
    return EVENT_TYPE_LABELS[normalized];
  }
  return toTitleCase(normalized || "event");
}

function defaultRuntimeEventSummary(eventType: string, status?: string | null) {
  const normalizedType = normalizeEventType(eventType);
  const normalizedStatus = status?.trim().toLowerCase();

  if (normalizedType === "runtime.active") {
    return "Runtime transitioned to active trading.";
  }
  if (normalizedType === "runtime.paused") {
    return "Runtime paused new trading activity.";
  }
  if (normalizedType === "runtime.stopped") {
    return "Runtime stopped and will not place new trades.";
  }
  if (normalizedType === "action.executed") {
    return "Runtime completed a trading action successfully.";
  }
  if (normalizedType === "action.skipped") {
    return "Runtime skipped a trading action after its checks.";
  }
  if (normalizedType === "action.failed") {
    return "Runtime failed while carrying out a trading action.";
  }
  if (normalizedStatus === "success") {
    return "Runtime recorded a successful event.";
  }
  if (normalizedStatus === "skipped") {
    return "Runtime recorded a skipped event.";
  }
  if (normalizedStatus === "error") {
    return "Runtime recorded a failed event.";
  }
  return "Runtime recorded a new event.";
}

export function formatRuntimeEventSummary(event: RuntimeEventDescriptor) {
  const summary = event.decision_summary?.trim();
  if (!summary) {
    return defaultRuntimeEventSummary(event.event_type, event.status);
  }
  if (TECHNICAL_SUMMARY_PATTERN.test(summary) || (summary.length > 36 && !summary.includes(" "))) {
    return defaultRuntimeEventSummary(event.event_type, event.status);
  }
  return summary.charAt(0).toUpperCase() + summary.slice(1);
}
