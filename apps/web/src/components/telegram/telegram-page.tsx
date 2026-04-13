"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
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
    left.copy_activity !== right.copy_activity
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

  return (
    <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">
      <section className="flex flex-wrap items-end justify-between gap-4 border-b border-[rgba(255,255,255,0.08)] pb-6 md:pb-8">
        <div className="grid gap-2">
          <h1 className="font-mono text-[clamp(2rem,4vw,2.8rem)] font-bold uppercase tracking-tight text-neutral-50">
            Telegram
          </h1>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400">
            Link one wallet, send runtime alerts there, and keep Telegram ready for fast checks.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={handleGenerateLink}
            disabled={!authenticated || !walletAddress || actionLoading !== null}
            className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {actionLoading === "link" ? "Refreshing link..." : "Generate secure link"}
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
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
        <article className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#9fd3ff]">
                Setup path
              </span>
              <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                Link the wallet once, then let the bot do the chasing
              </h2>
            </div>
            <span className="text-xs uppercase tracking-[0.16em] text-neutral-500">
              Secure link: {formatTimeUntil(status?.link_expires_at ?? null)}
            </span>
          </div>

          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            Keep the chat link healthy, make sure the webhook is live, and decide which notifications are worth an interruption.
          </p>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={handleGenerateLink}
              disabled={!authenticated || !walletAddress || actionLoading !== null}
              className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {actionLoading === "link" ? "Refreshing link..." : "Refresh secure link"}
            </button>
            <Link
              href={secureLinkHref ?? status?.bot_link ?? "#"}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full border border-[rgba(84,180,255,0.28)] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#9fd3ff] transition hover:border-[#54b4ff] hover:bg-[rgba(48,125,184,0.14)]"
            >
              Open Telegram bot
              <Send className="h-3.5 w-3.5" />
            </Link>
          </div>
        </article>

        <aside className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.08)] bg-[#141618] p-5 md:p-6">
          <div className="flex items-center justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#9fd3ff]">
                Delivery line
              </span>
              <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                {status?.connected ? "Connected" : "Awaiting link"}
              </h2>
            </div>
            <button
              type="button"
              onClick={refresh}
              disabled={actionLoading !== null || !authenticated}
              className="rounded-full border border-[rgba(255,255,255,0.12)] p-2 text-neutral-300 transition hover:border-white hover:text-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
              aria-label="Refresh Telegram status"
            >
              <RefreshCcw className={`h-4 w-4 ${actionLoading === "refresh" ? "animate-spin" : ""}`} />
            </button>
          </div>

          <div className="grid grid-cols-3 gap-3">
            {[0, 1, 2].map((index) => (
              <div
                key={index}
                className={`h-24 rounded-[1.2rem] border ${
                  status?.connected
                    ? "border-[rgba(84,180,255,0.24)] bg-[linear-gradient(180deg,rgba(84,180,255,0.28),rgba(84,180,255,0.06))]"
                    : "border-[rgba(255,255,255,0.08)] bg-[linear-gradient(180deg,rgba(255,255,255,0.1),rgba(255,255,255,0.02))]"
                }`}
              />
            ))}
          </div>

          <div className="grid gap-3 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#14171a] p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">
                Linked chat
              </span>
              <span
                className={`rounded-full px-2.5 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${
                  status?.connected
                    ? "bg-[rgba(116,185,127,0.12)] text-[#9fcca7]"
                    : "bg-[rgba(255,255,255,0.06)] text-neutral-400"
                }`}
              >
                {status?.connected ? "Live" : "Not linked"}
              </span>
            </div>
            <div className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
              {status?.telegram_username
                ? `@${status.telegram_username}`
                : status?.telegram_first_name || "No chat linked yet"}
            </div>
            <p className="text-sm leading-6 text-neutral-400">
              {status?.connected
                ? `${status.chat_label ?? "Private chat"} linked on ${formatDateTime(status.connected_at)}`
                : "Generate a secure link, open the bot, and press Start from Telegram to bind this wallet."}
            </p>
          </div>
        </aside>
      </section>

      {ready && !authenticated ? (
        <article className="flex flex-wrap items-center justify-between gap-4 rounded-[1.8rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-5">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">
              Sign in required
            </span>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400">
              Connect the trading wallet you want Telegram to represent before you generate a secure link or edit delivery rules.
            </p>
          </div>
          <button
            type="button"
            onClick={login}
            className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
          >
            Sign in to link Telegram
          </button>
        </article>
      ) : null}

      {loading ? (
        <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="skeleton h-[22rem] rounded-[2rem]" />
          <div className="skeleton h-[22rem] rounded-[2rem]" />
        </section>
      ) : null}

      {error ? (
        <article className="rounded-[1.6rem] border border-[#f3b86b]/30 bg-[#f3b86b]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      {notice ? (
        <article className="rounded-[1.6rem] border border-[#74b97f]/25 bg-[#74b97f]/10 px-5 py-4 text-sm text-neutral-50">
          {notice}
        </article>
      ) : null}

      {status ? (
        <>
          {!status.webhook_ready ? (
            <article className="grid gap-2 rounded-[1.8rem] border border-[rgba(84,180,255,0.2)] bg-[rgba(48,125,184,0.12)] px-5 py-5">
              <div className="inline-flex items-center gap-2 text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#9fd3ff]">
                <AlertTriangle className="h-3.5 w-3.5" />
                Backend setup still needed
              </div>
              <p className="max-w-3xl text-sm leading-7 text-neutral-200">
                Incoming Telegram messages only reach ClashX after the backend has both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_URL`. Point the webhook URL at `/api/telegram/webhook` on the FastAPI server, then restart the backend so it can sync the webhook automatically.
              </p>
            </article>
          ) : null}

          <section className="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
            <article className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div className="grid gap-1">
                <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#9fd3ff]">
                  Delivery checks
                </span>
                <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                  Keep the route healthy
                </h2>
                </div>
                <span className="text-xs uppercase tracking-[0.16em] text-neutral-500">
                  Secure link: {formatTimeUntil(status.link_expires_at)}
                </span>
              </div>

              <div className="grid gap-3">
                {setupState.map((step) => (
                  <article
                    key={step.label}
                    className="grid gap-2 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="inline-flex items-center gap-2 text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">
                        {step.ready ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-[#74b97f]" />
                        ) : (
                          <AlertTriangle className="h-3.5 w-3.5 text-[#f3b86b]" />
                        )}
                        {step.label}
                      </div>
                      <span
                        className={`rounded-full px-2.5 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${
                          step.ready
                            ? "bg-[rgba(116,185,127,0.12)] text-[#9fcca7]"
                            : "bg-[rgba(243,184,107,0.12)] text-[#f3b86b]"
                        }`}
                      >
                        {step.ready ? "Ready" : "Pending"}
                      </span>
                    </div>
                    <p className="text-sm leading-6 text-neutral-400">{step.detail}</p>
                  </article>
                ))}
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={handleGenerateLink}
                  disabled={actionLoading !== null}
                  className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {actionLoading === "link" ? "Refreshing link..." : "Refresh secure link"}
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

            <article className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
              <div className="grid gap-1">
                <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">
                  Live controls
                </span>
                <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                  Decide what deserves a Telegram interruption
                </h2>
              </div>

              <div className="grid gap-4 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
                <label className="flex items-center justify-between gap-4">
                  <div className="grid gap-1">
                    <span className="text-sm font-medium text-neutral-50">Master delivery switch</span>
                    <span className="text-xs leading-5 text-neutral-500">
                      Pause every Telegram push without unlinking the chat.
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={notificationsEnabled}
                    onChange={(event) => setNotificationsEnabled(event.target.checked)}
                    className="h-5 w-5 rounded border-neutral-600 bg-transparent text-[#54b4ff] focus:ring-[#54b4ff]"
                  />
                </label>

                {prefs ? (
                  <div className="grid gap-3">
                    {[
                      {
                        key: "critical_alerts",
                        label: "Critical alerts",
                        detail: "Runtime stops, missing Pacifica authorization, and portfolio kill switches.",
                        icon: ShieldCheck,
                      },
                      {
                        key: "execution_failures",
                        label: "Execution failures",
                        detail: "Failed runtime actions with the symbol and error reason attached.",
                        icon: Zap,
                      },
                      {
                        key: "copy_activity",
                        label: "Copy trading updates",
                        detail: "Relationship status changes and scale updates from the copy desk.",
                        icon: BellRing,
                      },
                    ].map((item) => {
                      const Icon = item.icon;
                      return (
                        <label
                          key={item.key}
                          className="flex items-center justify-between gap-4 rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#14171a] px-4 py-4"
                        >
                          <div className="flex items-start gap-3">
                            <div className="mt-0.5 rounded-full border border-[rgba(84,180,255,0.22)] bg-[rgba(48,125,184,0.12)] p-2 text-[#9fd3ff]">
                              <Icon className="h-4 w-4" />
                            </div>
                            <div className="grid gap-1">
                              <span className="text-sm font-medium text-neutral-50">{item.label}</span>
                              <span className="text-xs leading-5 text-neutral-500">{item.detail}</span>
                            </div>
                          </div>
                          <input
                            type="checkbox"
                            checked={prefs[item.key as keyof TelegramNotificationPrefs]}
                            onChange={(event) =>
                              setPrefs((current) =>
                                current
                                  ? {
                                      ...current,
                                      [item.key]: event.target.checked,
                                    }
                                  : current,
                              )
                            }
                            className="h-5 w-5 rounded border-neutral-600 bg-transparent text-[#54b4ff] focus:ring-[#54b4ff]"
                          />
                        </label>
                      );
                    })}
                  </div>
                ) : null}

                <div className="flex flex-wrap gap-3 pt-1">
                  <button
                    type="button"
                    onClick={handleSavePreferences}
                    disabled={!dirty || actionLoading !== null}
                    className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {actionLoading === "save" ? "Saving..." : "Save preferences"}
                  </button>
                  <button
                    type="button"
                    onClick={handleTest}
                    disabled={!status.connected || actionLoading !== null}
                    className="inline-flex items-center gap-2 rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <TestTube2 className="h-3.5 w-3.5" />
                    {actionLoading === "test" ? "Sending..." : "Send test ping"}
                  </button>
                  <button
                    type="button"
                    onClick={handleDisconnect}
                    disabled={!status.connected || actionLoading !== null}
                    className="inline-flex items-center gap-2 rounded-full border border-[rgba(243,184,107,0.25)] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#f3b86b] transition hover:border-[#f3b86b] hover:bg-[#f3b86b]/8 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Unplug className="h-3.5 w-3.5" />
                    {actionLoading === "disconnect" ? "Disconnecting..." : "Disconnect chat"}
                  </button>
                </div>
              </div>
            </article>
          </section>

          <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
            <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
              <div className="grid gap-1">
                <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">
                  Bot menu
                </span>
                <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                  Telegram commands worth memorizing
                </h2>
              </div>
              <div className="grid gap-3">
                {status.commands.map((command) => (
                  <article
                    key={command.command}
                    className="grid gap-1 rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4"
                  >
                    <div className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
                      /{command.command}
                    </div>
                    <p className="text-sm leading-6 text-neutral-400">{command.description}</p>
                  </article>
                ))}
              </div>
            </article>

            <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] p-5 md:p-6">
              <div className="grid gap-1">
                <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#9fd3ff]">
                  Message shape
                </span>
                <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                  What lands in chat
                </h2>
              </div>

              <div className="grid gap-3">
                {[
                  {
                    title: "Critical runtime alert",
                    body: "Alpha Trend stopped. Reason: allocated drawdown budget breached.",
                    tone: "border-[rgba(243,184,107,0.22)] bg-[rgba(243,184,107,0.08)] text-[#f3b86b]",
                  },
                  {
                    title: "Execution failure",
                    body: "Mean Revert failed place market order on BTC. Reason: Pacifica rejected the order.",
                    tone: "border-[rgba(84,180,255,0.24)] bg-[rgba(48,125,184,0.1)] text-[#9fd3ff]",
                  },
                  {
                    title: "Copy trading update",
                    body: "Relationship status: paused. Scale: 2000 bps.",
                    tone: "border-[rgba(116,185,127,0.24)] bg-[rgba(116,185,127,0.08)] text-[#9fcca7]",
                  },
                ].map((preview) => (
                  <article
                    key={preview.title}
                    className={`grid gap-2 rounded-[1.5rem] border px-4 py-4 ${preview.tone}`}
                  >
                    <div className="text-[0.62rem] font-semibold uppercase tracking-[0.18em]">
                      {preview.title}
                    </div>
                    <p className="text-sm leading-6 text-neutral-100">{preview.body}</p>
                  </article>
                ))}
              </div>
            </article>
          </section>
        </>
      ) : null}
    </main>
  );
}
