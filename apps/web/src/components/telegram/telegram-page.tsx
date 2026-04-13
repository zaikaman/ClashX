"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  RefreshCcw,
  Send,
  ShieldCheck,
  TestTube2,
  Unplug,
  Zap,
} from "lucide-react";

import { useClashxAuth } from "@/lib/clashx-auth";
import {
  createTelegramLink,
  disconnectTelegram,
  fetchTelegramStatus,
  sendTelegramTest,
  type TelegramConnectionStatus,
  type TelegramNotificationPrefs,
  updateTelegramPreferences,
} from "@/lib/telegram";

function formatDateTime(value: string | null) {
  if (!value) {
    return "Not yet";
  }
  return new Date(value).toLocaleString();
}

function formatTimeUntil(value: string | null) {
  if (!value) {
    return "No active secure link";
  }
  const deltaMs = new Date(value).getTime() - Date.now();
  if (deltaMs <= 0) {
    return "Expired";
  }
  const deltaMinutes = Math.round(deltaMs / 60000);
  if (deltaMinutes < 60) {
    return `${deltaMinutes}m left`;
  }
  const deltaHours = Math.round(deltaMinutes / 60);
  return `${deltaHours}h left`;
}

function preferenceChanged(
  left: TelegramNotificationPrefs | null,
  right: TelegramNotificationPrefs | null,
) {
  if (!left || !right) {
    return false;
  }
  return (
    left.critical_alerts !== right.critical_alerts ||
    left.execution_failures !== right.execution_failures ||
    left.copy_activity !== right.copy_activity ||
    left.trade_activity !== right.trade_activity
  );
}

/* ─── Toggle Switch ──────────────────────────────────────────── */
function Toggle({
  checked,
  onChange,
  id,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  id?: string;
}) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="relative inline-flex h-[22px] w-[40px] shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#dce85d]/40"
      style={{
        background: checked
          ? "linear-gradient(135deg, #dce85d 0%, #c5d048 100%)"
          : "rgba(255,255,255,0.08)",
      }}
    >
      <span
        className="pointer-events-none block h-[16px] w-[16px] rounded-full shadow-sm transition-transform duration-200"
        style={{
          transform: checked ? "translateX(20px)" : "translateX(3px)",
          background: checked ? "#090a0a" : "rgba(255,255,255,0.4)",
        }}
      />
    </button>
  );
}

export function TelegramPage() {
  const { ready, authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();
  const [status, setStatus] = useState<TelegramConnectionStatus | null>(null);
  const [prefs, setPrefs] = useState<TelegramNotificationPrefs | null>(null);
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!authenticated || !walletAddress) {
      setStatus(null);
      setPrefs(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void fetchTelegramStatus(walletAddress, getAuthHeaders, controller.signal)
      .then((payload) => {
        setStatus(payload);
        setPrefs(payload.notification_prefs);
        setNotificationsEnabled(payload.notifications_enabled);
      })
      .catch((loadError) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Could not load Telegram settings");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [authenticated, getAuthHeaders, walletAddress]);

  const secureLinkHref = status?.deeplink_url ?? status?.bot_link ?? null;
  const dirty =
    status !== null &&
    (notificationsEnabled !== status.notifications_enabled ||
      preferenceChanged(prefs, status.notification_prefs));

  const setupState = useMemo(() => {
    if (!status) {
      return [];
    }
    return [
      {
        label: "Backend token",
        ready: status.token_configured,
        detail: status.token_configured ? "Bot token loaded on the backend." : "Set TELEGRAM_BOT_TOKEN in the backend env.",
      },
      {
        label: "Webhook route",
        ready: status.webhook_url_configured,
        detail: status.webhook_url_configured
          ? "Webhook URL is configured."
          : "Set TELEGRAM_WEBHOOK_URL to your backend /api/telegram/webhook endpoint.",
      },
      {
        label: "Wallet link",
        ready: status.connected,
        detail: status.connected
          ? "This wallet is linked to a Telegram private chat."
          : "Generate a secure link, open the bot, and press Start in Telegram.",
      },
    ];
  }, [status]);

  async function refresh() {
    if (!walletAddress) {
      return;
    }
    setActionLoading("refresh");
    setError(null);
    setNotice(null);
    try {
      const payload = await fetchTelegramStatus(walletAddress, getAuthHeaders);
      setStatus(payload);
      setPrefs(payload.notification_prefs);
      setNotificationsEnabled(payload.notifications_enabled);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Could not refresh Telegram settings");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleGenerateLink() {
    if (!walletAddress) {
      return;
    }
    setActionLoading("link");
    setError(null);
    setNotice(null);
    try {
      const payload = await createTelegramLink(walletAddress, getAuthHeaders);
      setStatus(payload);
      setPrefs(payload.notification_prefs);
      setNotificationsEnabled(payload.notifications_enabled);
      const linkToCopy = payload.deeplink_url ?? payload.bot_link;
      try {
        await navigator.clipboard.writeText(linkToCopy);
        setNotice("Secure Telegram link refreshed and copied to your clipboard.");
      } catch {
        setNotice("Secure Telegram link refreshed. Copy it manually if the clipboard prompt was blocked.");
      }
    } catch (linkError) {
      setError(linkError instanceof Error ? linkError.message : "Could not generate a Telegram link");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleSavePreferences() {
    if (!walletAddress || !prefs) {
      return;
    }
    setActionLoading("save");
    setError(null);
    setNotice(null);
    try {
      const payload = await updateTelegramPreferences(walletAddress, getAuthHeaders, {
        notifications_enabled: notificationsEnabled,
        critical_alerts: prefs.critical_alerts,
        execution_failures: prefs.execution_failures,
        copy_activity: prefs.copy_activity,
        trade_activity: prefs.trade_activity,
      });
      setStatus(payload);
      setPrefs(payload.notification_prefs);
      setNotificationsEnabled(payload.notifications_enabled);
      setNotice("Telegram notification preferences saved.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save Telegram preferences");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleTest() {
    if (!walletAddress) {
      return;
    }
    setActionLoading("test");
    setError(null);
    setNotice(null);
    try {
      const payload = await sendTelegramTest(walletAddress, getAuthHeaders);
      setStatus(payload);
      setPrefs(payload.notification_prefs);
      setNotificationsEnabled(payload.notifications_enabled);
      setNotice("Test message sent to the connected Telegram chat.");
    } catch (testError) {
      setError(testError instanceof Error ? testError.message : "Could not send a Telegram test message");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleDisconnect() {
    if (!walletAddress) {
      return;
    }
    setActionLoading("disconnect");
    setError(null);
    setNotice(null);
    try {
      const payload = await disconnectTelegram(walletAddress, getAuthHeaders);
      setStatus(payload);
      setPrefs(payload.notification_prefs);
      setNotificationsEnabled(payload.notifications_enabled);
      setNotice("Telegram was disconnected for this wallet.");
    } catch (disconnectError) {
      setError(
        disconnectError instanceof Error
          ? disconnectError.message
          : "Could not disconnect Telegram",
      );
    } finally {
      setActionLoading(null);
    }
  }

  /* ─── Notification items ────────────────────────────────────── */
  const notifItems = [
    {
      key: "critical_alerts",
      label: "Critical alerts",
      detail: "Runtime stops, authorization, kill switches",
      icon: ShieldCheck,
      accent: "#f3b86b",
    },
    {
      key: "execution_failures",
      label: "Execution failures",
      detail: "Failed actions with error context",
      icon: Zap,
      accent: "#9fd3ff",
    },
    {
      key: "copy_activity",
      label: "Copy trading",
      detail: "Relationship and scale updates",
      icon: BellRing,
      accent: "#dce85d",
    },
    {
      key: "trade_activity",
      label: "Trade activity",
      detail: "Entries, TP/SL, manual closes, hits",
      icon: Send,
      accent: "#74b97f",
    },
  ];

  /* ─── Message preview data ──────────────────────────────────── */
  const messagePreviews = [
    {
      title: "Critical runtime alert",
      body: "Alpha Trend stopped. Reason: allocated drawdown budget breached.",
      accent: "#f3b86b",
    },
    {
      title: "Execution failure",
      body: "Mean Revert failed place market order on BTC. Reason: Pacifica rejected the order.",
      accent: "#9fd3ff",
    },
    {
      title: "Copy trading update",
      body: "Relationship status: paused. Scale: 2000 bps.",
      accent: "#74b97f",
    },
  ];

  return (
    <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">

      {/* ── Hero banner ───────────────────────────────────────── */}
      <section className="flex flex-wrap items-end justify-between gap-4 border-b border-[rgba(255,255,255,0.08)] pb-6 md:pb-8">
        <div className="grid gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-mono text-[clamp(2rem,4vw,2.8rem)] font-bold uppercase tracking-tight text-neutral-50">
              Telegram
            </h1>
            {/* Inline connection badge */}
            <span
              className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.14em]"
              style={{
                background: status?.connected
                  ? "rgba(116,185,127,0.1)"
                  : "rgba(255,255,255,0.04)",
                border: `1px solid ${status?.connected ? "rgba(116,185,127,0.25)" : "rgba(255,255,255,0.08)"}`,
                color: status?.connected ? "#9fcca7" : "#71717a",
              }}
            >
              <span
                className="h-[5px] w-[5px] rounded-full"
                style={{
                  background: status?.connected ? "#74b97f" : "#52525b",
                  boxShadow: status?.connected ? "0 0 6px #74b97f" : "none",
                }}
              />
              {status?.connected
                ? status.telegram_username
                  ? `@${status.telegram_username}`
                  : "Connected"
                : "Not linked"}
            </span>
          </div>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400">
            Link one wallet, send runtime alerts there, and keep Telegram ready for fast checks.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleGenerateLink}
              disabled={!authenticated || !walletAddress || actionLoading !== null}
              className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {actionLoading === "link" ? "Refreshing…" : "Generate secure link"}
            </button>
            <Link
              href={secureLinkHref ?? "#"}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full border border-[rgba(84,180,255,0.28)] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#9fd3ff] transition hover:border-[#54b4ff] hover:bg-[rgba(48,125,184,0.14)]"
            >
              Open bot
              <ExternalLink className="h-3.5 w-3.5" />
            </Link>
            <button
              type="button"
              onClick={refresh}
              disabled={actionLoading !== null || !authenticated}
              className="rounded-full border border-[rgba(255,255,255,0.1)] p-2.5 text-neutral-400 transition hover:border-white/20 hover:text-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
              aria-label="Refresh Telegram status"
            >
              <RefreshCcw className={`h-3.5 w-3.5 ${actionLoading === "refresh" ? "animate-spin" : ""}`} />
            </button>
        </div>
      </section>

      {/* ── Notices ───────────────────────────────────────────── */}
      {error ? (
        <div className="mx-0 mb-6 rounded-[1.2rem] border border-[#f3b86b]/25 bg-[#f3b86b]/8 px-5 py-3.5 text-sm text-neutral-100">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="mx-0 mb-6 rounded-[1.2rem] border border-[#74b97f]/20 bg-[#74b97f]/8 px-5 py-3.5 text-sm text-neutral-100">
          {notice}
        </div>
      ) : null}

      {/* ── Auth gate ─────────────────────────────────────────── */}
      {ready && !authenticated ? (
        <section className="mb-8 flex flex-col items-start gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">
              Sign in required
            </span>
            <p className="max-w-xl text-sm leading-7 text-neutral-400">
              Connect the trading wallet you want Telegram to represent before generating a secure link or editing delivery rules.
            </p>
          </div>
          <button
            type="button"
            onClick={login}
            className="shrink-0 rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
          >
            Sign in to link Telegram
          </button>
        </section>
      ) : null}

      {/* ── Loading skeleton ──────────────────────────────────── */}
      {loading ? (
        <div className="grid gap-6">
          <div className="skeleton h-[14rem] rounded-[2rem]" />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="skeleton h-[10rem] rounded-[1.6rem]" />
            <div className="skeleton h-[10rem] rounded-[1.6rem]" />
          </div>
        </div>
      ) : null}

      {/* ── Webhook warning ───────────────────────────────────── */}
      {status && !status.webhook_ready ? (
        <section className="mb-8 rounded-[1.6rem] border border-[rgba(84,180,255,0.18)] bg-[rgba(48,125,184,0.08)] px-6 py-5">
          <div className="mb-2 inline-flex items-center gap-2 text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#9fd3ff]">
            <AlertTriangle className="h-3.5 w-3.5" />
            Backend setup still needed
          </div>
          <p className="max-w-3xl text-sm leading-7 text-neutral-300">
            Incoming Telegram messages only reach ClashX after the backend has both <code className="rounded bg-white/5 px-1.5 py-0.5 text-[0.75rem]">TELEGRAM_BOT_TOKEN</code> and <code className="rounded bg-white/5 px-1.5 py-0.5 text-[0.75rem]">TELEGRAM_WEBHOOK_URL</code>. Point the webhook URL at <code className="rounded bg-white/5 px-1.5 py-0.5 text-[0.75rem]">/api/telegram/webhook</code> on the FastAPI server, then restart.
          </p>
        </section>
      ) : null}

      {status ? (
        <>
          {/* ═══════════════════════════════════════════════════════ */}
          {/* SETUP TIMELINE + CONNECTION CARD                       */}
          {/* ═══════════════════════════════════════════════════════ */}
          <section className="mb-10 grid gap-6 lg:grid-cols-[1fr_340px]">

            {/* ── Vertical timeline ──────────────────────────────── */}
            <article className="rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-6 md:p-8">
              <div className="mb-6 flex items-end justify-between gap-4">
                <div>
                  <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#9fd3ff]">
                    Setup path
                  </span>
                  <h2 className="mt-1 font-mono text-xl font-bold uppercase tracking-tight text-neutral-50 md:text-2xl">
                    Integration checklist
                  </h2>
                </div>
                <span className="whitespace-nowrap text-[0.6rem] uppercase tracking-[0.14em] text-neutral-500">
                  Link: {formatTimeUntil(status.link_expires_at)}
                </span>
              </div>

              {/* Timeline steps */}
              <div className="relative pl-8">
                {/* Vertical connector line */}
                <div
                  className="absolute bottom-4 left-[11px] top-4 w-px"
                  style={{ background: "linear-gradient(180deg, rgba(84,180,255,0.3) 0%, rgba(255,255,255,0.06) 100%)" }}
                />

                <div className="grid gap-0">
                  {setupState.map((step, i) => (
                    <div key={step.label} className="relative flex gap-4 pb-6 last:pb-0">
                      {/* Dot */}
                      <div
                        className="absolute -left-8 top-[3px] flex h-[22px] w-[22px] items-center justify-center rounded-full"
                        style={{
                          background: step.ready
                            ? "rgba(116,185,127,0.15)"
                            : "rgba(243,184,107,0.1)",
                          border: `1.5px solid ${step.ready ? "rgba(116,185,127,0.4)" : "rgba(243,184,107,0.3)"}`,
                        }}
                      >
                        {step.ready ? (
                          <CheckCircle2 className="h-3 w-3 text-[#74b97f]" />
                        ) : (
                          <span className="font-mono text-[0.5rem] font-bold text-[#f3b86b]">{i + 1}</span>
                        )}
                      </div>
                      {/* Content */}
                      <div className="grid gap-1 pt-px">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-neutral-50">{step.label}</span>
                          <span
                            className="rounded-full px-2 py-0.5 text-[0.5rem] font-semibold uppercase tracking-[0.12em]"
                            style={{
                              background: step.ready ? "rgba(116,185,127,0.1)" : "rgba(243,184,107,0.08)",
                              color: step.ready ? "#9fcca7" : "#f3b86b",
                            }}
                          >
                            {step.ready ? "Ready" : "Pending"}
                          </span>
                        </div>
                        <p className="text-[0.78rem] leading-6 text-neutral-500">{step.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Action row */}
              <div className="mt-6 flex flex-wrap gap-3 border-t border-[rgba(255,255,255,0.05)] pt-6">
                <button
                  type="button"
                  onClick={handleGenerateLink}
                  disabled={actionLoading !== null}
                  className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {actionLoading === "link" ? "Refreshing…" : "Refresh secure link"}
                </button>
                <Link
                  href={secureLinkHref ?? status.bot_link}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-full border border-[rgba(84,180,255,0.28)] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#9fd3ff] transition hover:border-[#54b4ff] hover:bg-[rgba(48,125,184,0.14)]"
                >
                  Open Telegram bot
                  <Send className="h-3.5 w-3.5" />
                </Link>
              </div>
            </article>

            {/* ── Connection card (sidebar) ──────────────────────── */}
            <aside className="flex flex-col gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-6">
              <div>
                <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#9fd3ff]">
                  Linked chat
                </span>
                <h2 className="mt-1 font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">
                  {status.connected ? "Connected" : "Awaiting link"}
                </h2>
              </div>

              {/* Status display */}
              <div
                className="flex-1 rounded-[1.4rem] p-5"
                style={{
                  background: status.connected
                    ? "linear-gradient(135deg, rgba(84,180,255,0.06) 0%, rgba(116,185,127,0.04) 100%)"
                    : "rgba(255,255,255,0.02)",
                  border: `1px solid ${status.connected ? "rgba(84,180,255,0.12)" : "rgba(255,255,255,0.05)"}`,
                }}
              >
                <div className="mb-3 flex items-center justify-between gap-2">
                  <span
                    className="rounded-full px-2.5 py-1 text-[0.52rem] font-bold uppercase tracking-[0.16em]"
                    style={{
                      background: status.connected ? "rgba(116,185,127,0.12)" : "rgba(255,255,255,0.04)",
                      color: status.connected ? "#9fcca7" : "#71717a",
                    }}
                  >
                    {status.connected ? "Live" : "Not linked"}
                  </span>
                  <span className="text-[0.5rem] uppercase tracking-[0.12em] text-neutral-600">
                    {status.connected ? formatDateTime(status.connected_at) : "—"}
                  </span>
                </div>
                <div className="font-mono text-lg font-bold tracking-tight text-neutral-50">
                  {status.telegram_username
                    ? `@${status.telegram_username}`
                    : status.telegram_first_name || "No chat linked yet"}
                </div>
                <p className="mt-2 text-[0.78rem] leading-6 text-neutral-500">
                  {status.connected
                    ? `${status.chat_label ?? "Private chat"} linked to this wallet.`
                    : "Generate a secure link, open the bot, and press Start from Telegram to bind this wallet."}
                </p>
              </div>

              {/* Quick actions */}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleTest}
                  disabled={!status.connected || actionLoading !== null}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-full border border-[rgba(255,255,255,0.08)] py-2.5 text-[0.58rem] font-semibold uppercase tracking-[0.12em] text-neutral-400 transition hover:border-white/15 hover:text-neutral-200 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <TestTube2 className="h-3 w-3" />
                  {actionLoading === "test" ? "Sending…" : "Test"}
                </button>
                <button
                  type="button"
                  onClick={handleDisconnect}
                  disabled={!status.connected || actionLoading !== null}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-full border border-[rgba(243,184,107,0.15)] py-2.5 text-[0.58rem] font-semibold uppercase tracking-[0.12em] text-[#f3b86b]/70 transition hover:border-[#f3b86b]/30 hover:text-[#f3b86b] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Unplug className="h-3 w-3" />
                  {actionLoading === "disconnect" ? "…" : "Disconnect"}
                </button>
              </div>
            </aside>
          </section>

          {/* ═══════════════════════════════════════════════════════ */}
          {/* NOTIFICATION PREFERENCES                               */}
          {/* ═══════════════════════════════════════════════════════ */}
          <section className="mb-10">
            <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
              <div>
                <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">
                  Delivery rules
                </span>
                <h2 className="mt-1 font-mono text-xl font-bold uppercase tracking-tight text-neutral-50 md:text-2xl">
                  What deserves an interruption
                </h2>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[0.62rem] font-semibold uppercase tracking-[0.14em] text-neutral-500">
                  Master switch
                </span>
                <Toggle
                  id="toggle-master"
                  checked={notificationsEnabled}
                  onChange={setNotificationsEnabled}
                />
              </div>
            </div>

            {/* 2×2 tiles */}
            {prefs ? (
              <div className="grid gap-4 sm:grid-cols-2">
                {notifItems.map((item) => {
                  const Icon = item.icon;
                  const checked = prefs[item.key as keyof TelegramNotificationPrefs];
                  return (
                    <div
                      key={item.key}
                      className="group flex items-start justify-between gap-4 rounded-[1.6rem] border bg-[#141618] px-5 py-5 transition-colors"
                      style={{
                        borderColor: checked
                          ? `${item.accent}18`
                          : "rgba(255,255,255,0.05)",
                      }}
                    >
                      <div className="flex items-start gap-3.5">
                        <div
                          className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
                          style={{
                            background: `${item.accent}10`,
                            border: `1px solid ${item.accent}20`,
                          }}
                        >
                          <Icon className="h-4 w-4" style={{ color: item.accent }} />
                        </div>
                        <div className="grid gap-0.5">
                          <span className="text-sm font-medium text-neutral-50">{item.label}</span>
                          <span className="text-[0.72rem] leading-5 text-neutral-500">{item.detail}</span>
                        </div>
                      </div>
                      <Toggle
                        id={`toggle-${item.key}`}
                        checked={checked}
                        onChange={(v) =>
                          setPrefs((c) =>
                            c ? { ...c, [item.key]: v } : c,
                          )
                        }
                      />
                    </div>
                  );
                })}
              </div>
            ) : null}

            {/* Save */}
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={handleSavePreferences}
                disabled={!dirty || actionLoading !== null}
                className="rounded-full bg-[#dce85d] px-6 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {actionLoading === "save" ? "Saving…" : "Save preferences"}
              </button>
            </div>
          </section>

          {/* ═══════════════════════════════════════════════════════ */}
          {/* BOT COMMANDS + MESSAGE PREVIEWS (side by side)         */}
          {/* ═══════════════════════════════════════════════════════ */}
          <section className="grid gap-6 lg:grid-cols-[1fr_1fr]">

            {/* ── Commands strip ─────────────────────────────────── */}
            <article className="rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-6">
              <div className="mb-5">
                <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">
                  Bot menu
                </span>
                <h2 className="mt-1 font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">
                  Commands
                </h2>
              </div>

              <div className="flex flex-wrap gap-2">
                {status.commands.map((command) => (
                  <div
                    key={command.command}
                    className="group relative overflow-hidden rounded-[1rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3 transition hover:border-[rgba(84,180,255,0.15)]"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-neutral-50">
                        /{command.command}
                      </span>
                      <ChevronRight className="h-3 w-3 text-neutral-600 transition group-hover:text-neutral-400" />
                    </div>
                    <p className="mt-1 text-[0.72rem] leading-5 text-neutral-500">{command.description}</p>
                  </div>
                ))}
              </div>
            </article>

            {/* ── Message previews (chat‑bubble) ─────────────────── */}
            <article className="rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-6">
              <div className="mb-5">
                <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#9fd3ff]">
                  Message shape
                </span>
                <h2 className="mt-1 font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">
                  What lands in chat
                </h2>
              </div>

              <div className="grid gap-3">
                {messagePreviews.map((msg) => (
                  <div
                    key={msg.title}
                    className="flex gap-3 rounded-[1.2rem] bg-[#0d0f10] px-4 py-4"
                    style={{
                      borderLeft: `3px solid ${msg.accent}`,
                    }}
                  >
                    <div className="grid gap-1.5">
                      <span
                        className="text-[0.58rem] font-bold uppercase tracking-[0.14em]"
                        style={{ color: msg.accent }}
                      >
                        {msg.title}
                      </span>
                      <p className="text-[0.78rem] leading-6 text-neutral-300">{msg.body}</p>
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </section>
        </>
      ) : null}
    </main>
  );
}
