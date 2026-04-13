"use client";

import { useEffect, useMemo, useState } from "react";

import {
  fetchPublishingSettings,
  readCachedPublishingSettings,
  type PublishingSettings,
  updatePublishingSettings,
} from "@/lib/public-bots";

type PublishingFormState = {
  visibility: string;
  heroHeadline: string;
  accessNote: string;
  inviteWalletsText: string;
  creatorDisplayName: string;
  creatorHeadline: string;
  creatorBio: string;
};

const FIELD_LABEL_CLASS =
  "text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400";
const FIELD_WRAPPER_CLASS = "grid gap-2";
const FIELD_CLASS =
  "rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]";
const FIELD_CLASS_ALT_FOCUS =
  "rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]";

function buildInitialState(settings: PublishingSettings): PublishingFormState {
  return {
    visibility: settings.visibility,
    heroHeadline: settings.hero_headline,
    accessNote: settings.access_note,
    inviteWalletsText: settings.invite_wallet_addresses.join("\n"),
    creatorDisplayName: settings.creator_profile.display_name,
    creatorHeadline: settings.creator_profile.headline,
    creatorBio: settings.creator_profile.bio,
  };
}

function parseInviteWallets(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[\n,]/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

export function BotPublishingPanel({
  botId,
  runtimeId,
  walletAddress,
  getAuthHeaders,
  onSaved,
  compact = false,
  initialSettings = null,
}: {
  botId: string;
  runtimeId?: string | null;
  walletAddress: string;
  getAuthHeaders: (headersInit?: HeadersInit) => Promise<Headers>;
  onSaved?: (settings: PublishingSettings) => void;
  compact?: boolean;
  initialSettings?: PublishingSettings | null;
}) {
  const cachedSettings = readCachedPublishingSettings(botId, walletAddress);
  const seededSettings = cachedSettings ?? initialSettings;
  const [settings, setSettings] = useState<PublishingSettings | null>(seededSettings);
  const [form, setForm] = useState<PublishingFormState | null>(
    seededSettings ? buildInitialState(seededSettings) : null,
  );
  const [loading, setLoading] = useState(!seededSettings);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [inviteLinkStatus, setInviteLinkStatus] = useState<"idle" | "copied" | "failed">("idle");
  const [refreshing, setRefreshing] = useState(Boolean(seededSettings));
  const hasSeededSettings = Boolean(seededSettings);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      if (!hasSeededSettings) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }
      try {
        const headers = await getAuthHeaders();
        const nextSettings = await fetchPublishingSettings(botId, walletAddress, headers, controller.signal);
        if (controller.signal.aborted) {
          return;
        }
        setSettings(nextSettings);
        setForm(buildInitialState(nextSettings));
        setError(null);
      } catch (loadError) {
        if (!controller.signal.aborted) {
          setError(loadError instanceof Error ? loadError.message : "Could not load publishing settings");
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    }

    void load();
    return () => controller.abort();
  }, [botId, walletAddress, getAuthHeaders, hasSeededSettings]);

  const inviteCount = useMemo(() => parseInviteWallets(form?.inviteWalletsText ?? "").length, [form?.inviteWalletsText]);
  const inviteLink =
    runtimeId && typeof window !== "undefined"
      ? `${window.location.origin}/marketplace/${encodeURIComponent(runtimeId)}`
      : null;

  async function handleCopyInviteLink() {
    if (!inviteLink) {
      return;
    }
    try {
      await navigator.clipboard.writeText(inviteLink);
      setInviteLinkStatus("copied");
    } catch {
      setInviteLinkStatus("failed");
    }
  }

  async function handleSave() {
    if (!form) {
      return;
    }
    setSaving(true);
    setSuccess(null);
    setError(null);
    try {
      const headers = await getAuthHeaders();
      const nextSettings = await updatePublishingSettings(botId, headers, {
        wallet_address: walletAddress,
        visibility: form.visibility,
        hero_headline: form.heroHeadline.trim(),
        access_note: form.accessNote.trim(),
        invite_wallet_addresses: parseInviteWallets(form.inviteWalletsText),
        creator_display_name: form.creatorDisplayName.trim(),
        creator_headline: form.creatorHeadline.trim(),
        creator_bio: form.creatorBio.trim(),
      });
      setSettings(nextSettings);
      setForm(buildInitialState(nextSettings));
      setSuccess("Publishing settings updated.");
      onSaved?.(nextSettings);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save publishing settings");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <article className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-5 text-sm text-neutral-400">
        Loading publishing controls...
      </article>
    );
  }

  if (!form || !settings) {
    return (
      <article className="rounded-2xl border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-5 py-5 text-sm text-neutral-50">
        {error ?? "Publishing controls are unavailable right now."}
      </article>
    );
  }

  return (
    <article className="grid gap-4 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d]">
            Marketplace publishing
          </span>
          <h3 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
            Control how this strategy shows up
          </h3>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            Set who can access it, shape the creator profile, and decide how it appears in discovery.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {refreshing ? (
            <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
              Refreshing
            </span>
          ) : null}
          <div className="rounded-full border border-[rgba(255,255,255,0.1)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
            {settings.publish_state}
          </div>
        </div>
      </div>

      {error ? (
        <div className="rounded-2xl border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-4 py-3 text-sm text-neutral-50">
          {error}
        </div>
      ) : null}

      {success ? (
        <div className="rounded-2xl border border-[#74b97f]/30 bg-[#74b97f]/10 px-4 py-3 text-sm text-neutral-50">
          {success}
        </div>
      ) : null}

      <div className={`grid gap-4 ${compact ? "" : "xl:grid-cols-[1.05fr_0.95fr] xl:items-start"}`}>
        <div className="grid self-start gap-4">
          <label className={FIELD_WRAPPER_CLASS}>
            <span className={FIELD_LABEL_CLASS}>Access</span>
            <select
              value={form.visibility}
              onChange={(event) => setForm((current) => (current ? { ...current, visibility: event.target.value } : current))}
              className={FIELD_CLASS}
            >
              <option value="private">Private</option>
              <option value="public">Public</option>
              <option value="unlisted">Unlisted</option>
              <option value="invite_only">Invite-only</option>
            </select>
          </label>

          <label className={FIELD_WRAPPER_CLASS}>
            <span className={FIELD_LABEL_CLASS}>Shelf headline</span>
            <input
              value={form.heroHeadline}
              onChange={(event) => setForm((current) => (current ? { ...current, heroHeadline: event.target.value } : current))}
              placeholder="Fast trend rotation with tight drawdown control"
              className={FIELD_CLASS}
            />
          </label>

          <label className={FIELD_WRAPPER_CLASS}>
            <span className={FIELD_LABEL_CLASS}>Access note</span>
            <input
              value={form.accessNote}
              onChange={(event) => setForm((current) => (current ? { ...current, accessNote: event.target.value } : current))}
              placeholder="Best used on liquid majors with a funded Pacifica wallet."
              className={FIELD_CLASS}
            />
          </label>

          {form.visibility === "invite_only" ? (
            <div className="grid gap-4 rounded-[1.55rem] border border-[rgba(220,232,93,0.14)] bg-[linear-gradient(180deg,rgba(220,232,93,0.08),rgba(13,15,16,0.18))] p-4">
              <div className="grid gap-1">
                <span className="text-[0.58rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">
                  Invite lane
                </span>
                <h4 className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">
                  Share one link, gate it by wallet
                </h4>
                <p className="text-sm leading-6 text-neutral-400">
                  Allowlisted wallets can open this runtime page, then follow live or fork a clone from the same link.
                </p>
              </div>

              <label className={FIELD_WRAPPER_CLASS}>
                <span className={`flex items-center justify-between gap-3 ${FIELD_LABEL_CLASS}`}>
                  <span>Invite wallets</span>
                  <span className="text-neutral-500">{inviteCount} added</span>
                </span>
                <textarea
                  value={form.inviteWalletsText}
                  onChange={(event) => setForm((current) => (current ? { ...current, inviteWalletsText: event.target.value } : current))}
                  rows={Math.max(4, inviteCount || 3)}
                  placeholder={"WalletA\nWalletB"}
                  className={`min-h-[8rem] ${FIELD_CLASS}`}
                />
              </label>

              <div className="grid gap-3 rounded-[1.35rem] border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="grid gap-1">
                    <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
                      Shareable invite
                    </span>
                    <p className="text-sm leading-6 text-neutral-400">
                      The recipient still has to sign in with an invited wallet before the page unlocks.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleCopyInviteLink()}
                    disabled={!inviteLink}
                    className="rounded-full border border-[rgba(220,232,93,0.22)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d] transition hover:border-[#dce85d] hover:bg-[#dce85d]/8 disabled:cursor-not-allowed disabled:border-[rgba(255,255,255,0.08)] disabled:text-neutral-500"
                  >
                    {inviteLinkStatus === "copied" ? "Copied" : inviteLinkStatus === "failed" ? "Copy failed" : "Copy link"}
                  </button>
                </div>
                <div className="rounded-[1.1rem] border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-4 py-3 text-sm text-neutral-300">
                  {inviteLink ?? "Deploy this bot once to mint a runtime link for invites."}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="grid self-start gap-4">
          <label className={FIELD_WRAPPER_CLASS}>
            <span className={FIELD_LABEL_CLASS}>Creator name</span>
            <input
              value={form.creatorDisplayName}
              onChange={(event) => setForm((current) => (current ? { ...current, creatorDisplayName: event.target.value } : current))}
              className={FIELD_CLASS_ALT_FOCUS}
            />
          </label>

          <label className={FIELD_WRAPPER_CLASS}>
            <span className={FIELD_LABEL_CLASS}>Creator headline</span>
            <input
              value={form.creatorHeadline}
              onChange={(event) => setForm((current) => (current ? { ...current, creatorHeadline: event.target.value } : current))}
              placeholder="Systematic intraday momentum across Pacifica majors"
              className={FIELD_CLASS_ALT_FOCUS}
            />
          </label>

          <label className={FIELD_WRAPPER_CLASS}>
            <span className={FIELD_LABEL_CLASS}>Creator bio</span>
            <textarea
              value={form.creatorBio}
              onChange={(event) => setForm((current) => (current ? { ...current, creatorBio: event.target.value } : current))}
              rows={compact ? 4 : 5}
              className={`min-h-[7rem] ${FIELD_CLASS_ALT_FOCUS}`}
            />
          </label>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[rgba(255,255,255,0.06)] pt-4">
        <p className="text-xs leading-6 text-neutral-500">
          Public bots appear in the marketplace. Unlisted stays off discovery. Invite-only requires a wallet allowlist.
        </p>
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
          className="rounded-full border border-[rgba(220,232,93,0.24)] bg-[#dce85d] px-5 py-2.5 text-[0.66rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e6ef6c] disabled:opacity-60"
        >
          {saving ? "Saving..." : "Save publishing"}
        </button>
      </div>
    </article>
  );
}
