"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import { ArrowUpRight, FlaskConical, History, LoaderCircle, Play, RefreshCcw } from "lucide-react";

import { useClashxAuth } from "@/lib/clashx-auth";
import type {
  BacktestAssumptionConfig,
  BacktestRunDetail,
  BacktestRunJobCreateResponse,
  BacktestRunJobProgress,
  BacktestRunJobStatusResponse,
  BacktestRunRequestPayload,
  BacktestRunSummary,
  BacktestTriggerEvent,
  BacktestsBootstrapPayload,
} from "@/lib/backtests";

type SavedBot = {
  id: string;
  name: string;
  description: string;
  strategy_type: string;
  market_scope: string;
  inferred_backtest_interval: string;
  updated_at: string;
};

type HistoryFilter = "all" | "completed" | "failed";
type HistoryScope = "all" | "selected";
type RunProgressState = {
  progress: number;
  stage: string;
  detail: string;
  interval: string;
  metrics?: Record<string, number | string>;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const INSPECTOR_PAGE_SIZE = 12;
const COMPARE_COLORS = ["#dce85d", "#74b97f", "#8ec5ff", "#f59e0b"];
const MAX_KLINE_CANDLES_PER_REQUEST = 4000;
const BACKTEST_JOB_POLL_VISIBLE_MS = 4000;
const BACKTEST_JOB_POLL_HIDDEN_MS = 12000;
const TIMEFRAME_TO_MS: Record<string, number> = {
  "1m": 60_000,
  "5m": 300_000,
  "15m": 900_000,
  "30m": 1_800_000,
  "1h": 3_600_000,
  "4h": 14_400_000,
  "1d": 86_400_000,
};
const DATE_PRESETS = [
  { id: "7d", label: "7D", days: 7 },
  { id: "30d", label: "30D", days: 30 },
  { id: "90d", label: "90D", days: 90 },
  { id: "custom", label: "Custom", days: 0 },
] as const;
const BacktestChart = dynamic(
  () => import("@/components/backtests/backtest-chart").then((mod) => mod.BacktestChart),
  {
    ssr: false,
    loading: () => <ChartPanelSkeleton />,
  },
);

function presetRange(days: number) {
  const end = new Date();
  const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

function formatMoney(value: number) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercent(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatBasisPoints(value: number) {
  return `${value.toFixed(2)} bps`;
}

function readNumericInput(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function toTimestampBounds(startDate: string, endDate: string) {
  const start = new Date(`${startDate}T00:00:00`).getTime();
  const end = new Date(`${endDate}T23:59:59.999`).getTime();
  return { start, end };
}

function clampNumber(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function toFiniteNumber(value: unknown, fallback: number) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function estimateBacktestWorkload(startDate: string, endDate: string, interval: string | null | undefined) {
  const { start, end } = toTimestampBounds(startDate, endDate);
  const resolvedInterval = interval && interval in TIMEFRAME_TO_MS ? interval : "15m";
  const intervalMs = TIMEFRAME_TO_MS[resolvedInterval];
  const estimatedBars = Math.max(1, Math.ceil((end - start + 1) / intervalMs));
  const estimatedRequests = Math.max(1, Math.ceil(estimatedBars / MAX_KLINE_CANDLES_PER_REQUEST));
  const estimatedDurationMs = clampNumber(3500 + estimatedRequests * 1800 + estimatedBars * 0.55, 5000, 28000);
  return {
    interval: resolvedInterval,
    estimatedBars,
    estimatedRequests,
    estimatedDurationMs,
  };
}

function toRunProgressState(progressPayload: BacktestRunJobProgress): RunProgressState {
  return {
    progress: clampNumber(toFiniteNumber(progressPayload.progress, 0), 0, 100),
    stage: String(progressPayload.stage ?? "").trim() || "Backtest update",
    detail: String(progressPayload.detail ?? "").trim() || "The worker has not emitted a detailed progress message yet.",
    interval: String(progressPayload.interval ?? "").trim() || "15m",
    metrics: progressPayload.metrics,
  };
}

function hasLiveJobProgress(
  progressPayload: BacktestRunJobStatusResponse["progress"] | null | undefined,
): progressPayload is BacktestRunJobProgress {
  if (!progressPayload || typeof progressPayload !== "object") {
    return false;
  }
  const progressValue = toFiniteNumber(progressPayload.progress, Number.NaN);
  if (!Number.isFinite(progressValue)) {
    return false;
  }
  const stage = String(progressPayload.stage ?? "").trim();
  const detail = String(progressPayload.detail ?? "").trim();
  const interval = String(progressPayload.interval ?? "").trim();
  return Boolean(stage && detail && interval);
}

function formatDuration(seconds: number) {
  if (seconds <= 0) return "0m";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  if (hours <= 0) return `${minutes}m`;
  return `${hours}h ${minutes}m`;
}

function formatDateTime(value: number | string) {
  return new Date(value).toLocaleString();
}

function formatLabel(value: string) {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getEventTone(kind: string) {
  const normalized = kind.toLowerCase();

  if (
    normalized.includes("stop") ||
    normalized.includes("risk") ||
    normalized.includes("reject") ||
    normalized.includes("error")
  ) {
    return "border-[#e06c6e]/20 bg-[#e06c6e]/10 text-[#f4b0b1]";
  }

  if (normalized.includes("exit") || normalized.includes("close") || normalized.includes("take")) {
    return "border-[#8ec5ff]/20 bg-[#8ec5ff]/10 text-[#b7d9ff]";
  }

  if (normalized.includes("entry") || normalized.includes("open") || normalized.includes("signal")) {
    return "border-[#74b97f]/20 bg-[#74b97f]/10 text-[#9fddb0]";
  }

  return "border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.04)] text-neutral-300";
}

function summarizeEventGroups(events: BacktestTriggerEvent[]) {
  const counts = new Map<string, number>();

  events.forEach((event) => {
    const label = formatLabel(event.kind || event.title);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  });

  return Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, 4)
    .map(([label, count]) => ({ label, count }));
}

function isActiveBacktestJob(job: BacktestRunJobStatusResponse) {
  return job.status === "queued" || job.status === "running";
}

function upsertBacktestJob(
  jobs: BacktestRunJobStatusResponse[],
  nextJob: BacktestRunJobStatusResponse,
): BacktestRunJobStatusResponse[] {
  const deduped = [nextJob, ...jobs.filter((job) => job.id !== nextJob.id)];
  return deduped.sort((left, right) => {
    const leftTime = Date.parse(left.updatedAt ?? left.createdAt ?? "") || 0;
    const rightTime = Date.parse(right.updatedAt ?? right.createdAt ?? "") || 0;
    return rightTime - leftTime;
  });
}

function toResumedRunProgress(
  job: BacktestRunJobStatusResponse,
  fallbackInterval: string,
): RunProgressState {
  if (hasLiveJobProgress(job.progress)) {
    return toRunProgressState(job.progress);
  }
  return {
    progress: job.status === "running" ? 12 : 6,
    stage: job.status === "running" ? "Resuming worker job" : "Queued on worker",
    detail:
      job.status === "running"
        ? "The worker is still replaying this run."
        : "The worker has the job queued and will start it shortly.",
    interval: fallbackInterval,
  };
}

function formatJobStatusLabel(status: BacktestRunJobStatusResponse["status"]) {
  return status.replace("_", " ");
}

function formatJobTimestamp(job: BacktestRunJobStatusResponse) {
  return job.completedAt ?? job.updatedAt ?? job.createdAt ?? null;
}

export function BacktestingLabPage() {
  const searchParams = useSearchParams();
  const queryBotId = searchParams.get("botId");
  const { authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();

  const initialRange = useMemo(() => presetRange(30), []);
  const [bots, setBots] = useState<SavedBot[]>([]);
  const [runs, setRuns] = useState<BacktestRunSummary[]>([]);
  const [runCache, setRunCache] = useState<Record<string, BacktestRunDetail>>({});
  const [selectedBotId, setSelectedBotId] = useState("");
  const [datePreset, setDatePreset] = useState<(typeof DATE_PRESETS)[number]["id"]>("30d");
  const [startDate, setStartDate] = useState(initialRange.start);
  const [endDate, setEndDate] = useState(initialRange.end);
  const [initialCapitalUsd, setInitialCapitalUsd] = useState("10000");
  const [feeBps, setFeeBps] = useState("4");
  const [slippageBps, setSlippageBps] = useState("5");
  const [fundingBpsPerInterval, setFundingBpsPerInterval] = useState("0");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [inspectorView, setInspectorView] = useState<"trades" | "journal">("trades");
  const [tradePage, setTradePage] = useState(1);
  const [journalPage, setJournalPage] = useState(1);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyFilter, setHistoryFilter] = useState<HistoryFilter>("all");
  const [historyScope, setHistoryScope] = useState<HistoryScope>("all");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [backtestJobs, setBacktestJobs] = useState<BacktestRunJobStatusResponse[]>([]);
  const [pendingBacktestJobId, setPendingBacktestJobId] = useState<string | null>(null);
  const [runProgress, setRunProgress] = useState<RunProgressState | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const deferredHistoryQuery = useDeferredValue(historyQuery);
  const currentRun = activeRunId ? runCache[activeRunId] ?? null : null;
  const compareRuns = compareIds.map((runId) => runCache[runId]).filter(Boolean) as BacktestRunDetail[];
  const selectedBot = bots.find((bot) => bot.id === selectedBotId) ?? null;
  const latestBacktestJobs = useMemo(() => backtestJobs.slice(0, 6), [backtestJobs]);
  const pendingWorkload = useMemo(
    () => estimateBacktestWorkload(startDate, endDate, selectedBot?.inferred_backtest_interval),
    [endDate, selectedBot?.inferred_backtest_interval, startDate],
  );
  const comparisonRuns = useMemo(() => {
    const next: BacktestRunDetail[] = [];
    const seen = new Set<string>();

    [currentRun, ...compareRuns].forEach((run) => {
      if (!run || seen.has(run.id)) {
        return;
      }
      seen.add(run.id);
      next.push(run);
    });

    return next;
  }, [compareRuns, currentRun]);

  useEffect(() => {
    if (!authenticated || !walletAddress) {
      setBots([]);
      setRuns([]);
      setRunCache({});
      setBacktestJobs([]);
      setSelectedBotId(queryBotId ?? "");
      setActiveRunId(null);
      setCompareIds([]);
      setPendingBacktestJobId(null);
      setRunning(false);
      setRunProgress(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    async function loadInitialState() {
      setLoading(true);
      setPageError(null);
      setHistoryError(null);
      try {
        const resolvedWallet = walletAddress;
        if (!resolvedWallet) return;
        const headers = await getAuthHeaders();
        const walletQuery = encodeURIComponent(resolvedWallet);
        const response = await fetch(`${API_BASE_URL}/api/backtests/bootstrap?wallet_address=${walletQuery}`, {
          cache: "no-store",
          headers,
          signal: controller.signal,
        });
        const payload = (await response.json()) as BacktestsBootstrapPayload | { detail?: string };
        if (!response.ok) {
          throw new Error(("detail" in payload ? payload.detail : null) ?? "Could not load the backtesting lab.");
        }

        if (cancelled) return;
        const bootstrap = payload as BacktestsBootstrapPayload;
        const nextBots = bootstrap.bots as SavedBot[];
        const nextRuns = bootstrap.runs;
        const nextJobs = bootstrap.jobs ?? [];
        setBots(nextBots);
        setRuns(nextRuns);
        setBacktestJobs(nextJobs);
        setRunCache({});
        setHistoryError(null);
        const preferredBotId =
          queryBotId && nextBots.some((bot) => bot.id === queryBotId)
            ? queryBotId
            : nextBots[0]?.id ?? "";
        const resumableJob = nextJobs.find((job) => isActiveBacktestJob(job)) ?? null;
        const resumableInterval =
          resumableJob?.progress?.interval ??
          nextBots.find((bot) => bot.id === preferredBotId)?.inferred_backtest_interval ??
          "15m";
        setSelectedBotId((current) => current || preferredBotId);
        setActiveRunId(null);
        if (resumableJob) {
          setPendingBacktestJobId(resumableJob.id);
          setRunning(true);
          setRunProgress(toResumedRunProgress(resumableJob, resumableInterval));
        } else {
          setPendingBacktestJobId(null);
          setRunning(false);
          setRunProgress(null);
        }
      } catch (error) {
        if (!cancelled && !(error instanceof DOMException && error.name === "AbortError")) {
          setPageError(error instanceof Error ? error.message : "Could not load the backtesting lab.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadInitialState();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [authenticated, getAuthHeaders, queryBotId, walletAddress]);

  useEffect(() => {
    if (!authenticated || !walletAddress || !activeRunId || runCache[activeRunId]) {
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    async function loadRunDetail(runId: string) {
      try {
        const resolvedWallet = walletAddress;
        if (!resolvedWallet) return;
        const headers = await getAuthHeaders();
        const response = await fetch(
          `${API_BASE_URL}/api/backtests/runs/${encodeURIComponent(runId)}?wallet_address=${encodeURIComponent(resolvedWallet)}`,
          {
            cache: "no-store",
            headers,
            signal: controller.signal,
          },
        );
        const payload = (await response.json()) as BacktestRunDetail | { detail?: string };
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Could not load backtest run." : "Could not load backtest run.");
        }
        if (cancelled) return;
        setRunCache((current) => ({ ...current, [runId]: payload as BacktestRunDetail }));
      } catch (error) {
        if (!cancelled && !(error instanceof DOMException && error.name === "AbortError")) {
          setHistoryError(error instanceof Error ? error.message : "Could not load backtest run.");
        }
      }
    }
    void loadRunDetail(activeRunId);
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeRunId, authenticated, getAuthHeaders, runCache, walletAddress]);

  useEffect(() => {
    if (!authenticated || !walletAddress) {
      return;
    }
    const pendingIds = compareIds.filter((runId) => !runCache[runId]);
    if (pendingIds.length === 0) {
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    async function loadCompareRuns() {
      try {
        const resolvedWallet = walletAddress;
        if (!resolvedWallet) return;
        const headers = await getAuthHeaders();
        const results = await Promise.all(
          pendingIds.map(async (runId) => {
            const response = await fetch(
              `${API_BASE_URL}/api/backtests/runs/${encodeURIComponent(runId)}?wallet_address=${encodeURIComponent(resolvedWallet)}`,
              {
                cache: "no-store",
                headers,
                signal: controller.signal,
              },
            );
            const payload = (await response.json()) as BacktestRunDetail | { detail?: string };
            if (!response.ok) {
              throw new Error("detail" in payload ? payload.detail ?? "Could not load compare run." : "Could not load compare run.");
            }
            return payload as BacktestRunDetail;
          }),
        );
        if (cancelled) return;
        setRunCache((current) => {
          const next = { ...current };
          results.forEach((run) => {
            next[run.id] = run;
          });
          return next;
        });
      } catch (error) {
        if (!cancelled && !(error instanceof DOMException && error.name === "AbortError")) {
          setHistoryError(error instanceof Error ? error.message : "Could not load compare runs.");
        }
      }
    }
    void loadCompareRuns();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [authenticated, compareIds, getAuthHeaders, runCache, walletAddress]);

  useEffect(() => {
    if (!authenticated || !pendingBacktestJobId) {
      return;
    }

    let cancelled = false;
    let timeoutId: number | null = null;

    const scheduleNextPoll = () => {
      if (cancelled) {
        return;
      }
      const delay = typeof document !== "undefined" && document.visibilityState === "hidden"
        ? BACKTEST_JOB_POLL_HIDDEN_MS
        : BACKTEST_JOB_POLL_VISIBLE_MS;
      timeoutId = window.setTimeout(() => {
        void pollJob();
      }, delay);
    };

    const clearProgressSoon = () => {
      window.setTimeout(() => {
        setRunProgress(null);
      }, 700);
    };

    const pollJob = async () => {
      try {
        const headers = await getAuthHeaders();
        const response = await fetch(`${API_BASE_URL}/api/backtests/runs/jobs/${encodeURIComponent(pendingBacktestJobId)}`, {
          cache: "no-store",
          headers,
        });
        const payload = (await response.json()) as BacktestRunJobStatusResponse | { detail?: string };
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Could not poll backtest job." : "Could not poll backtest job.");
        }
        if (cancelled) {
          return;
        }

        const job = payload as BacktestRunJobStatusResponse;
        setBacktestJobs((current) => upsertBacktestJob(current, job));
        if (hasLiveJobProgress(job.progress)) {
          setRunProgress(toRunProgressState(job.progress));
        }

        if (job.status === "completed" && job.result) {
          const finalRun = job.result;
          setRunProgress({
            progress: 100,
            stage: finalRun.status === "completed" ? "Replay complete" : "Run finished with issues",
            detail: finalRun.status === "completed" ? "The result set is ready." : "The replay finished with issue details.",
            interval: finalRun.interval,
            metrics: job.progress?.metrics,
          });
          setRuns((current) => [finalRun, ...current.filter((run) => run.id !== finalRun.id)]);
          setRunCache((current) => ({ ...current, [finalRun.id]: finalRun }));
          setActiveRunId(finalRun.id);
          setPendingBacktestJobId(null);
          setRunning(false);
          clearProgressSoon();
          return;
        }

        if (job.status === "failed") {
          setPendingBacktestJobId(null);
          setRunning(false);
          setPageError(job.errorDetail ?? "Backtest failed.");
          clearProgressSoon();
          return;
        }

        scheduleNextPoll();
      } catch (error) {
        if (cancelled) {
          return;
        }
        setPendingBacktestJobId(null);
        setRunning(false);
        setPageError(error instanceof Error ? error.message : "Could not poll backtest job.");
        clearProgressSoon();
      }
    };

    void pollJob();

    return () => {
      cancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [authenticated, getAuthHeaders, pendingBacktestJobId]);

  const filteredRuns = useMemo(() => {
    const query = deferredHistoryQuery.trim().toLowerCase();
    return runs.filter((run) => {
      if (historyFilter !== "all" && run.status !== historyFilter) {
        return false;
      }
      if (historyScope === "selected" && selectedBotId && run.bot_definition_id !== selectedBotId) {
        return false;
      }
      if (!query) {
        return true;
      }
      return (
        run.bot_name_snapshot.toLowerCase().includes(query) ||
        run.interval.toLowerCase().includes(query) ||
        run.status.toLowerCase().includes(query)
      );
    });
  }, [deferredHistoryQuery, historyFilter, historyScope, runs, selectedBotId]);

  async function refreshHistory() {
    if (!authenticated || !walletAddress) return;
    try {
      const headers = await getAuthHeaders();
      const walletQuery = encodeURIComponent(walletAddress);
      const [runsResponse, jobsResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/backtests/runs?wallet_address=${walletQuery}`, {
          cache: "no-store",
          headers,
        }),
        fetch(`${API_BASE_URL}/api/backtests/runs/jobs?wallet_address=${walletQuery}`, {
          cache: "no-store",
          headers,
        }),
      ]);
      const runsPayload = (await runsResponse.json()) as BacktestRunSummary[] | { detail?: string };
      const jobsPayload = (await jobsResponse.json()) as BacktestRunJobStatusResponse[] | { detail?: string };
      if (!runsResponse.ok) {
        throw new Error(
          "detail" in runsPayload ? runsPayload.detail ?? "Could not refresh backtests." : "Could not refresh backtests.",
        );
      }
      if (!jobsResponse.ok) {
        throw new Error(
          "detail" in jobsPayload ? jobsPayload.detail ?? "Could not refresh backtest jobs." : "Could not refresh backtest jobs.",
        );
      }
      setRuns(runsPayload as BacktestRunSummary[]);
      setBacktestJobs(jobsPayload as BacktestRunJobStatusResponse[]);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Could not refresh backtests.");
    }
  }

  function resumeBacktestJob(job: BacktestRunJobStatusResponse) {
    setPageError(null);
    setPendingBacktestJobId(job.id);
    setRunning(true);
    setRunProgress(toResumedRunProgress(job, job.progress?.interval ?? selectedBot?.inferred_backtest_interval ?? "15m"));
  }

  async function runBacktest() {
    if (!authenticated) {
      login();
      return;
    }
    if (!walletAddress || !selectedBotId) {
      setPageError("Choose a saved bot before you run a backtest.");
      return;
    }
    const { start, end } = toTimestampBounds(startDate, endDate);
    const payload: BacktestRunRequestPayload = {
      wallet_address: walletAddress,
      bot_id: selectedBotId,
      start_time: start,
      end_time: end,
      initial_capital_usd: readNumericInput(initialCapitalUsd),
      assumptions: {
        fee_bps: readNumericInput(feeBps),
        slippage_bps: readNumericInput(slippageBps),
        funding_bps_per_interval: readNumericInput(fundingBpsPerInterval),
      },
    };

    setRunning(true);
    setPageError(null);
    setRunProgress(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/backtests/runs/jobs`, {
        method: "POST",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      const result = (await response.json()) as BacktestRunJobCreateResponse | { detail?: string };
      if (!response.ok || !("id" in result)) {
        throw new Error("detail" in result ? result.detail ?? "Backtest failed." : "Backtest failed.");
      }
      const createdAt = new Date().toISOString();
      setBacktestJobs((current) =>
        upsertBacktestJob(current, {
          id: result.id,
          jobType: "backtest_run",
          status: "queued",
          createdAt,
          updatedAt: createdAt,
        }),
      );
      setPendingBacktestJobId(result.id);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "Backtest failed.");
      setRunning(false);
      window.setTimeout(() => setRunProgress(null), 700);
    }
  }

  function toggleCompare(runId: string) {
    setHistoryError(null);
    setCompareIds((current) => {
      if (current.includes(runId)) {
        return current.filter((id) => id !== runId);
      }
      if (current.length >= 3) {
        setHistoryError("Compare is limited to three runs at a time.");
        return current;
      }
      return [...current, runId];
    });
  }

  function applyPreset(nextPreset: (typeof DATE_PRESETS)[number]["id"]) {
    setDatePreset(nextPreset);
    if (nextPreset === "custom") return;
    const preset = DATE_PRESETS.find((item) => item.id === nextPreset);
    if (!preset) return;
    const nextRange = presetRange(preset.days);
    setStartDate(nextRange.start);
    setEndDate(nextRange.end);
  }

  const summary = currentRun?.result_json.summary ?? null;
  const assumptionConfig: BacktestAssumptionConfig = currentRun?.result_json.assumption_config ?? {
    fee_bps: readNumericInput(feeBps),
    slippage_bps: readNumericInput(slippageBps),
    funding_bps_per_interval: readNumericInput(fundingBpsPerInterval),
  };
  const preflightIssues = useMemo(() => currentRun?.result_json.preflight_issues ?? [], [currentRun]);
  const executionIssues = useMemo(() => currentRun?.result_json.execution_issues ?? [], [currentRun]);
  const trades = useMemo(() => currentRun?.result_json.trades ?? [], [currentRun]);
  const triggerEvents = useMemo(() => currentRun?.result_json.trigger_events ?? [], [currentRun]);
  const tradePageCount = Math.max(1, Math.ceil(trades.length / INSPECTOR_PAGE_SIZE));
  const journalPageCount = Math.max(1, Math.ceil(triggerEvents.length / INSPECTOR_PAGE_SIZE));
  const visibleTrades = useMemo(
    () => trades.slice((tradePage - 1) * INSPECTOR_PAGE_SIZE, tradePage * INSPECTOR_PAGE_SIZE),
    [tradePage, trades],
  );
  const visibleTriggerEvents = useMemo(
    () => triggerEvents.slice((journalPage - 1) * INSPECTOR_PAGE_SIZE, journalPage * INSPECTOR_PAGE_SIZE),
    [journalPage, triggerEvents],
  );
  const recentJournalEvents = useMemo(() => [...triggerEvents].reverse().slice(0, 5), [triggerEvents]);
  const eventGroups = useMemo(() => summarizeEventGroups(triggerEvents), [triggerEvents]);
  const trackedSymbols = useMemo(() => {
    const summarySymbols = currentRun?.result_json.summary?.symbols ?? [];
    if (summarySymbols.length > 0) {
      return summarySymbols;
    }

    const symbols = new Set<string>();

    triggerEvents.forEach((event) => {
      if (event.symbol) {
        symbols.add(event.symbol);
      }
    });

    trades.forEach((trade) => {
      if (trade.symbol) {
        symbols.add(trade.symbol);
      }
    });

    return Array.from(symbols);
  }, [currentRun, trades, triggerEvents]);
  const visibleTrackedSymbols = trackedSymbols.slice(0, 6);
  const hiddenTrackedSymbolCount = Math.max(0, trackedSymbols.length - visibleTrackedSymbols.length);
  const chartDescription = summary
    ? trackedSymbols.length > 1
      ? `Portfolio balance across ${trackedSymbols.length} symbols on ${currentRun?.interval ?? summary.interval}.`
      : summary.primary_symbol
        ? `Portfolio balance for ${summary.primary_symbol} on ${currentRun?.interval ?? summary.interval}.`
        : "Portfolio balance for the selected replay."
    : "Open a run to load the chart.";

  useEffect(() => {
    setTradePage(1);
    setJournalPage(1);
  }, [activeRunId]);

  useEffect(() => {
    setTradePage((current) => Math.min(current, tradePageCount));
  }, [tradePageCount]);

  useEffect(() => {
    setJournalPage((current) => Math.min(current, journalPageCount));
  }, [journalPageCount]);

  if (!authenticated) {
    return (
      <main className="shell grid gap-6 pb-10 md:pb-12">
        <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[linear-gradient(135deg,#16181a,rgba(22,24,26,0.72),rgba(116,185,127,0.08))] p-8 md:p-10">
          <span className="label text-[#dce85d]">Backtesting lab</span>
          <h1 className="max-w-4xl font-mono text-[clamp(2.4rem,6vw,4.8rem)] font-extrabold uppercase leading-[0.9] tracking-[-0.05em] text-neutral-50">
            Rehearse every bot before it sees live flow.
          </h1>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400 md:text-base">
            Load a saved strategy, replay its rules over historical candles, and compare how different runs stack up before you deploy capital.
          </p>
          <button
            type="button"
            onClick={login}
            className="mt-2 w-fit rounded-full bg-[#dce85d] px-5 py-3 text-sm font-semibold text-[#090a0a] transition hover:bg-[#e7f06d]"
          >
            Sign in to open the lab
          </button>
        </section>
      </main>
    );
  }

  if (loading) {
    return <BacktestingLabSkeleton />;
  }

  return (
    <main className="shell grid gap-6 pb-10 md:pb-12">
      <section className="flex flex-wrap items-end justify-between gap-4 border-b border-[rgba(255,255,255,0.08)] pb-6 md:pb-8">
        <div className="grid gap-2">
          <h1 className="font-mono text-[clamp(2rem,4vw,2.8rem)] font-bold uppercase tracking-tight text-neutral-50">
            Backtests
          </h1>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400">
            Replay saved bots and compare runs before going live.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void refreshHistory()}
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
          >
            <span className="inline-flex items-center gap-2">
              <RefreshCcw className="h-3.5 w-3.5" />
              Refresh history
            </span>
          </button>
          {selectedBot ? (
            <Link
              href={`/bots/${selectedBot.id}`}
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
            >
              <span className="inline-flex items-center gap-2">
                Open bot
                <ArrowUpRight className="h-3.5 w-3.5" />
              </span>
            </Link>
          ) : null}
        </div>
      </section>

      {pageError ? (
        <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">{pageError}</article>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem] xl:items-start">
        <div className="grid gap-6">
          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
            <div className="grid gap-2">
              <span className="label text-[#74b97f]">Run controls</span>
              <p className="text-sm leading-7 text-neutral-400">
                Pick a saved bot, set the replay window, and queue a worker-backed historical run against Pacifica candle data. Replay interval is inferred from the bot rules.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
              <label className="grid min-w-0 gap-1.5 text-sm text-neutral-400 xl:col-span-2">
                Saved bot
                <select
                  value={selectedBotId}
                  onChange={(event) => setSelectedBotId(event.target.value)}
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3.5 py-3 text-sm text-neutral-50 outline-none transition w-full focus:border-[#dce85d]"
                >
                  <option value="">Choose a bot</option>
                  {bots.map((bot) => (
                    <option key={bot.id} value={bot.id}>
                      {bot.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="grid min-w-0 gap-1.5 text-sm text-neutral-400">
                <span>Replay interval</span>
                <div className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3.5 py-3 text-sm text-neutral-50">
                  {selectedBot?.inferred_backtest_interval ?? "Pick a bot"}
                </div>
              </div>
              <label className="grid min-w-0 gap-1.5 text-sm text-neutral-400">
                Initial capital
                <input
                  value={initialCapitalUsd}
                  onChange={(event) => setInitialCapitalUsd(event.target.value)}
                  inputMode="decimal"
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3.5 py-3 text-sm text-neutral-50 outline-none transition w-full focus:border-[#dce85d]"
                />
              </label>
              <div className="grid gap-1.5 text-sm text-neutral-400 xl:col-span-2">
                Range
                <div className="flex flex-wrap gap-2">
                  {DATE_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => applyPreset(preset.id)}
                      className={`rounded-full border px-3 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] transition ${
                        datePreset === preset.id
                          ? "border-[#dce85d]/40 bg-[#dce85d]/10 text-[#dce85d]"
                          : "border-[rgba(255,255,255,0.12)] text-neutral-400 hover:border-white hover:text-neutral-50"
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="grid min-w-0 gap-1.5 text-sm text-neutral-400">
                Start date
                <input
                  type="date"
                  value={startDate}
                  onChange={(event) => {
                    setDatePreset("custom");
                    setStartDate(event.target.value);
                  }}
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3.5 py-3 text-sm text-neutral-50 outline-none transition w-full focus:border-[#dce85d]"
                />
              </label>
              <label className="grid min-w-0 gap-1.5 text-sm text-neutral-400">
                End date
                <input
                  type="date"
                  value={endDate}
                  onChange={(event) => {
                    setDatePreset("custom");
                    setEndDate(event.target.value);
                  }}
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3.5 py-3 text-sm text-neutral-50 outline-none transition w-full focus:border-[#dce85d]"
                />
              </label>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <label className="grid min-w-0 gap-1.5 text-sm text-neutral-400">
                Fees (bps)
                <input
                  value={feeBps}
                  onChange={(event) => setFeeBps(event.target.value)}
                  inputMode="decimal"
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3.5 py-3 text-sm text-neutral-50 outline-none transition w-full focus:border-[#dce85d]"
                />
              </label>
              <label className="grid min-w-0 gap-1.5 text-sm text-neutral-400">
                Slippage (bps)
                <input
                  value={slippageBps}
                  onChange={(event) => setSlippageBps(event.target.value)}
                  inputMode="decimal"
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3.5 py-3 text-sm text-neutral-50 outline-none transition w-full focus:border-[#dce85d]"
                />
              </label>
              <label className="grid min-w-0 gap-1.5 text-sm text-neutral-400">
                Funding / replay bar (bps)
                <input
                  value={fundingBpsPerInterval}
                  onChange={(event) => setFundingBpsPerInterval(event.target.value)}
                  inputMode="decimal"
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3.5 py-3 text-sm text-neutral-50 outline-none transition w-full focus:border-[#dce85d]"
                />
              </label>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[rgba(255,255,255,0.06)] pt-4">
              <div className="grid gap-1 text-sm text-neutral-500">
                <span>
                  {selectedBot
                    ? `${selectedBot.strategy_type} / ${selectedBot.market_scope} / ${selectedBot.inferred_backtest_interval} replay`
                    : "Pick a bot to unlock the replay settings."}
                </span>
                {selectedBot ? (
                  <span className="text-xs uppercase tracking-[0.16em] text-neutral-600">
                    {pendingWorkload.estimatedBars.toLocaleString()} bars / {pendingWorkload.estimatedRequests}{" "}
                    Pacifica {pendingWorkload.estimatedRequests === 1 ? "window" : "windows"}
                  </span>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => void runBacktest()}
                disabled={running || !selectedBotId || loading}
                className="rounded-full bg-[#dce85d] px-5 py-3 text-sm font-semibold text-[#090a0a] transition hover:bg-[#e7f06d] disabled:cursor-not-allowed disabled:bg-neutral-700 disabled:text-neutral-400"
              >
                <span className="inline-flex items-center gap-2">
                  {running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  {running ? "Running backtest..." : "Run backtest"}
                </span>
              </button>
            </div>
            {runProgress ? (
              <article className="grid gap-3 rounded-[1.6rem] border border-[#8ec5ff]/20 bg-[linear-gradient(135deg,rgba(142,197,255,0.12),rgba(220,232,93,0.08))] p-4 text-neutral-50">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="grid gap-1">
                    <span className="label text-[#8ec5ff]">{runProgress.stage}</span>
                    <p className="text-sm leading-6 text-neutral-200">{runProgress.detail}</p>
                  </div>
                  <div className="rounded-full border border-[rgba(255,255,255,0.12)] bg-[rgba(9,10,10,0.45)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-neutral-200">
            {Math.round(toFiniteNumber(runProgress.progress, 0))}%
                  </div>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-[rgba(255,255,255,0.08)]">
                  <div
                    className="h-full rounded-full bg-[linear-gradient(90deg,#8ec5ff_0%,#dce85d_55%,#74b97f_100%)] transition-[width] duration-300 ease-out"
                    style={{ width: `${clampNumber(toFiniteNumber(runProgress.progress, 0), 0, 100)}%` }}
                  />
                </div>
                <div className="flex flex-wrap gap-3 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
                  <span>
                    {Number(runProgress.metrics?.processed_bars ?? runProgress.metrics?.estimated_bars ?? 0).toLocaleString()} /{" "}
                    {Number(runProgress.metrics?.total_bars ?? runProgress.metrics?.estimated_bars ?? pendingWorkload.estimatedBars).toLocaleString()} bars
                  </span>
                  <span>
                    {Number(runProgress.metrics?.completed_requests ?? 0).toLocaleString()} /{" "}
                    {Number(runProgress.metrics?.total_requests ?? runProgress.metrics?.estimated_requests ?? pendingWorkload.estimatedRequests).toLocaleString()} requests
                  </span>
                  <span>{runProgress.interval} cadence</span>
                </div>
              </article>
            ) : null}
          </section>

          {summary ? (
            <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-8">
              {[
                { label: "Gross PnL", value: formatMoney(summary.gross_pnl_total), tone: summary.gross_pnl_total >= 0 ? "text-[#8ec5ff]" : "text-[#e06c6e]" },
                { label: "Net PnL", value: formatMoney(summary.pnl_total), tone: summary.pnl_total >= 0 ? "text-[#74b97f]" : "text-[#e06c6e]" },
                { label: "Net PnL %", value: formatPercent(summary.pnl_total_pct), tone: summary.pnl_total_pct >= 0 ? "text-[#74b97f]" : "text-[#e06c6e]" },
                { label: "Fees paid", value: formatMoney(summary.fees_paid_usd), tone: "text-neutral-50" },
                { label: "Funding", value: formatMoney(summary.funding_pnl_usd), tone: summary.funding_pnl_usd >= 0 ? "text-[#74b97f]" : "text-[#e06c6e]" },
                { label: "Drawdown", value: `${summary.max_drawdown_pct.toFixed(2)}%`, tone: "text-neutral-50" },
                { label: "Win rate", value: `${summary.win_rate.toFixed(1)}%`, tone: "text-neutral-50" },
                { label: "Trades", value: String(summary.trade_count), tone: "text-neutral-50" },
                { label: "Avg duration", value: formatDuration(summary.avg_trade_duration_seconds), tone: "text-neutral-50" },
              ].map((item) => (
                <article key={item.label} className="grid gap-1 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4">
                  <span className="label text-neutral-500">{item.label}</span>
                  <div className={`font-mono text-xl font-bold uppercase ${item.tone}`}>{item.value}</div>
                </article>
              ))}
            </section>
          ) : null}

          {preflightIssues.length > 0 ? (
            <article className="grid gap-2 rounded-[1.8rem] border border-[#dce85d]/30 bg-[#dce85d]/10 p-5 text-sm leading-7 text-neutral-50">
              <span className="label text-[#dce85d]">Preflight warning</span>
              {preflightIssues.map((issue) => (
                <p key={issue}>{issue}</p>
              ))}
            </article>
          ) : null}
          {executionIssues.length > 0 ? (
            <article className="grid gap-2 rounded-[1.8rem] border border-[#8ec5ff]/30 bg-[#8ec5ff]/10 p-5 text-sm leading-7 text-neutral-50">
              <span className="label text-[#8ec5ff]">Run issue</span>
              {executionIssues.map((issue) => (
                <p key={issue}>{issue}</p>
              ))}
            </article>
          ) : null}

          {comparisonRuns.length > 1 ? (
            <section className="grid gap-3 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:grid-cols-3">
              {comparisonRuns.map((run, index) => (
                <article key={run.id} className="grid gap-2 rounded-[1.5rem] bg-[#090a0a] p-4">
                  <span className="label" style={{ color: COMPARE_COLORS[index % COMPARE_COLORS.length] }}>
                    {currentRun ? (index === 0 ? "Selected run" : `Compare ${index}`) : `Compare ${index + 1}`}
                  </span>
                  <div className="font-mono text-lg font-bold uppercase text-neutral-50">{run.bot_name_snapshot}</div>
                  <div className="text-sm text-neutral-400">
                    {formatMoney(run.pnl_total)} / {formatPercent(run.pnl_total_pct)}
                  </div>
                  {(run.result_json.summary?.symbols?.length ?? 0) > 1 ? (
                    <div className="text-xs text-neutral-500">{run.result_json.summary.symbols.length} symbols in rotation</div>
                  ) : null}
                  <div className="text-xs text-neutral-500">
                    DD {run.max_drawdown_pct.toFixed(2)}% · WR {run.win_rate.toFixed(1)}% · {run.trade_count} trades
                  </div>
                </article>
              ))}
            </section>
          ) : null}

          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="grid gap-1">
                <span className="label text-[#74b97f]">Replay chart</span>
                <p className="text-sm text-neutral-500">{chartDescription}</p>
              </div>
              {currentRun ? (
                <div className="flex flex-wrap items-center gap-2">
                  <div className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
                    {currentRun.interval} replay
                  </div>
                  {trackedSymbols.length ? (
                    <div className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
                      {trackedSymbols.length} {trackedSymbols.length === 1 ? "symbol" : "symbols"}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
            {visibleTrackedSymbols.length ? (
              <div className="flex flex-wrap gap-2">
                {visibleTrackedSymbols.map((symbol) => (
                  <span
                    key={symbol}
                    className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3 py-1.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300"
                  >
                    {symbol}
                  </span>
                ))}
                {hiddenTrackedSymbolCount > 0 ? (
                  <span className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3 py-1.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
                    +{hiddenTrackedSymbolCount} more
                  </span>
                ) : null}
              </div>
            ) : null}
            <BacktestChart runs={comparisonRuns} />
          </section>

          <section className="grid gap-4">
            <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[rgba(255,255,255,0.06)] pb-4">
                <div className="grid gap-1">
                  <span className="label text-[#dce85d]">Tester log</span>
                  <p className="text-sm text-neutral-500">
                    Keep fills in view by default, then switch to the journal when you want the rule trail behind each move.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {(["trades", "journal"] as const).map((view) => (
                    <button
                      key={view}
                      type="button"
                      onClick={() => setInspectorView(view)}
                      className={`rounded-full border px-3 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] transition ${
                        inspectorView === view
                          ? "border-[#dce85d]/40 bg-[#dce85d]/10 text-[#dce85d]"
                          : "border-[rgba(255,255,255,0.12)] text-neutral-400 hover:border-white hover:text-neutral-50"
                      }`}
                    >
                      {view === "trades" ? "Trade log" : "Journal"}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  { label: "Trades", value: String(trades.length) },
                  { label: "Journal events", value: String(triggerEvents.length) },
                  {
                    label: "Symbols",
                    value: trackedSymbols.length
                      ? `${visibleTrackedSymbols.join(", ")}${hiddenTrackedSymbolCount > 0 ? ` +${hiddenTrackedSymbolCount}` : ""}`
                      : "--",
                  },
                  {
                    label: "Latest event",
                    value: triggerEvents.length ? formatDateTime(triggerEvents[triggerEvents.length - 1].timestamp) : "Waiting for a run",
                  },
                ].map((item) => (
                  <article key={item.label} className="grid gap-1 rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a] p-4">
                    <span className="label text-neutral-500">{item.label}</span>
                    <div className="text-sm font-semibold text-neutral-100">{item.value}</div>
                  </article>
                ))}
              </div>

              {inspectorView === "trades" ? (
                <div className="min-w-0 overflow-hidden rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a]">
                  <div className="hidden grid-cols-[1.1fr_0.95fr_0.95fr_0.85fr_0.9fr_0.7fr] gap-4 border-b border-[rgba(255,255,255,0.06)] px-4 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500 md:grid">
                    <span>Position</span>
                    <span>Opened</span>
                    <span>Closed</span>
                    <span>Size</span>
                    <span>Result</span>
                    <span>Duration</span>
                  </div>
                  <div className="grid max-h-[32rem] gap-2 overflow-auto p-3 md:p-4">
                    {trades.length ? (
                      visibleTrades.map((trade) => (
                        <div
                          key={`${trade.trade_id}-${trade.status}`}
                          className="rounded-[1.25rem] border border-[rgba(255,255,255,0.05)] bg-[#111315] px-4 py-3"
                        >
                          <div className="grid gap-3 md:hidden">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div>
                                <div className="font-mono text-sm font-bold uppercase text-neutral-50">
                                  {trade.symbol} {trade.side}
                                </div>
                                <div className="text-[0.68rem] uppercase tracking-[0.16em] text-neutral-500">
                                  {trade.status === "open"
                                    ? "Open position"
                                    : trade.close_reason
                                      ? formatLabel(trade.close_reason)
                                      : "Closed position"}
                                </div>
                              </div>
                              <div
                                className={`font-mono text-sm font-bold ${
                                  trade.pnl_usd !== null && trade.pnl_usd < 0 ? "text-[#e06c6e]" : "text-[#74b97f]"
                                }`}
                              >
                                {trade.pnl_usd !== null ? formatMoney(trade.pnl_usd) : formatMoney(trade.unrealized_pnl ?? 0)}
                              </div>
                            </div>
                            <div className="grid gap-2 text-sm text-neutral-400">
                              <div>Opened {formatDateTime(trade.entry_time)}</div>
                              <div>{trade.exit_time ? `Closed ${formatDateTime(trade.exit_time)}` : "Still open"}</div>
                              <div>Size {formatMoney(trade.notional_usd)}</div>
                              <div>{trade.duration_seconds !== null ? formatDuration(trade.duration_seconds) : "Open"}</div>
                              <div className="text-xs leading-5 text-neutral-500">
                                Gross {formatMoney(trade.gross_pnl_usd)} · Fees {formatMoney(trade.fees_paid_usd)} · Funding {formatMoney(trade.funding_pnl_usd)}
                              </div>
                            </div>
                          </div>

                          <div className="hidden items-center gap-4 md:grid md:grid-cols-[1.1fr_0.95fr_0.95fr_0.85fr_0.9fr_0.7fr]">
                            <div className="min-w-0">
                              <div className="font-mono text-sm font-bold uppercase text-neutral-50">
                                {trade.symbol} {trade.side}
                              </div>
                              <div className="truncate text-[0.68rem] uppercase tracking-[0.16em] text-neutral-500">
                                {trade.status === "open"
                                  ? "Open position"
                                  : trade.close_reason
                                    ? formatLabel(trade.close_reason)
                                    : "Closed position"}
                              </div>
                            </div>
                            <div className="text-sm text-neutral-300">{formatDateTime(trade.entry_time)}</div>
                            <div className="text-sm text-neutral-300">{trade.exit_time ? formatDateTime(trade.exit_time) : "Still open"}</div>
                            <div className="text-sm text-neutral-300">{formatMoney(trade.notional_usd)}</div>
                            <div
                              className={`font-mono text-sm font-bold ${
                                trade.pnl_usd !== null && trade.pnl_usd < 0 ? "text-[#e06c6e]" : "text-[#74b97f]"
                              }`}
                            >
                              <div>{trade.pnl_usd !== null ? formatMoney(trade.pnl_usd) : formatMoney(trade.unrealized_pnl ?? 0)}</div>
                              <div className="mt-1 text-[0.62rem] font-medium uppercase tracking-[0.12em] text-neutral-500">
                                Gross {formatMoney(trade.gross_pnl_usd)} · Fees {formatMoney(trade.fees_paid_usd)} · Funding {formatMoney(trade.funding_pnl_usd)}
                              </div>
                            </div>
                            <div className="text-sm text-neutral-300">
                              {trade.duration_seconds !== null ? formatDuration(trade.duration_seconds) : "Open"}
                            </div>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="rounded-[1.25rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#111315] p-5 text-sm leading-6 text-neutral-500">
                        Closed and open positions will land here after the replay finishes.
                      </div>
                    )}
                  </div>
                  <InspectorPagination
                    page={tradePage}
                    pageCount={tradePageCount}
                    totalItems={trades.length}
                    pageSize={INSPECTOR_PAGE_SIZE}
                    noun="trades"
                    onPageChange={setTradePage}
                  />
                </div>
              ) : (
                <div className="overflow-hidden rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a]">
                  <div className="grid max-h-[32rem] gap-2 overflow-auto p-3 md:p-4">
                    {triggerEvents.length ? (
                      visibleTriggerEvents.map((event) => (
                        <div
                          key={`${event.timestamp}-${event.title}-${event.detail}`}
                          className="rounded-[1.25rem] border border-[rgba(255,255,255,0.05)] bg-[#111315] px-4 py-3"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className={`rounded-full border px-2 py-1 text-[0.55rem] font-semibold uppercase tracking-[0.16em] ${getEventTone(event.kind)}`}>
                                  {formatLabel(event.kind)}
                                </span>
                                <span className="text-sm font-semibold text-neutral-50">{event.title}</span>
                              </div>
                              <p className="mt-2 text-sm leading-6 text-neutral-400">{event.detail}</p>
                            </div>
                            <div className="grid justify-items-end gap-1 text-right">
                              <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-2 py-1 text-[0.55rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
                                {event.symbol}
                              </span>
                              <span className="text-xs text-neutral-500">{formatDateTime(event.timestamp)}</span>
                            </div>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="rounded-[1.25rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#111315] p-5 text-sm leading-6 text-neutral-500">
                        The journal fills in once the replay starts hitting entries, exits, and rule checks.
                      </div>
                    )}
                  </div>
                  <InspectorPagination
                    page={journalPage}
                    pageCount={journalPageCount}
                    totalItems={triggerEvents.length}
                    pageSize={INSPECTOR_PAGE_SIZE}
                    noun="events"
                    onPageChange={setJournalPage}
                  />
                </div>
              )}
            </article>

            {false ? (
              <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
              <div className="flex items-center justify-between gap-3">
                <span className="label text-[#74b97f]">Activity snapshot</span>
                <span className="text-xs text-neutral-500">{triggerEvents.length} events</span>
              </div>
              <div className="grid gap-3">
                {trades.length ? (
                  trades.map((trade) => (
                    <div key={`${trade.trade_id}-${trade.status}`} className="rounded-[1.4rem] bg-[#090a0a] p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="font-mono text-lg font-bold uppercase text-neutral-50">
                            {trade.symbol} {trade.side}
                          </div>
                          <div className="text-xs text-neutral-500">
                            {new Date(trade.entry_time).toLocaleString()}
                            {trade.exit_time ? ` → ${new Date(trade.exit_time).toLocaleString()}` : " · still open"}
                          </div>
                        </div>
                        <div className={`font-mono text-sm font-bold ${trade.pnl_usd !== null && trade.pnl_usd < 0 ? "text-[#e06c6e]" : "text-[#74b97f]"}`}>
                          {trade.pnl_usd !== null ? formatMoney(trade.pnl_usd) : formatMoney(trade.unrealized_pnl ?? 0)}
                        </div>
                      </div>
                      <div className="mt-3 grid gap-2 text-sm text-neutral-400 md:grid-cols-4">
                        <div>Entry {trade.entry_price.toFixed(2)}</div>
                        <div>Exit {trade.exit_price !== null ? trade.exit_price.toFixed(2) : "--"}</div>
                        <div>Size {formatMoney(trade.notional_usd)}</div>
                        <div>{trade.duration_seconds !== null ? formatDuration(trade.duration_seconds) : "Open"}</div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-[1.4rem] bg-[#090a0a] p-4 text-sm leading-6 text-neutral-500">
                    Closed and open positions will be listed here after a run finishes.
                  </div>
                )}
              </div>
              </article>
            ) : null}
          </section>
        </div>

        <aside className="grid gap-4 self-start xl:sticky xl:top-6">
          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="grid gap-1">
                <span className="label text-[#8ec5ff]">Worker queue</span>
                <p className="text-sm text-neutral-500">Recent backtest jobs survive reloads. Reattach to any job that is still queued or running.</p>
              </div>
              <LoaderCircle className={`h-4 w-4 ${running ? "animate-spin text-[#8ec5ff]" : "text-neutral-500"}`} />
            </div>
            <div className="grid gap-3">
              {latestBacktestJobs.length ? (
                latestBacktestJobs.map((job) => {
                  const watching = pendingBacktestJobId === job.id;
                  const active = isActiveBacktestJob(job);
                  const jobTimestamp = formatJobTimestamp(job);
                  return (
                    <div
                      key={job.id}
                      className={`grid gap-3 rounded-[1.4rem] border p-4 ${
                        watching
                          ? "border-[#8ec5ff]/35 bg-[linear-gradient(135deg,rgba(142,197,255,0.08),rgba(9,10,10,0.92))]"
                          : "border-[rgba(255,255,255,0.06)] bg-[#090a0a]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-semibold text-neutral-50">{job.progress?.stage ?? (active ? "Backtest worker job" : "Finished worker job")}</div>
                          <div className="text-xs text-neutral-500">
                            {jobTimestamp ? formatDateTime(jobTimestamp) : "Waiting for worker timestamps"}
                          </div>
                        </div>
                        <span
                          className={`rounded-full px-2 py-1 text-[0.55rem] font-semibold uppercase tracking-[0.16em] ${
                            job.status === "completed"
                              ? "bg-[#74b97f]/12 text-[#74b97f]"
                              : job.status === "failed"
                                ? "bg-[#e06c6e]/12 text-[#f4b0b1]"
                                : "bg-[#8ec5ff]/12 text-[#8ec5ff]"
                          }`}
                        >
                          {formatJobStatusLabel(job.status)}
                        </span>
                      </div>
                      <div className="grid gap-1 text-sm text-neutral-400">
                        <div>{job.progress?.detail ?? (job.errorDetail ?? "No live progress snapshot yet.")}</div>
                        <div className="text-xs uppercase tracking-[0.16em] text-neutral-500">
                          {Math.round(job.progress?.progress ?? (job.status === "running" ? 12 : job.status === "queued" ? 6 : 100))}% progress
                        </div>
                      </div>
                      {active ? (
                        <button
                          type="button"
                          onClick={() => resumeBacktestJob(job)}
                          className={`rounded-full border px-3 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] transition ${
                            watching
                              ? "border-[#8ec5ff]/40 bg-[#8ec5ff]/10 text-[#8ec5ff]"
                              : "border-[rgba(255,255,255,0.12)] text-neutral-300 hover:border-[#8ec5ff] hover:text-[#8ec5ff]"
                          }`}
                        >
                          {watching ? "Watching job" : "Reattach"}
                        </button>
                      ) : null}
                    </div>
                  );
                })
              ) : (
                <div className="rounded-[1.4rem] bg-[#090a0a] p-4 text-sm leading-6 text-neutral-500">
                  Worker jobs will appear here as soon as you queue a backtest.
                </div>
              )}
            </div>
          </section>

          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="grid gap-1">
                <span className="label text-[#dce85d]">Run history</span>
                <p className="text-sm text-neutral-500">Browse the full wallet history and keep up to three extra runs selected for compare.</p>
              </div>
              <History className="h-4 w-4 text-neutral-500" />
            </div>
            <label className="grid gap-1.5 text-sm text-neutral-400">
              Search history
              <input
                value={historyQuery}
                onChange={(event) => setHistoryQuery(event.target.value)}
                placeholder="Bot, interval, status"
                className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3.5 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setHistoryScope("all")}
                className={`rounded-full border px-3 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] transition ${
                  historyScope === "all"
                    ? "border-[#74b97f]/40 bg-[#74b97f]/10 text-[#74b97f]"
                    : "border-[rgba(255,255,255,0.12)] text-neutral-400 hover:border-white hover:text-neutral-50"
                }`}
              >
                All bots
              </button>
              <button
                type="button"
                onClick={() => setHistoryScope("selected")}
                disabled={!selectedBotId}
                className={`rounded-full border px-3 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] transition ${
                  historyScope === "selected"
                    ? "border-[#74b97f]/40 bg-[#74b97f]/10 text-[#74b97f]"
                    : "border-[rgba(255,255,255,0.12)] text-neutral-400 hover:border-white hover:text-neutral-50"
                } disabled:cursor-not-allowed disabled:border-[rgba(255,255,255,0.08)] disabled:text-neutral-600`}
              >
                Launch bot
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {(["all", "completed", "failed"] as const).map((filter) => (
                <button
                  key={filter}
                  type="button"
                  onClick={() => setHistoryFilter(filter)}
                  className={`rounded-full border px-3 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] transition ${
                    historyFilter === filter
                      ? "border-[#dce85d]/40 bg-[#dce85d]/10 text-[#dce85d]"
                      : "border-[rgba(255,255,255,0.12)] text-neutral-400 hover:border-white hover:text-neutral-50"
                  }`}
                >
                  {filter}
                </button>
              ))}
            </div>
            <p className="text-xs text-neutral-500">
              Showing {filteredRuns.length} of {runs.length} saved runs.
            </p>
            {historyError ? <p className="text-sm text-[#dce85d]">{historyError}</p> : null}
            <div className="grid gap-3">
              {loading ? (
                <div className="rounded-[1.4rem] bg-[#090a0a] p-4 text-sm text-neutral-500">Loading history...</div>
              ) : filteredRuns.length ? (
                filteredRuns.map((run) => {
                  const selected = run.id === activeRunId;
                  const compareSelected = compareIds.includes(run.id);
                  return (
                    <button
                      key={run.id}
                      type="button"
                      onClick={() => startTransition(() => setActiveRunId(run.id))}
                      className={`grid gap-3 rounded-[1.4rem] border p-4 text-left transition ${
                        selected
                          ? "border-[#dce85d]/35 bg-[#dce85d]/8"
                          : "border-[rgba(255,255,255,0.06)] bg-[#090a0a] hover:border-[rgba(255,255,255,0.14)]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-neutral-50">{run.bot_name_snapshot}</div>
                          <div className="text-xs text-neutral-500">{new Date(run.completed_at ?? run.created_at).toLocaleString()}</div>
                        </div>
                        <span className={`rounded-full px-2 py-1 text-[0.55rem] font-semibold uppercase tracking-[0.16em] ${
                          run.status === "completed" ? "bg-[#74b97f]/12 text-[#74b97f]" : "bg-[#dce85d]/12 text-[#dce85d]"
                        }`}>
                          {run.status}
                        </span>
                      </div>
                      <div className="grid gap-1 text-sm text-neutral-400">
                        <div className={run.pnl_total >= 0 ? "text-[#74b97f]" : "text-[#e06c6e]"}>
                          {formatMoney(run.pnl_total)} / {formatPercent(run.pnl_total_pct)}
                        </div>
                        <div className="text-xs text-neutral-500">
                          {run.interval} · DD {run.max_drawdown_pct.toFixed(2)}% · WR {run.win_rate.toFixed(1)}%
                        </div>
                      </div>
                      <label className="flex items-center gap-2 text-xs text-neutral-400">
                        <input
                          type="checkbox"
                          checked={compareSelected}
                          onChange={(event) => {
                            event.stopPropagation();
                            toggleCompare(run.id);
                          }}
                        />
                        Add to compare
                      </label>
                    </button>
                  );
                })
              ) : (
                <div className="rounded-[1.4rem] bg-[#090a0a] p-4 text-sm leading-6 text-neutral-500">
                  No runs match the current filter.
                </div>
              )}
            </div>
          </section>

          <section className="grid gap-3 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="flex items-center gap-2 text-neutral-400">
              <FlaskConical className="h-4 w-4 text-[#74b97f]" />
              <span className="label text-[#74b97f]">Replay assumptions</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              {[
                { label: "Fees", value: formatBasisPoints(assumptionConfig.fee_bps) },
                { label: "Slippage", value: formatBasisPoints(assumptionConfig.slippage_bps) },
                { label: "Funding", value: formatBasisPoints(assumptionConfig.funding_bps_per_interval) },
              ].map((item) => (
                <div key={item.label} className="rounded-[1.3rem] border border-[rgba(255,255,255,0.05)] bg-[#090a0a] p-3">
                  <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{item.label}</div>
                  <div className="mt-1 font-mono text-sm font-bold uppercase text-neutral-50">{item.value}</div>
                </div>
              ))}
            </div>
            <div className="grid gap-2 text-sm leading-6 text-neutral-400">
              {(currentRun?.result_json.assumptions ?? [
                "Entries and exits execute on candle close.",
                "Take-profit and stop-loss checks use candle high and low on later bars.",
                "The lab stores every finished run so you can revisit it later.",
              ]).map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}

function BacktestingLabSkeleton() {
  return (
    <main className="shell grid gap-6 pb-10 md:pb-12">
      <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[linear-gradient(135deg,#16181a,rgba(22,24,26,0.7),rgba(220,232,93,0.08))] p-6 md:p-8">
        <div className="grid gap-3">
          <div className="skeleton h-4 w-28 rounded-full" />
          <div className="skeleton h-14 w-full max-w-4xl rounded-[1.5rem]" />
          <div className="skeleton h-5 w-full max-w-3xl rounded-full" />
          <div className="skeleton h-5 w-2/3 max-w-2xl rounded-full" />
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem] xl:items-start">
        <div className="grid gap-6">
          <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
            <div className="grid gap-2">
              <div className="skeleton h-4 w-24 rounded-full" />
              <div className="skeleton h-4 w-full max-w-2xl rounded-full" />
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
              <div className="grid gap-2 xl:col-span-2">
                <div className="skeleton h-3 w-20 rounded-full" />
                <div className="skeleton h-12 w-full rounded-[1.3rem]" />
              </div>
              <div className="grid gap-2">
                <div className="skeleton h-3 w-16 rounded-full" />
                <div className="skeleton h-12 w-full rounded-[1.3rem]" />
              </div>
              <div className="grid gap-2">
                <div className="skeleton h-3 w-24 rounded-full" />
                <div className="skeleton h-12 w-full rounded-[1.3rem]" />
              </div>
              <div className="grid gap-2 xl:col-span-2">
                <div className="skeleton h-3 w-14 rounded-full" />
                <div className="flex gap-2">
                  {Array.from({ length: 4 }).map((_, index) => (
                    <div key={`preset-skeleton-${index}`} className="skeleton h-10 w-16 rounded-full" />
                  ))}
                </div>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <div className="skeleton h-3 w-20 rounded-full" />
                <div className="skeleton h-12 w-full rounded-[1.3rem]" />
              </div>
              <div className="grid gap-2">
                <div className="skeleton h-3 w-20 rounded-full" />
                <div className="skeleton h-12 w-full rounded-[1.3rem]" />
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[rgba(255,255,255,0.06)] pt-4">
              <div className="skeleton h-4 w-56 rounded-full" />
              <div className="skeleton h-12 w-40 rounded-full" />
            </div>
          </section>

          <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, index) => (
              <article
                key={`summary-skeleton-${index}`}
                className="grid gap-2 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4"
              >
                <div className="skeleton h-3 w-16 rounded-full" />
                <div className="skeleton h-8 w-24 rounded-md" />
              </article>
            ))}
          </section>

          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="grid gap-2">
                <div className="skeleton h-4 w-24 rounded-full" />
                <div className="skeleton h-4 w-64 rounded-full" />
              </div>
              <div className="skeleton h-8 w-24 rounded-full" />
            </div>
            <div className="skeleton h-[25rem] w-full rounded-[1.6rem]" />
          </section>

          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="grid gap-2">
                <div className="skeleton h-4 w-28 rounded-full" />
                <div className="skeleton h-4 w-72 rounded-full" />
              </div>
              <div className="flex gap-2">
                <div className="skeleton h-9 w-24 rounded-full" />
                <div className="skeleton h-9 w-24 rounded-full" />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={`tester-summary-skeleton-${index}`} className="grid gap-2 rounded-[1.4rem] bg-[#090a0a] p-4">
                  <div className="skeleton h-3 w-20 rounded-full" />
                  <div className="skeleton h-4 w-full rounded-full" />
                </div>
              ))}
            </div>
            <div className="grid gap-3 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a] p-3 md:p-4">
              {Array.from({ length: 4 }).map((_, rowIndex) => (
                <div key={`tester-row-skeleton-${rowIndex}`} className="rounded-[1.4rem] bg-[#111315] p-4">
                  <div className="grid gap-3">
                    <div className="skeleton h-4 w-40 rounded-full" />
                    <div className="skeleton h-4 w-full rounded-full" />
                    <div className="skeleton h-4 w-2/3 rounded-full" />
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <aside className="grid gap-4 self-start xl:sticky xl:top-6">
          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="grid gap-2">
              <div className="skeleton h-4 w-20 rounded-full" />
              <div className="skeleton h-4 w-44 rounded-full" />
            </div>
            <div className="grid gap-2">
              <div className="skeleton h-3 w-24 rounded-full" />
              <div className="skeleton h-12 w-full rounded-[1.3rem]" />
            </div>
            <div className="flex gap-2">
              {Array.from({ length: 3 }).map((_, index) => (
                <div key={`history-filter-skeleton-${index}`} className="skeleton h-9 w-20 rounded-full" />
              ))}
            </div>
            <div className="grid gap-3">
              {Array.from({ length: 5 }).map((_, index) => (
                <div
                  key={`history-card-skeleton-${index}`}
                  className="grid gap-3 rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a] p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="grid gap-2">
                      <div className="skeleton h-4 w-32 rounded-full" />
                      <div className="skeleton h-3 w-24 rounded-full" />
                    </div>
                    <div className="skeleton h-6 w-16 rounded-full" />
                  </div>
                  <div className="grid gap-2">
                    <div className="skeleton h-4 w-28 rounded-full" />
                    <div className="skeleton h-3 w-40 rounded-full" />
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="grid gap-3 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="skeleton h-4 w-28 rounded-full" />
            <div className="grid gap-2">
              <div className="skeleton h-4 w-full rounded-full" />
              <div className="skeleton h-4 w-5/6 rounded-full" />
              <div className="skeleton h-4 w-2/3 rounded-full" />
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}

function InspectorPagination({
  page,
  pageCount,
  totalItems,
  pageSize,
  noun,
  onPageChange,
}: {
  page: number;
  pageCount: number;
  totalItems: number;
  pageSize: number;
  noun: string;
  onPageChange: (page: number) => void;
}) {
  const start = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = totalItems === 0 ? 0 : Math.min(totalItems, page * pageSize);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[rgba(255,255,255,0.06)] px-3 pb-3 pt-1 text-xs text-neutral-500 md:px-4 md:pb-4">
      <span>
        {start}-{end} of {totalItems} {noun}
      </span>
      <div className="flex items-center gap-2">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-600">
          Page {page} / {pageCount}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50 disabled:cursor-not-allowed disabled:border-[rgba(255,255,255,0.08)] disabled:text-neutral-600"
        >
          Prev
        </button>
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pageCount}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50 disabled:cursor-not-allowed disabled:border-[rgba(255,255,255,0.08)] disabled:text-neutral-600"
        >
          Next
        </button>
      </div>
    </div>
  );
}

function ChartPanelSkeleton() {
  return <div className="skeleton min-h-[26rem] w-full rounded-[2rem]" />;
}
