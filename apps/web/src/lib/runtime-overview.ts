export type RuntimeHealth = {
  runtime_id: string | null;
  health: string;
  status: string;
  mode: string;
  last_runtime_update: string | null;
  last_event_at: string | null;
  heartbeat_age_seconds: number | null;
  error_rate_recent: number;
  reasons: string[];
};

export type RuntimeMetrics = {
  runtime_id: string;
  status: string;
  uptime_seconds: number | null;
  window_hours: number;
  events_total: number;
  actions_total: number;
  actions_success: number;
  actions_error: number;
  actions_skipped: number;
  success_rate: number;
  status_counts: Record<string, number>;
  event_type_counts: Record<string, number>;
  failure_reasons: Array<{ reason: string; count: number }>;
  recent_failures: Array<{
    id: string;
    event_type: string;
    error_reason: string;
    decision_summary: string;
    created_at: string;
  }>;
  last_event_at: string | null;
};

export type RuntimeOverview = {
  health: RuntimeHealth;
  metrics: RuntimeMetrics;
};
