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
  isFeatured: boolean;
  featuredCollectionTitle: string;
  featuredRank: number;
  inviteWalletsText: string;
  creatorDisplayName: string;
  creatorHeadline: string;
  creatorBio: string;
};

function buildInitialState(settings: PublishingSettings): PublishingFormState {
  return {
    visibility: settings.visibility,
    heroHeadline: settings.hero_headline,
    accessNote: settings.access_note,
    isFeatured: settings.is_featured,
    featuredCollectionTitle:
      settings.featured_collection_title ?? settings.creator_profile.featured_collection_title ?? "",
    featuredRank: settings.featured_rank,
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
  walletAddress,
  getAuthHeaders,
  onSaved,
  compact = false,
  initialSettings = null,
}: {
  botId: string;
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
  const [refreshing, setRefreshing] = useState(Boolean(seededSettings));

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      if (!settings) {
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
  }, [botId, walletAddress, getAuthHeaders]);

  const inviteCount = useMemo(() => parseInviteWallets(form?.inviteWalletsText ?? "").length, [form?.inviteWalletsText]);

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
        is_featured: form.isFeatured,
        featured_collection_title: form.featuredCollectionTitle.trim(),
        featured_rank: Number.isFinite(form.featuredRank) ? form.featuredRank : 0,
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
            Choose the access mode, shape the creator profile, and decide whether this bot belongs on a featured shelf.
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

      <div className={`grid gap-4 ${compact ? "" : "xl:grid-cols-[1.05fr_0.95fr]"}`}>
        <div className="grid gap-4">
          <label className="grid gap-2">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Access</span>
            <select
              value={form.visibility}
              onChange={(event) => setForm((current) => (current ? { ...current, visibility: event.target.value } : current))}
              className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
            >
              <option value="private">Private</option>
              <option value="public">Public</option>
              <option value="unlisted">Unlisted</option>
              <option value="invite_only">Invite-only</option>
            </select>
          </label>

          <label className="grid gap-2">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Shelf headline</span>
            <input
              value={form.heroHeadline}
              onChange={(event) => setForm((current) => (current ? { ...current, heroHeadline: event.target.value } : current))}
              placeholder="Fast trend rotation with tight drawdown control"
              className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
            />
          </label>

          <label className="grid gap-2">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Access note</span>
            <input
              value={form.accessNote}
              onChange={(event) => setForm((current) => (current ? { ...current, accessNote: event.target.value } : current))}
              placeholder="Best used on liquid majors with a funded Pacifica wallet."
              className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
            />
          </label>

          {form.visibility === "invite_only" ? (
            <label className="grid gap-2">
              <span className="flex items-center justify-between gap-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
                <span>Invite wallets</span>
                <span className="text-neutral-500">{inviteCount} added</span>
              </span>
              <textarea
                value={form.inviteWalletsText}
                onChange={(event) => setForm((current) => (current ? { ...current, inviteWalletsText: event.target.value } : current))}
                rows={Math.max(4, inviteCount || 3)}
                placeholder={"WalletA\nWalletB"}
                className="min-h-[8rem] rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
              />
            </label>
          ) : null}
        </div>

        <div className="grid gap-4">
          <label className="grid gap-2">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Creator name</span>
            <input
              value={form.creatorDisplayName}
              onChange={(event) => setForm((current) => (current ? { ...current, creatorDisplayName: event.target.value } : current))}
              className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#74b97f]"
            />
          </label>

          <label className="grid gap-2">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Creator headline</span>
            <input
              value={form.creatorHeadline}
              onChange={(event) => setForm((current) => (current ? { ...current, creatorHeadline: event.target.value } : current))}
              placeholder="Systematic intraday momentum across Pacifica majors"
              className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#74b97f]"
            />
          </label>

          <label className="grid gap-2">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Creator bio</span>
            <textarea
              value={form.creatorBio}
              onChange={(event) => setForm((current) => (current ? { ...current, creatorBio: event.target.value } : current))}
              rows={compact ? 4 : 5}
              className="min-h-[7rem] rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#74b97f]"
            />
          </label>
        </div>
      </div>

      <div className={`grid gap-4 ${compact ? "" : "md:grid-cols-[0.7fr_0.2fr_0.1fr]"}`}>
        <label className="grid gap-2">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Featured shelf</span>
          <input
            value={form.featuredCollectionTitle}
            onChange={(event) =>
              setForm((current) => (current ? { ...current, featuredCollectionTitle: event.target.value } : current))
            }
            placeholder="High conviction majors"
            disabled={!form.isFeatured && form.visibility !== "public"}
            className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d] disabled:opacity-60"
          />
        </label>

        <label className="grid gap-2">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Shelf rank</span>
          <input
            type="number"
            min={0}
            max={50}
            value={form.featuredRank}
            onChange={(event) =>
              setForm((current) =>
                current ? { ...current, featuredRank: Number.parseInt(event.target.value || "0", 10) || 0 } : current,
              )
            }
            disabled={!form.isFeatured}
            className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d] disabled:opacity-60"
          />
        </label>

        <label className="flex items-center justify-between rounded-[1.2rem] border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-300">
          <span>Feature</span>
          <input
            type="checkbox"
            checked={form.isFeatured}
            disabled={form.visibility !== "public"}
            onChange={(event) => setForm((current) => (current ? { ...current, isFeatured: event.target.checked } : current))}
            className="h-4 w-4 rounded border-[rgba(255,255,255,0.18)] bg-transparent"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[rgba(255,255,255,0.06)] pt-4">
        <p className="text-xs leading-6 text-neutral-500">
          Public bots appear in discovery. Unlisted stays off shelves. Invite-only requires a wallet allowlist.
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
