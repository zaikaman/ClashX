"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import { ArrowUpRight, FlaskConical, History, LoaderCircle, Play, RefreshCcw } from "lucide-react";

import { BacktestChart } from "@/components/backtests/backtest-chart";
import { useClashxAuth } from "@/lib/clashx-auth";
import type { BacktestRunDetail, BacktestRunRequestPayload, BacktestRunSummary } from "@/lib/backtests";

type SavedBot = {
  id: string;
  name: string;
  description: string;
  strategy_type: string;
  market_scope: string;
  updated_at: string;
};

type HistoryFilter = "all" | "completed" | "failed";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const INTERVAL_OPTIONS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"] as const;
const DATE_PRESETS = [
  { id: "7d", label: "7D", days: 7 },
  { id: "30d", label: "30D", days: 30 },
  { id: "90d", label: "90D", days: 90 },
  { id: "custom", label: "Custom", days: 0 },
] as const;

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

function toTimestampBounds(startDate: string, endDate: string) {
  const start = new Date(`${startDate}T00:00:00`).getTime();
  const end = new Date(`${endDate}T23:59:59.999`).getTime();
  return { start, end };
}

function formatDuration(seconds: number) {
  if (seconds <= 0) return "0m";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  if (hours <= 0) return `${minutes}m`;
  return `${hours}h ${minutes}m`;
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
  const [interval, setInterval] = useState<(typeof INTERVAL_OPTIONS)[number]>("15m");
  const [datePreset, setDatePreset] = useState<(typeof DATE_PRESETS)[number]["id"]>("30d");
  const [startDate, setStartDate] = useState(initialRange.start);
  const [endDate, setEndDate] = useState(initialRange.end);
  const [initialCapitalUsd, setInitialCapitalUsd] = useState("10000");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyFilter, setHistoryFilter] = useState<HistoryFilter>("all");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const deferredHistoryQuery = useDeferredValue(historyQuery);
  const currentRun = activeRunId ? runCache[activeRunId] ?? null : null;
  const compareRuns = compareIds.map((runId) => runCache[runId]).filter(Boolean) as BacktestRunDetail[];
  const selectedBot = bots.find((bot) => bot.id === selectedBotId) ?? null;

  useEffect(() => {
    if (!authenticated || !walletAddress) {
      setBots([]);
      setRuns([]);
      setRunCache({});
      setSelectedBotId(queryBotId ?? "");
      setActiveRunId(null);
      setCompareIds([]);
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function loadInitialState() {
      setLoading(true);
      setPageError(null);
      setHistoryError(null);
      try {
        const resolvedWallet = walletAddress;
        if (!resolvedWallet) return;
        const headers = await getAuthHeaders();
        const walletQuery = encodeURIComponent(resolvedWallet);
        const [botsResponse, runsResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/bots?wallet_address=${walletQuery}`, {
            cache: "no-store",
            headers,
          }),
          fetch(`${API_BASE_URL}/api/backtests/runs?wallet_address=${walletQuery}`, {
            cache: "no-store",
            headers,
          }),
        ]);

        const [botsPayload, runsPayload] = await Promise.all([botsResponse.json(), runsResponse.json()]);
        if (!botsResponse.ok) {
          throw new Error(("detail" in botsPayload ? botsPayload.detail : null) ?? "Could not load saved bots.");
        }
        if (!runsResponse.ok) {
          throw new Error(("detail" in runsPayload ? runsPayload.detail : null) ?? "Could not load backtest history.");
        }

        if (cancelled) return;
        const nextBots = botsPayload as SavedBot[];
        const nextRuns = runsPayload as BacktestRunSummary[];
        setBots(nextBots);
        setRuns(nextRuns);
        const preferredBotId =
          queryBotId && nextBots.some((bot) => bot.id === queryBotId)
            ? queryBotId
            : nextBots[0]?.id ?? "";
        setSelectedBotId((current) => current || preferredBotId);
        if (nextRuns[0]) {
          setActiveRunId((current) => current ?? nextRuns[0].id);
        }
      } catch (error) {
        if (!cancelled) {
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
    };
  }, [authenticated, getAuthHeaders, queryBotId, walletAddress]);

  useEffect(() => {
    if (!authenticated || !walletAddress || !activeRunId || runCache[activeRunId]) {
      return;
    }
    let cancelled = false;
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
          },
        );
        const payload = (await response.json()) as BacktestRunDetail | { detail?: string };
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Could not load backtest run." : "Could not load backtest run.");
        }
        if (cancelled) return;
        setRunCache((current) => ({ ...current, [runId]: payload as BacktestRunDetail }));
      } catch (error) {
        if (!cancelled) {
          setHistoryError(error instanceof Error ? error.message : "Could not load backtest run.");
        }
      }
    }
    void loadRunDetail(activeRunId);
    return () => {
      cancelled = true;
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
        if (!cancelled) {
          setHistoryError(error instanceof Error ? error.message : "Could not load compare runs.");
        }
      }
    }
    void loadCompareRuns();
    return () => {
      cancelled = true;
    };
  }, [authenticated, compareIds, getAuthHeaders, runCache, walletAddress]);

  const filteredRuns = useMemo(() => {
    const query = deferredHistoryQuery.trim().toLowerCase();
    return runs.filter((run) => {
      if (historyFilter !== "all" && run.status !== historyFilter) {
        return false;
      }
      if (selectedBotId && run.bot_definition_id !== selectedBotId && query.length === 0) {
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
  }, [deferredHistoryQuery, historyFilter, runs, selectedBotId]);

  async function refreshHistory() {
    if (!authenticated || !walletAddress) return;
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/api/backtests/runs?wallet_address=${encodeURIComponent(walletAddress)}`, {
        cache: "no-store",
        headers,
      });
      const payload = (await response.json()) as BacktestRunSummary[] | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Could not refresh backtests." : "Could not refresh backtests.");
      }
      setRuns(payload as BacktestRunSummary[]);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Could not refresh backtests.");
    }
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
      interval,
      start_time: start,
      end_time: end,
      initial_capital_usd: Number(initialCapitalUsd),
    };

    setRunning(true);
    setPageError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/backtests/runs`, {
        method: "POST",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      const result = (await response.json()) as BacktestRunDetail | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in result ? result.detail ?? "Backtest failed." : "Backtest failed.");
      }
      const detail = result as BacktestRunDetail;
      setRuns((current) => [detail, ...current.filter((run) => run.id !== detail.id)]);
      setRunCache((current) => ({ ...current, [detail.id]: detail }));
      setActiveRunId(detail.id);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "Backtest failed.");
    } finally {
      setRunning(false);
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
  const preflightIssues = currentRun?.result_json.preflight_issues ?? [];

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

  return (
    <main className="shell grid gap-6 pb-10 md:pb-12">
      <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[linear-gradient(135deg,#16181a,rgba(22,24,26,0.7),rgba(220,232,93,0.08))] p-6 md:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="grid gap-3">
            <span className="label text-[#dce85d]">Backtesting lab</span>
            <h1 className="max-w-4xl font-mono text-[clamp(2.1rem,5vw,4.2rem)] font-extrabold uppercase leading-[0.9] tracking-[-0.05em] text-neutral-50">
              Pressure-test every saved bot on replay.
            </h1>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400 md:text-base">
              Run candle-close simulations, inspect trade-by-trade behavior, and keep a searchable history of what each strategy looked like before it touched a live runtime.
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
        </div>
      </section>

      {pageError ? (
        <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">{pageError}</article>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="grid gap-6">
          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
            <div className="grid gap-2">
              <span className="label text-[#74b97f]">Run controls</span>
              <p className="text-sm leading-7 text-neutral-400">
                Pick a saved bot, set the replay window, and launch a synchronous historical run against Pacifica candle data.
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
              <label className="grid min-w-0 gap-1.5 text-sm text-neutral-400">
                Interval
                <select
                  value={interval}
                  onChange={(event) => setInterval(event.target.value as (typeof INTERVAL_OPTIONS)[number])}
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3.5 py-3 text-sm text-neutral-50 outline-none transition w-full focus:border-[#dce85d]"
                >
                  {INTERVAL_OPTIONS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
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
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[rgba(255,255,255,0.06)] pt-4">
              <div className="text-sm text-neutral-500">
                {selectedBot ? `${selectedBot.strategy_type} / ${selectedBot.market_scope}` : "Pick a bot to unlock the replay settings."}
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
          </section>

          {summary ? (
            <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
              {[
                { label: "Net PnL", value: formatMoney(summary.pnl_total), tone: summary.pnl_total >= 0 ? "text-[#74b97f]" : "text-[#e06c6e]" },
                { label: "Net PnL %", value: formatPercent(summary.pnl_total_pct), tone: summary.pnl_total_pct >= 0 ? "text-[#74b97f]" : "text-[#e06c6e]" },
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

          {compareRuns.length > 1 ? (
            <section className="grid gap-3 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:grid-cols-3">
              {compareRuns.map((run, index) => (
                <article key={run.id} className="grid gap-2 rounded-[1.5rem] bg-[#090a0a] p-4">
                  <span className="label" style={{ color: ["#dce85d", "#74b97f", "#8ec5ff"][index % 3] }}>
                    Compare {index + 1}
                  </span>
                  <div className="font-mono text-lg font-bold uppercase text-neutral-50">{run.bot_name_snapshot}</div>
                  <div className="text-sm text-neutral-400">
                    {formatMoney(run.pnl_total)} / {formatPercent(run.pnl_total_pct)}
                  </div>
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
                <p className="text-sm text-neutral-500">
                  {summary?.primary_symbol ? `${summary.primary_symbol} candles on the right scale, equity on the left.` : "Open a run to load the chart."}
                </p>
              </div>
              {currentRun ? (
                <div className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
                  {currentRun.interval} replay
                </div>
              ) : null}
            </div>
            <BacktestChart run={currentRun} compareRuns={compareRuns} />
          </section>

          <section className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
            <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
              <div className="flex items-center justify-between gap-3">
                <span className="label text-[#dce85d]">Triggered events</span>
                <span className="text-xs text-neutral-500">
                  {currentRun?.result_json.trigger_events.length ?? 0} events
                </span>
              </div>
              <div className="grid gap-3">
                {currentRun?.result_json.trigger_events.length ? (
                  currentRun.result_json.trigger_events.map((event) => (
                    <div key={`${event.timestamp}-${event.title}-${event.detail}`} className="rounded-[1.4rem] bg-[#090a0a] p-4">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-semibold text-neutral-50">{event.title}</span>
                        <span className="text-[0.62rem] uppercase tracking-[0.16em] text-neutral-500">{event.symbol}</span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-neutral-400">{event.detail}</p>
                      <p className="mt-2 text-xs text-neutral-500">{new Date(event.timestamp).toLocaleString()}</p>
                    </div>
                  ))
                ) : (
                  <div className="rounded-[1.4rem] bg-[#090a0a] p-4 text-sm leading-6 text-neutral-500">
                    Actionable ticks will appear here after a run is loaded.
                  </div>
                )}
              </div>
            </article>

            <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
              <div className="flex items-center justify-between gap-3">
                <span className="label text-[#74b97f]">Trade log</span>
                <span className="text-xs text-neutral-500">{currentRun?.result_json.trades.length ?? 0} rows</span>
              </div>
              <div className="grid gap-3">
                {currentRun?.result_json.trades.length ? (
                  currentRun.result_json.trades.map((trade) => (
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
          </section>
        </div>

        <aside className="grid gap-4 self-start xl:sticky xl:top-6">
          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="grid gap-1">
                <span className="label text-[#dce85d]">Run history</span>
                <p className="text-sm text-neutral-500">Keep up to three runs selected for compare.</p>
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
