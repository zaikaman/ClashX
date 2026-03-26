"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  Check,
  PauseCircle,
  Play,
  Power,
  RefreshCw,
  Search,
  SquareStack,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  PacificaOnboardingChecklist,
  type PacificaOnboardingStatus,
} from "@/components/pacifica/onboarding-checklist";
import { useClashxAuth } from "@/lib/clashx-auth";
import {
  PacificaReadinessError,
  assertPacificaDeployReadiness,
} from "@/lib/pacifica-readiness";
import type { BotPerformance } from "@/lib/bot-performance";

type RuntimeSummary = {
  id: string;
  status: string;
  mode: string;
  updated_at: string;
  deployed_at?: string | null;
  stopped_at?: string | null;
};

type BotFleetItem = {
  id: string;
  name: string;
  description: string;
  wallet_address: string;
  visibility: string;
  authoring_mode: string;
  strategy_type: string;
  market_scope: string;
  updated_at: string;
  runtime?: RuntimeSummary | null;
  performance?: BotPerformance | null;
};

type StatusFilter = "all" | "active" | "paused" | "stopped" | "draft";
type BotAction = "deploy" | "resume" | "stop" | "delete";
type Feedback = {
  tone: "error" | "success" | "info";
  message: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const PAGE_SIZE = 10;
const DEFAULT_RISK_POLICY_JSON = JSON.stringify(
  {
    max_leverage: 5,
    max_order_size_usd: 200,
    allocated_capital_usd: 200,
    max_open_positions: 1,
    cooldown_seconds: 45,
    max_drawdown_pct: 18,
  },
  null,
  2,
);

const STATUS_META: Record<
  Exclude<StatusFilter, "all">,
  { label: string; chipClassName: string; panelClassName: string; note: string }
> = {
  active: {
    label: "Live",
    chipClassName: "border-[#74b97f]/35 bg-[#74b97f]/12 text-[#a9d7b1]",
    panelClassName: "border-[#74b97f]/18 bg-[#74b97f]/8",
    note: "This bot is currently running.",
  },
  paused: {
    label: "Paused",
    chipClassName: "border-[#dce85d]/35 bg-[#dce85d]/12 text-[#e3eca0]",
    panelClassName: "border-[#dce85d]/18 bg-[#dce85d]/8",
    note: "The runtime is set up, but paused for now.",
  },
  stopped: {
    label: "Stopped",
    chipClassName: "border-[rgba(255,255,255,0.12)] bg-[rgba(255,255,255,0.05)] text-neutral-300",
    panelClassName: "border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)]",
    note: "You can deploy it again or remove it.",
  },
  draft: {
    label: "Draft",
    chipClassName: "border-[#6f7480]/30 bg-[#202328] text-neutral-300",
    panelClassName: "border-[rgba(255,255,255,0.08)] bg-[#111315]",
    note: "Saved, but not deployed yet.",
  },
};

const STATUS_PRIORITY: Record<Exclude<StatusFilter, "all">, number> = {
  active: 0,
  paused: 1,
  stopped: 2,
  draft: 3,
};

function joinClasses(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function humanize(value: string) {
  return value.replace(/_/g, " ");
}

function authoringLabel() {
  return "Builder";
}

function formatSignedAmount(value: number) {
  const absolute = Math.abs(value);
  const precision = absolute >= 1 ? 2 : absolute >= 0.1 ? 3 : absolute > 0 ? 4 : 2;
  return `${value >= 0 ? "+" : "-"}${absolute.toFixed(precision)}%`;
}

function formatSignedUsd(value: number) {
  const absolute = Math.abs(value);
  const precision = absolute > 0 && absolute < 0.01 ? 4 : 2;
  return `${value >= 0 ? "+" : "-"}$${absolute.toFixed(precision)}`;
}

function performanceTone(value: number) {
  return value >= 0 ? "text-[#74b97f]" : "text-[#dce85d]";
}

function getBotStatus(bot: BotFleetItem): Exclude<StatusFilter, "all"> {
  if (!bot.runtime) {
    return "draft";
  }
  if (bot.runtime.status === "active" || bot.runtime.status === "paused" || bot.runtime.status === "stopped") {
    return bot.runtime.status;
  }
  return "draft";
}

function isDeployableBot(bot: BotFleetItem) {
  const status = getBotStatus(bot);
  return status === "draft" || status === "stopped";
}

function isStoppableBot(bot: BotFleetItem) {
  const status = getBotStatus(bot);
  return status === "active" || status === "paused";
}

function isDeletableBot(bot: BotFleetItem) {
  const status = getBotStatus(bot);
  return status === "draft" || status === "stopped";
}

function FleetStatCard({
  icon,
  eyebrow,
  value,
  detail,
}: {
  icon: ReactNode;
  eyebrow: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="grid gap-2 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <div className="flex items-center justify-between">
        <span className="label text-neutral-400">{eyebrow}</span>
        <span className="text-neutral-500">{icon}</span>
      </div>
      <div className="font-mono text-2xl font-bold uppercase text-neutral-50">{value}</div>
      <p className="text-sm leading-6 text-neutral-400">{detail}</p>
    </article>
  );
}

function FilterChip({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={joinClasses(
        "rounded-full border px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] transition",
        active
          ? "border-[#dce85d]/40 bg-[#dce85d]/12 text-[#e3eca0]"
          : "border-[rgba(255,255,255,0.12)] text-neutral-300 hover:border-white hover:text-neutral-50",
      )}
    >
      {label}
    </button>
  );
}

function StatusBadge({ status }: { status: Exclude<StatusFilter, "all"> }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={joinClasses(
        "rounded-full border px-2.5 py-1 text-[0.55rem] font-semibold uppercase tracking-[0.16em]",
        meta.chipClassName,
      )}
    >
      {meta.label}
    </span>
  );
}

function MetaBadge({ label }: { label: string }) {
  return (
    <span className="rounded-full border border-[rgba(255,255,255,0.06)] px-2.5 py-1 text-[0.55rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
      {label}
    </span>
  );
}

function FleetRowSkeleton() {
  return (
    <article className="grid gap-6 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6 xl:grid-cols-[auto_1fr_auto] xl:items-start">
      <div className="skeleton h-6 w-6 rounded-md" />
      <div className="grid gap-8 xl:grid-cols-[1.5fr_2fr]">
        <div className="grid gap-4">
          <div className="flex items-center gap-3">
            <div className="skeleton h-7 w-48 rounded-none" />
            <div className="skeleton h-5 w-16 rounded-full" />
            <div className="skeleton h-5 w-14 rounded-full" />
          </div>
          <div className="skeleton h-4 w-4/5 rounded-none" />
          <div className="flex gap-2">
            <div className="skeleton h-5 w-24 rounded-full" />
            <div className="skeleton h-5 w-32 rounded-full" />
          </div>
        </div>
        
        <div className="grid grid-cols-3 gap-6 pt-2">
          <div className="grid gap-3">
            <div className="skeleton h-3 w-16 rounded-none" />
            <div className="skeleton h-6 w-24 rounded-none" />
            <div className="skeleton h-3 w-32 rounded-none" />
          </div>
          <div className="grid gap-3">
            <div className="skeleton h-3 w-16 rounded-none" />
            <div className="skeleton h-6 w-24 rounded-none" />
            <div className="skeleton h-3 w-32 rounded-none" />
          </div>
          <div className="grid gap-3">
            <div className="skeleton h-3 w-16 rounded-none" />
            <div className="skeleton h-6 w-24 rounded-none" />
            <div className="skeleton h-3 w-32 rounded-none" />
          </div>
        </div>
      </div>
      <div className="mt-6 flex flex-col items-end gap-3 xl:mt-0">
        <div className="skeleton h-8 w-28 rounded-none" />
        <div className="skeleton h-8 w-28 rounded-none" />
      </div>
    </article>
  );
}

export function BotsFleetPage() {
  const { authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();
  const [bots, setBots] = useState<BotFleetItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [bulkRiskPolicy, setBulkRiskPolicy] = useState(DEFAULT_RISK_POLICY_JSON);
  const [policyEditorOpen, setPolicyEditorOpen] = useState(false);
  const [deleteArmed, setDeleteArmed] = useState(false);
  const [actionState, setActionState] = useState<{ label: string; completed: number; total: number } | null>(null);
  const [deployGuideOpen, setDeployGuideOpen] = useState(false);
  const [deployGuideStatus, setDeployGuideStatus] = useState<PacificaOnboardingStatus>({
    ready: false,
    blocker: "Sign in with your trading wallet before you deploy.",
    fundingVerified: false,
    appAccessVerified: false,
    agentAuthorized: false,
  });

  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }),
    [],
  );

  useEffect(() => {
    const resolvedWallet = walletAddress;
    if (!authenticated || !resolvedWallet) {
      setBots([]);
      setError(null);
      setFeedback(null);
      setSelectedIds([]);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    async function loadBots() {
      setLoading(true);
      try {
        const headers = await getAuthHeaders();
        const walletParam = encodeURIComponent(resolvedWallet ?? "");

        const fastResponse = await fetch(
          `${API_BASE_URL}/api/bots?wallet_address=${walletParam}&include_performance=true&performance_mode=fast`,
          {
            headers,
            signal: controller.signal,
          },
        );
        const fastPayload = (await fastResponse.json()) as BotFleetItem[] | { detail?: string };
        if (!fastResponse.ok) {
          throw new Error(
            "detail" in fastPayload ? fastPayload.detail ?? "Could not load bots" : "Could not load bots",
          );
        }

        if (cancelled || controller.signal.aborted) {
          return;
        }

        setBots(fastPayload as BotFleetItem[]);
        setError(null);
        setLoading(false);

        const fullResponse = await fetch(
          `${API_BASE_URL}/api/bots?wallet_address=${walletParam}&include_performance=true&performance_mode=full`,
          {
            headers,
            signal: controller.signal,
          },
        );
        if (!fullResponse.ok || cancelled || controller.signal.aborted) {
          return;
        }
        const fullPayload = (await fullResponse.json()) as BotFleetItem[];
        if (!cancelled && !controller.signal.aborted) {
          setBots(fullPayload);
        }
      } catch (loadError) {
        if (!cancelled && !controller.signal.aborted) {
          setError(loadError instanceof Error ? loadError.message : "Could not load bots");
        }
      } finally {
        if (!cancelled && !controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void loadBots();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [authenticated, walletAddress, getAuthHeaders, refreshKey]);

  useEffect(() => {
    setSelectedIds((current) => current.filter((id) => bots.some((bot) => bot.id === id)));
  }, [bots]);

  useEffect(() => {
    setDeleteArmed(false);
  }, [selectedIds, query, statusFilter]);

  useEffect(() => {
    setCurrentPage(1);
  }, [query, statusFilter]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const fleetCounts = useMemo(
    () =>
      bots.reduce(
        (counts, bot) => {
          const status = getBotStatus(bot);
          counts[status] += 1;
          return counts;
        },
        { active: 0, paused: 0, stopped: 0, draft: 0 },
      ),
    [bots],
  );

  const visibleBots = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return [...bots]
      .filter((bot) => {
        const status = getBotStatus(bot);
        const matchesStatus = statusFilter === "all" || status === statusFilter;
        const matchesQuery =
          !normalizedQuery ||
          bot.name.toLowerCase().includes(normalizedQuery) ||
          bot.description.toLowerCase().includes(normalizedQuery) ||
          bot.market_scope.toLowerCase().includes(normalizedQuery) ||
          bot.strategy_type.toLowerCase().includes(normalizedQuery);
        return matchesStatus && matchesQuery;
      })
      .sort((left, right) => {
        const leftStatus = getBotStatus(left);
        const rightStatus = getBotStatus(right);
        if (STATUS_PRIORITY[leftStatus] !== STATUS_PRIORITY[rightStatus]) {
          return STATUS_PRIORITY[leftStatus] - STATUS_PRIORITY[rightStatus];
        }
        return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
      });
  }, [bots, query, statusFilter]);

  const selectedBots = useMemo(() => bots.filter((bot) => selectedSet.has(bot.id)), [bots, selectedSet]);
  const totalPages = Math.max(1, Math.ceil(visibleBots.length / PAGE_SIZE));
  const paginatedVisibleBots = useMemo(() => {
    const startIndex = (currentPage - 1) * PAGE_SIZE;
    return visibleBots.slice(startIndex, startIndex + PAGE_SIZE);
  }, [currentPage, visibleBots]);
  const visibleSelectedCount = paginatedVisibleBots.filter((bot) => selectedSet.has(bot.id)).length;
  const allVisibleSelected = paginatedVisibleBots.length > 0 && visibleSelectedCount === paginatedVisibleBots.length;
  const deployableSelected = selectedBots.filter(isDeployableBot);
  const stoppableSelected = selectedBots.filter(isStoppableBot);
  const deletableSelected = selectedBots.filter(isDeletableBot);
  const walletLabel = walletAddress ? `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}` : "Not connected";
  const readyToDeployCount = fleetCounts.draft + fleetCounts.stopped;
  const busy = actionState !== null;
  const pageStart = visibleBots.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(currentPage * PAGE_SIZE, visibleBots.length);

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  async function readError(response: Response, fallback: string) {
    try {
      const payload = (await response.json()) as { detail?: string };
      return payload.detail ?? fallback;
    } catch {
      return fallback;
    }
  }

  async function requestBotAction(botId: string, action: Exclude<BotAction, "delete">, riskPolicyJson?: string) {
    if (!walletAddress) {
      throw new Error("Connect the wallet tied to this fleet first.");
    }
    const url =
      action === "deploy"
        ? `${API_BASE_URL}/api/bots/${botId}/deploy`
        : `${API_BASE_URL}/api/bots/${botId}/${action}?wallet_address=${encodeURIComponent(walletAddress)}`;
    const headers =
      action === "deploy" ? await getAuthHeaders({ "Content-Type": "application/json" }) : await getAuthHeaders();
    const body =
      action === "deploy"
        ? JSON.stringify({
            wallet_address: walletAddress,
            risk_policy_json: JSON.parse(riskPolicyJson ?? DEFAULT_RISK_POLICY_JSON) as Record<string, unknown>,
          })
        : undefined;

    const response = await fetch(url, { method: "POST", headers, body });
    if (!response.ok) {
      throw new Error(await readError(response, "Bot action failed"));
    }
    return (await response.json()) as RuntimeSummary;
  }

  async function deleteBot(botId: string) {
    if (!walletAddress) {
      throw new Error("Connect the wallet tied to this fleet first.");
    }
    const response = await fetch(`${API_BASE_URL}/api/bots/${botId}?wallet_address=${encodeURIComponent(walletAddress)}`, {
      method: "DELETE",
      headers: await getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(await readError(response, "Could not delete bot"));
    }
  }

  function applyRuntimeUpdate(botId: string, runtime: RuntimeSummary) {
    setBots((current) => current.map((bot) => (bot.id === botId ? { ...bot, runtime } : bot)));
  }

  function removeBotFromState(botId: string) {
    setBots((current) => current.filter((bot) => bot.id !== botId));
    setSelectedIds((current) => current.filter((id) => id !== botId));
  }

  async function runSingleAction(bot: BotFleetItem, action: Exclude<BotAction, "delete">) {
    if (action === "deploy" && !deployGuideStatus.ready) {
      setDeployGuideOpen(true);
      return;
    }

    if (action === "deploy" && walletAddress) {
      try {
        await assertPacificaDeployReadiness(walletAddress, getAuthHeaders);
      } catch (actionError) {
        if (actionError instanceof PacificaReadinessError) {
          setDeployGuideOpen(true);
        }
        setFeedback({
          tone: "error",
          message: actionError instanceof Error ? actionError.message : "Pacifica readiness check failed",
        });
        return;
      }
    }

    const label = `${action === "deploy" ? "Deploying" : action === "resume" ? "Resuming" : "Stopping"} ${bot.name}`;
    setFeedback(null);
    setActionState({ label, completed: 0, total: 1 });

    try {
      const runtime = await requestBotAction(bot.id, action, bulkRiskPolicy);
      applyRuntimeUpdate(bot.id, runtime);
      setFeedback({
        tone: "success",
        message:
          action === "deploy"
            ? `${bot.name} is live now.`
            : action === "resume"
              ? `${bot.name} is running again.`
              : `${bot.name} has been stopped.`,
      });
      setRefreshKey((value) => value + 1);
    } catch (actionError) {
      setFeedback({
        tone: "error",
        message: actionError instanceof Error ? actionError.message : "Bot action failed",
      });
    } finally {
      setActionState(null);
    }
  }

  async function runBulkAction(action: Extract<BotAction, "deploy" | "stop" | "delete">) {
    const eligibleBots =
      action === "deploy" ? deployableSelected : action === "stop" ? stoppableSelected : deletableSelected;

    if (eligibleBots.length === 0) {
      setFeedback({
        tone: "info",
        message:
          action === "deploy"
            ? "Pick at least one draft or stopped bot to deploy."
            : action === "stop"
              ? "Pick at least one live or paused bot to stop."
              : "You can only delete drafts or bots that have already been stopped.",
      });
      return;
    }

    if (action === "deploy" && !deployGuideStatus.ready) {
      setDeployGuideOpen(true);
      return;
    }

    if (action === "deploy") {
      try {
        JSON.parse(bulkRiskPolicy);
      } catch {
        setFeedback({
          tone: "error",
          message: "That deploy policy JSON is invalid. Fix it before you deploy the selected bots.",
        });
        setPolicyEditorOpen(true);
        return;
      }

      if (walletAddress) {
        try {
          await assertPacificaDeployReadiness(walletAddress, getAuthHeaders);
        } catch (actionError) {
          if (actionError instanceof PacificaReadinessError) {
            setDeployGuideOpen(true);
          }
          setFeedback({
            tone: "error",
            message: actionError instanceof Error ? actionError.message : "Pacifica readiness check failed",
          });
          return;
        }
      }
    }

    setFeedback(null);
    setActionState({
      label:
        action === "deploy"
          ? "Deploying selected bots"
          : action === "stop"
            ? "Stopping selected bots"
            : "Deleting selected bots",
      completed: 0,
      total: eligibleBots.length,
    });

    const failures: string[] = [];

    for (let index = 0; index < eligibleBots.length; index += 1) {
      const bot = eligibleBots[index];
      try {
        if (action === "delete") {
          await deleteBot(bot.id);
          removeBotFromState(bot.id);
        } else {
          const runtime = await requestBotAction(bot.id, action, bulkRiskPolicy);
          applyRuntimeUpdate(bot.id, runtime);
        }
      } catch (actionError) {
        failures.push(`${bot.name}: ${actionError instanceof Error ? actionError.message : "Action failed"}`);
      } finally {
        setActionState((current) => (current ? { ...current, completed: index + 1 } : current));
      }
    }

    setDeleteArmed(false);
    setActionState(null);
    setRefreshKey((value) => value + 1);

    if (failures.length > 0) {
      setFeedback({
        tone: "error",
        message: failures.slice(0, 3).join("  "),
      });
      return;
    }

    setFeedback({
      tone: "success",
      message:
        action === "deploy"
          ? `${eligibleBots.length} bot${eligibleBots.length === 1 ? "" : "s"} deployed.`
          : action === "stop"
            ? `${eligibleBots.length} bot${eligibleBots.length === 1 ? "" : "s"} stopped.`
            : `${eligibleBots.length} bot${eligibleBots.length === 1 ? "" : "s"} deleted.`,
    });
  }

  function toggleBotSelection(botId: string) {
    setSelectedIds((current) => (current.includes(botId) ? current.filter((id) => id !== botId) : [...current, botId]));
  }

  function selectVisibleBots() {
    if (allVisibleSelected) {
      const visibleIds = new Set(paginatedVisibleBots.map((bot) => bot.id));
      setSelectedIds((current) => current.filter((id) => !visibleIds.has(id)));
      return;
    }
    setSelectedIds((current) => Array.from(new Set([...current, ...paginatedVisibleBots.map((bot) => bot.id)])));
  }

  function selectByPredicate(predicate: (bot: BotFleetItem) => boolean) {
    setSelectedIds(paginatedVisibleBots.filter(predicate).map((bot) => bot.id));
  }

  return (
    <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">
      <PacificaOnboardingChecklist
        open={deployGuideOpen}
        onClose={() => setDeployGuideOpen(false)}
        mode="builder"
        onStatusChange={setDeployGuideStatus}
        walletAddressOverride={walletAddress}
      />
      <section className="flex flex-wrap items-center gap-2">
        {!authenticated ? (
          <button
            type="button"
            onClick={login}
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
          >
            Sign in to load my bots
          </button>
        ) : null}
        <Link
          href="/build"
          className="rounded-full bg-[#dce85d] px-5 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
        >
          New bot draft
        </Link>
        {authenticated ? (
          <button
            type="button"
            onClick={() => setRefreshKey((value) => value + 1)}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-white hover:text-neutral-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw className={joinClasses("h-3.5 w-3.5", busy ? "animate-spin" : "")} />
            Refresh fleet
          </button>
        ) : null}
      </section>

      {error ? (
        <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      {feedback ? (
        <article
          className={joinClasses(
            "rounded-2xl px-5 py-4 text-sm",
            feedback.tone === "error"
              ? "border border-[#dce85d]/30 bg-[#dce85d]/10 text-neutral-50"
              : feedback.tone === "success"
                ? "border border-[#74b97f]/30 bg-[#74b97f]/10 text-neutral-50"
                : "border border-[rgba(255,255,255,0.08)] bg-[#16181a] text-neutral-200",
          )}
        >
          {feedback.message}
        </article>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(18rem,0.75fr)]">
        <article className="relative overflow-hidden rounded-[2rem] border border-[#dce85d]/14 bg-[#16181a] p-6">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.14),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(116,185,127,0.12),transparent_30%)]" />
          <div className="relative grid gap-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="label text-[#dce85d]">Fleet board</span>
              <span className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">
                {authenticated ? `${bots.length} bots loaded` : "Wallet locked"}
              </span>
            </div>
            <div className="grid gap-3">
              <h2 className="max-w-4xl font-mono text-3xl font-bold uppercase tracking-tight text-neutral-50 md:text-[2.35rem]">
                Keep track of every bot in one place instead of opening each runtime one by one.
              </h2>
              <p className="max-w-3xl text-sm leading-7 text-neutral-400">
                You can see what is live at a glance, filter the list quickly, and run bulk actions without guessing which bots are deployed.
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0f1112] px-4 py-4">
                <div className="label text-[#74b97f]">Live right now</div>
                <div className="mt-2 font-mono text-2xl font-bold uppercase text-neutral-50">{loading ? "..." : fleetCounts.active}</div>
                <p className="mt-2 text-xs leading-6 text-neutral-500">Bots currently running on {walletLabel}.</p>
              </div>
              <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0f1112] px-4 py-4">
                <div className="label text-[#dce85d]">Ready for action</div>
                <div className="mt-2 font-mono text-2xl font-bold uppercase text-neutral-50">{loading ? "..." : readyToDeployCount}</div>
                <p className="mt-2 text-xs leading-6 text-neutral-500">Drafts and stopped bots you can launch next.</p>
              </div>
              <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0f1112] px-4 py-4">
                <div className="label text-neutral-400">Current wallet</div>
                <div className="mt-2 font-mono text-2xl font-bold uppercase text-neutral-50">{loading ? "..." : walletLabel}</div>
                <p className="mt-2 text-xs leading-6 text-neutral-500">Bulk actions always use the connected wallet.</p>
              </div>
            </div>
          </div>
        </article>
        <aside className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
          <FleetStatCard icon={<Play className="h-4 w-4" />} eyebrow="Draft pipeline" value={loading ? "..." : `${fleetCounts.draft}`} detail="Saved drafts that are ready for validation, tuning, or deployment." />
          <FleetStatCard icon={<PauseCircle className="h-4 w-4" />} eyebrow="Needs attention" value={loading ? "..." : `${fleetCounts.paused + fleetCounts.stopped}`} detail="Paused and stopped bots are easiest to review together." />
          <FleetStatCard icon={<SquareStack className="h-4 w-4" />} eyebrow="Selection" value={`${selectedBots.length}`} detail="Filter first, then select the bots you want to act on." />
        </aside>
      </section>

      {!authenticated ? (
        <article className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <span className="label text-[#dce85d]">Sign in required</span>
          <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
            Connect your wallet to manage your bots
          </h2>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            Once you sign in, this page becomes the easiest way to see what is live, what is still a draft, and what needs attention.
          </p>
        </article>
      ) : (
        <>
          <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(20rem,0.9fr)]">
              <label className="grid gap-2">
                <span className="label text-[#dce85d]">Search your bots</span>
                <span className="flex items-center gap-3 rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0f1112] px-4 py-3">
                  <Search className="h-4 w-4 text-neutral-500" />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search by name, strategy, description, or market"
                    className="w-full bg-transparent text-sm text-neutral-50 outline-none placeholder:text-neutral-500"
                  />
                </span>
              </label>

              <div className="grid gap-4">
                <div className="grid gap-2">
                  <span className="label text-neutral-400">Show</span>
                  <div className="flex flex-wrap gap-2">
                    {(["all", "active", "paused", "stopped", "draft"] as StatusFilter[]).map((option) => (
                      <FilterChip
                        key={option}
                        active={statusFilter === option}
                        label={option === "all" ? `All (${bots.length})` : `${STATUS_META[option].label} (${fleetCounts[option]})`}
                        onClick={() => setStatusFilter(option)}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 border-t border-[rgba(255,255,255,0.06)] pt-4">
              <button
                type="button"
                onClick={selectVisibleBots}
                disabled={visibleBots.length === 0 || busy}
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {allVisibleSelected ? "Clear visible" : "Select visible"}
              </button>
              <button
                type="button"
                onClick={() => selectByPredicate((bot) => getBotStatus(bot) === "active")}
                disabled={busy}
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Select live
              </button>
              <button
                type="button"
                onClick={() => selectByPredicate(isDeployableBot)}
                disabled={busy}
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Select ready
              </button>
              <button
                type="button"
                onClick={() => setSelectedIds([])}
                disabled={selectedIds.length === 0 || busy}
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Clear selection
              </button>
              <span className="ml-auto text-xs text-neutral-500">
                Showing {pageStart}-{pageEnd} of {visibleBots.length} filtered / {bots.length} total
              </span>
            </div>
          </section>

          {selectedBots.length > 0 ? (
            <section className="grid gap-4 rounded-[2rem] border border-[#dce85d]/14 bg-[#141618] p-5 md:p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="grid gap-1">
                  <span className="label text-[#dce85d]">Bulk actions</span>
                  <h3 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                    {selectedBots.length} bot{selectedBots.length === 1 ? "" : "s"} selected
                  </h3>
                  <p className="text-sm leading-7 text-neutral-400">
                    {deployableSelected.length} ready to deploy, {stoppableSelected.length} ready to stop, and {deletableSelected.length} safe to delete.
                  </p>
                </div>
                {actionState ? (
                  <div className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0f1112] px-4 py-3 text-sm text-neutral-300">
                    {actionState.label}: {actionState.completed}/{actionState.total}
                  </div>
                ) : null}
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void runBulkAction("deploy")}
                  disabled={deployableSelected.length === 0 || busy}
                  className="inline-flex items-center gap-2 rounded-full bg-[#dce85d] px-5 py-2.5 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Play className="h-3.5 w-3.5" />
                  Deploy selected
                </button>
                <button
                  type="button"
                  onClick={() => void runBulkAction("stop")}
                  disabled={stoppableSelected.length === 0 || busy}
                  className="inline-flex items-center gap-2 rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-2.5 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Power className="h-3.5 w-3.5" />
                  Stop selected
                </button>
                <button
                  type="button"
                  onClick={() => setPolicyEditorOpen((current) => !current)}
                  className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-2.5 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50"
                >
                  {policyEditorOpen ? "Hide deploy policy" : "Edit deploy policy"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (!deleteArmed) {
                      setDeleteArmed(true);
                      return;
                    }
                    void runBulkAction("delete");
                  }}
                  disabled={deletableSelected.length === 0 || busy}
                  className={joinClasses(
                    "inline-flex items-center gap-2 rounded-full border px-5 py-2.5 text-[0.68rem] font-semibold uppercase tracking-[0.16em] transition disabled:cursor-not-allowed disabled:opacity-50",
                    deleteArmed
                      ? "border-[#dce85d]/50 bg-[#dce85d]/10 text-[#e6edaf] hover:border-[#dce85d] hover:bg-[#dce85d]/16"
                      : "border-[rgba(255,255,255,0.12)] text-neutral-300 hover:border-[#dce85d] hover:text-[#dce85d]",
                  )}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {deleteArmed ? "Confirm delete" : "Arm delete"}
                </button>
                {deleteArmed ? (
                  <button
                    type="button"
                    onClick={() => setDeleteArmed(false)}
                    className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-2.5 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50"
                  >
                    Cancel
                  </button>
                ) : null}
              </div>

              {policyEditorOpen ? (
                <label className="grid gap-2">
                  <span className="label text-[#74b97f]">Deploy policy JSON</span>
                  <textarea
                    value={bulkRiskPolicy}
                    onChange={(event) => setBulkRiskPolicy(event.target.value)}
                    rows={7}
                    className="min-h-[11rem] rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0f1112] px-4 py-3 font-mono text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
                  />
                  <span className="text-xs leading-6 text-neutral-500">
                    This same payload will be used for every selected deploy. Include `max_open_positions` here when you want a stricter cap on how many live entries each runtime can hold.
                  </span>
                </label>
              ) : null}
            </section>
          ) : null}

          <section className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="grid gap-1">
                <span className="label text-neutral-400">Fleet roster</span>
                <h3 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                  See what each bot is doing before you open it
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs uppercase tracking-[0.16em] text-neutral-500">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  type="button"
                  onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                  disabled={currentPage === 1}
                  className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Prev
                </button>
                <button
                  type="button"
                  onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                  disabled={currentPage === totalPages}
                  className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>

            {loading ? (
              <>
                <FleetRowSkeleton />
                <FleetRowSkeleton />
                <FleetRowSkeleton />
              </>
            ) : bots.length === 0 ? (
              <article className="grid gap-3 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-6 py-8">
                <span className="label text-[#dce85d]">Nothing saved yet</span>
                <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                  Start with a new bot draft
                </h2>
                <p className="max-w-3xl text-sm leading-7 text-neutral-400">
                  Open Builder studio for a guided setup, validate the rules, and come back here when the draft is ready to deploy.
                </p>
              </article>
            ) : visibleBots.length === 0 ? (
              <article className="grid gap-3 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-6 py-8">
                <span className="label text-[#dce85d]">No matches</span>
                <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                  No bots match the current filters
                </h2>
                <p className="max-w-3xl text-sm leading-7 text-neutral-400">
                  Try clearing the search or widening the filters to see more of your bots again.
                </p>
              </article>
            ) : (
              paginatedVisibleBots.map((bot, index) => {
                const status = getBotStatus(bot);
                const meta = STATUS_META[status];
                const selected = selectedSet.has(bot.id);
                const primaryAction =
                  status === "active"
                    ? { label: "Stop", action: "stop" as const }
                    : status === "paused"
                      ? { label: "Resume", action: "resume" as const }
                      : { label: "Deploy", action: "deploy" as const };

                return (
                  <article
                    key={bot.id}
                    className={joinClasses(
                      "stagger-in group relative grid gap-6 rounded-[2rem] border bg-[#16181a] p-6 transition duration-300 xl:grid-cols-[auto_1fr_auto] xl:items-start",
                      selected
                        ? "border-[#dce85d]/40"
                        : "border-[rgba(255,255,255,0.06)] hover:border-[rgba(255,255,255,0.12)]"
                    )}
                    style={{ animationDelay: `${index * 35}ms` }}
                  >
                    <button
                      type="button"
                      onClick={() => toggleBotSelection(bot.id)}
                      className={joinClasses(
                        "mt-1 flex h-6 w-6 shrink-0 cursor-pointer items-center justify-center rounded-md border transition-all duration-200",
                        selected
                          ? "border-[#dce85d] bg-[#dce85d] text-[#090a0a]"
                          : "border-[rgba(255,255,255,0.15)] bg-transparent text-transparent group-hover:border-[rgba(255,255,255,0.3)]"
                      )}
                      aria-label={selected ? `Deselect ${bot.name}` : `Select ${bot.name}`}
                    >
                      <Check className={joinClasses("h-3.5 w-3.5 transition-transform duration-200", selected ? "scale-100" : "scale-50")} strokeWidth={4} />
                    </button>

                    <div className="grid gap-8 xl:grid-cols-[1.5fr_2fr] xl:items-start">
                      <div className="grid gap-4">
                        <div className="flex flex-wrap items-center gap-3">
                          <Link
                            href={`/bots/${bot.id}`}
                            className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50 transition hover:text-[#dce85d]"
                          >
                            {bot.name}
                          </Link>
                          <StatusBadge status={status} />
                          <MetaBadge label={bot.visibility} />
                        </div>
                        <p className="line-clamp-2 max-w-lg text-sm leading-relaxed text-neutral-400">
                          {bot.description || "No description yet."}
                        </p>
                        <div className="flex flex-wrap gap-2 text-[0.6rem] uppercase tracking-[0.16em]">
                          <span className="text-neutral-500">MKT: <span className="text-neutral-300">{bot.market_scope}</span></span>
                          <span className="text-neutral-600">|</span>
                          <span className="text-neutral-500">STR: <span className="text-neutral-300">{humanize(bot.strategy_type)}</span></span>
                          <span className="text-neutral-600">|</span>
                          <span className="text-neutral-500">BLD: <span className="text-neutral-300">{authoringLabel()}</span></span>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-x-8 gap-y-6 md:grid-cols-3">
                        <div className="grid gap-2">
                          <span className="text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Runtime</span>
                          <div className={joinClasses("font-mono text-[1.1rem] font-bold uppercase tracking-tight", status === "active" ? "text-[#74b97f]" : status === "paused" ? "text-[#dce85d]" : "text-neutral-100")}>
                            {meta.label}
                          </div>
                          <div className="text-[0.6rem] uppercase tracking-[0.08em] text-neutral-400">
                            {bot.runtime?.updated_at ? dateFormatter.format(new Date(bot.runtime.updated_at)) : "Draft mode"}
                          </div>
                        </div>

                        <div className="grid gap-2">
                          <span className="text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Performance</span>
                          <div className={joinClasses("font-mono text-[1.1rem] font-bold uppercase tracking-tight", bot.performance ? performanceTone(bot.performance.pnl_total_pct) : "text-neutral-100")}>
                            {bot.performance ? formatSignedAmount(bot.performance.pnl_total_pct) : "—"}
                          </div>
                          <div className="text-[0.6rem] uppercase tracking-[0.08em] text-neutral-400">
                            {bot.performance ? `${bot.performance.positions.length} Live Pos | ${formatSignedUsd(bot.performance.pnl_total)} Net` : "Awaiting data"}
                          </div>
                        </div>

                        <div className="grid gap-2 col-span-2 md:col-span-1 border-t border-[rgba(255,255,255,0.06)] pt-4 md:border-t-0 md:pt-0">
                          <span className="text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Latest</span>
                          <div className="font-mono text-[1.1rem] font-bold uppercase tracking-tight text-neutral-50">
                            {bot.runtime?.deployed_at ? "Deployed" : bot.runtime?.stopped_at ? "Stopped" : "Edited"}
                          </div>
                          <div className="text-[0.6rem] uppercase tracking-[0.08em] text-neutral-400">
                            {dateFormatter.format(new Date(bot.runtime?.deployed_at || bot.runtime?.stopped_at || bot.updated_at))}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-3 xl:mt-0 xl:flex-col xl:items-end">
                      <button
                        type="button"
                        onClick={() => void runSingleAction(bot, primaryAction.action)}
                        disabled={busy}
                        className={joinClasses(
                          "inline-flex items-center gap-2 border px-4 py-2 text-[0.6rem] font-bold uppercase tracking-[0.16em] transition disabled:cursor-not-allowed disabled:opacity-50",
                          primaryAction.action === "stop"
                            ? "border-[rgba(255,255,255,0.15)] bg-transparent text-neutral-300 hover:border-[#74b97f] hover:text-[#74b97f]"
                            : "border-[#dce85d] bg-[#dce85d] text-[#090a0a] hover:border-[#e8f06d] hover:bg-[#e8f06d]",
                        )}
                      >
                        {primaryAction.action === "stop" ? <Power className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                        {primaryAction.label}
                      </button>
                      <Link
                        href={`/bots/${bot.id}`}
                        className="inline-flex items-center gap-2 border border-[rgba(255,255,255,0.15)] bg-transparent px-4 py-2 text-[0.6rem] font-bold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50"
                      >
                        Desk
                        <ArrowUpRight className="h-3 w-3" />
                      </Link>
                      <Link
                        href={`/build?botId=${encodeURIComponent(bot.id)}`}
                        className="inline-flex items-center gap-2 border border-[rgba(255,255,255,0.15)] bg-transparent px-4 py-2 text-[0.6rem] font-bold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
                      >
                        Edit
                        <ArrowUpRight className="h-3 w-3" />
                      </Link>
                    </div>
                  </article>
                );
              })
            )}

            {visibleBots.length > PAGE_SIZE ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-4 py-3">
                <span className="text-sm text-neutral-400">
                  Showing {pageStart}-{pageEnd} of {visibleBots.length} bots
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                    disabled={currentPage === 1}
                    className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Previous page
                  </button>
                  <span className="text-xs uppercase tracking-[0.16em] text-neutral-500">
                    {currentPage} / {totalPages}
                  </span>
                  <button
                    type="button"
                    onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                    disabled={currentPage === totalPages}
                    className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Next page
                  </button>
                </div>
              </div>
            ) : null}
          </section>
        </>
      )}
    </main>
  );
}
