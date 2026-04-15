"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { ExecutionLog } from "@/components/bots/execution-log";
import { BotCloneModal } from "@/components/copy/bot-clone-modal";
import { BotMirrorModal } from "@/components/copy/bot-mirror-modal";
import { CreatorReputationCard } from "@/components/leaderboard/creator-reputation-card";
import { DriftVisual } from "@/components/leaderboard/drift-visual";
import { StrategyPassportPanel } from "@/components/leaderboard/strategy-passport-panel";
import { TrustBadgeStrip } from "@/components/leaderboard/trust-badge-strip";
import { useClashxAuth } from "@/lib/clashx-auth";
import { fetchAccessibleRuntimeProfile, fetchRuntimeProfile, type RuntimeProfile } from "@/lib/public-bots";

function formatSigned(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatVisibilityLabel(visibility?: string) {
  if (visibility === "invite_only") {
    return "Invite-only";
  }
  if (visibility === "unlisted") {
    return "Unlisted";
  }
  if (visibility === "private") {
    return "Private";
  }
  return "Public";
}

function shortAddress(value?: string | null) {
  if (!value) {
    return "Unknown wallet";
  }
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
}

export default function MarketplaceRuntimePage({ params: paramsPromise }: { params: Promise<{ runtimeId: string }> }) {
  const params = use(paramsPromise);
  const { authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();
  const [profile, setProfile] = useState<RuntimeProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [openMirror, setOpenMirror] = useState(false);
  const [openClone, setOpenClone] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    async function loadProfile() {
      try {
        const publicProfile = await fetchRuntimeProfile(params.runtimeId, controller.signal);
        if (controller.signal.aborted) {
          return;
        }
        setProfile(publicProfile);
        setError(null);
      } catch (publicLoadError) {
        if (controller.signal.aborted) {
          return;
        }
        if (!authenticated || !walletAddress) {
          setProfile(null);
          setError(publicLoadError instanceof Error ? publicLoadError.message : "Could not load runtime profile");
          return;
        }
        try {
          const headers = await getAuthHeaders();
          const gatedProfile = await fetchAccessibleRuntimeProfile(
            params.runtimeId,
            walletAddress,
            headers,
            controller.signal,
          );
          if (controller.signal.aborted) {
            return;
          }
          setProfile(gatedProfile);
          setError(null);
        } catch (gatedLoadError) {
          if (controller.signal.aborted) {
            return;
          }
          setProfile(null);
          setError(gatedLoadError instanceof Error ? gatedLoadError.message : "Could not load runtime profile");
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void loadProfile();
    return () => controller.abort();
  }, [authenticated, getAuthHeaders, params.runtimeId, walletAddress]);

  if (!profile && !loading) {
    return (
      <main className="shell grid gap-8 pb-10 md:pb-12">
        <AccessGate
          runtimeId={params.runtimeId}
          authenticated={authenticated}
          walletAddress={walletAddress}
          error={error}
          onLogin={login}
        />
      </main>
    );
  }

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      {error && profile ? (
        <article className="rounded-2xl border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-6 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.1),transparent_24%),radial-gradient(circle_at_80%_20%,rgba(116,185,127,0.14),transparent_28%),linear-gradient(135deg,#171919,#0d0f10)] p-6 md:p-8 xl:grid-cols-[minmax(0,1.15fr)_22rem]">
        <div className="grid gap-6">
          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/marketplace"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-neutral-50 hover:text-neutral-50"
            >
              Back to board
            </Link>
            <span className="label text-[#dce85d]">Runtime dossier</span>
            <span className="rounded-full border border-[rgba(116,185,127,0.18)] bg-[#74b97f]/10 px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">
              {profile?.status ?? "Loading"}
            </span>
          </div>

          <div className="grid gap-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="grid max-w-4xl gap-3">
                <div className="flex flex-wrap items-center gap-3 text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">
                  <span>{profile?.strategy_type ?? "Strategy"}</span>
                  <span className="text-neutral-700">/</span>
                  <span>{profile?.authoring_mode ?? "Build flow"}</span>
                  <span className="text-neutral-700">/</span>
                  <span>{profile?.mode ?? "Mode"}</span>
                </div>
                <h1 className="max-w-5xl font-mono text-[clamp(2.2rem,5vw,4.3rem)] font-extrabold uppercase leading-[0.9] tracking-[-0.05em] text-neutral-50">
                  {profile?.bot_name ?? "Loading strategy"}
                </h1>
                <p className="max-w-3xl text-sm leading-7 text-neutral-400 md:text-base">
                  {profile?.description ?? "Loading the public runtime profile, replay drift, and creator trust signals."}
                </p>
              </div>

              {profile?.creator ? (
                <Link
                  href={`/marketplace/creators/${profile.creator.creator_id}`}
                  className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
                >
                  {profile.creator.display_name}
                </Link>
              ) : null}
            </div>

              {profile ? <TrustBadgeStrip trust={profile.trust} /> : null}
              {profile && profile.visibility !== "public" ? (
                <AccessRibbon visibility={profile.visibility} accessNote={profile.access_note} />
              ) : null}
            </div>

          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
            <HeroStat
              label="Marketplace rank"
              value={profile?.rank ? `#${profile.rank}` : loading ? "..." : "Unranked"}
              accent="text-[#dce85d]"
              detail="Current board position"
            />
            <HeroStat
              label="Trust score"
              value={profile ? `${profile.trust.trust_score}` : "--"}
              accent="text-neutral-50"
              detail={profile ? profile.trust.summary : "Trust model"}
            />
            <HeroStat
              label="Total PnL"
              value={profile ? formatSigned(profile.pnl_total) : "--"}
              accent={profile && profile.pnl_total < 0 ? "text-[#ff8a9b]" : "text-[#74b97f]"}
              detail="Lifetime public runtime result"
            />
            <HeroStat
              label="Risk grade"
              value={profile?.trust.risk_grade ?? "--"}
              accent="text-[#74b97f]"
              detail={profile ? `Risk score ${profile.trust.risk_score}` : "Risk profile"}
            />
          </div>
        </div>

        <aside className="grid self-start gap-4 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#101213] p-5">
          <div className="grid gap-1">
            <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">Action deck</div>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">Copy or clone</h2>
            <p className="text-sm leading-7 text-neutral-400">
              Use the live runtime directly or fork the setup into a draft before making changes.
            </p>
          </div>

          <div className="grid gap-3">
            <button
              type="button"
              onClick={() => setOpenMirror(true)}
              disabled={!profile || loading}
              className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:opacity-60"
            >
              Follow live
            </button>
            <button
              type="button"
              onClick={() => setOpenClone(true)}
              disabled={!profile || loading}
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f] disabled:opacity-60"
            >
              Clone draft
            </button>
          </div>

          <div className="grid gap-3 border-t border-white/6 pt-4">
            <MiniStat label="Live PnL" value={profile ? formatSigned(profile.pnl_unrealized) : "--"} />
            <MiniStat label="Win streak" value={profile ? `${profile.win_streak}` : "--"} />
            <MiniStat label="Failure rate" value={profile ? `${profile.trust.failure_rate_pct.toFixed(2)}%` : "--"} />
            <MiniStat label="Model uptime" value={profile ? `${profile.trust.uptime_pct.toFixed(1)}%` : "--"} />
          </div>
        </aside>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(20rem,0.95fr)] xl:items-start">
        <div className="grid self-start gap-5">
          {profile ? <DriftVisual drift={profile.drift} /> : <LoadingCard copy="Loading replay drift..." />}
          {profile ? <StrategyPassportPanel passport={profile.passport} /> : <LoadingCard copy="Loading strategy passport..." />}
        </div>

        <div className="grid self-start gap-5">
          <SignalBoard profile={profile} loading={loading} />
          {profile ? <CreatorReputationCard creator={profile.creator} /> : <LoadingCard copy="Loading creator reputation..." />}
        </div>
      </section>

      <section className="grid gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid gap-1">
            <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Activity stream</div>
            <h2 className="font-mono text-[clamp(1.75rem,3vw,2.35rem)] font-bold uppercase tracking-tight text-neutral-50">
              Recent runtime activity
            </h2>
            <p className="text-sm text-neutral-400">Latest decisions, outcomes, and repeated checks.</p>
          </div>

          <div className="grid justify-items-end gap-2">
            <span className="text-xs text-neutral-500">
              latest {profile?.recent_events.length ?? 0} events, refreshed with the marketplace profile
            </span>
            {profile?.creator ? (
              <Link
                href={`/marketplace/creators/${profile.creator.creator_id}`}
                className="rounded-full border border-white/10 px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
              >
                Creator page
              </Link>
            ) : null}
          </div>
        </div>

        {loading && !profile ? (
          <article className="rounded-[1.6rem] bg-[#16181a] px-5 py-6 text-sm leading-6 text-neutral-400">
            Loading recent runtime activity...
          </article>
        ) : (
          <ExecutionLog events={profile?.recent_events ?? []} />
        )}
      </section>

      <BotMirrorModal
        runtime={profile ? { runtime_id: profile.runtime_id, bot_name: profile.bot_name, rank: profile.rank ?? undefined } : null}
        open={openMirror}
        onClose={() => setOpenMirror(false)}
      />

      <BotCloneModal
        runtime={profile ? { runtime_id: profile.runtime_id, bot_name: profile.bot_name } : null}
        open={openClone}
        onClose={() => setOpenClone(false)}
      />
    </main>
  );
}

function SignalBoard({ profile, loading }: { profile: RuntimeProfile | null; loading: boolean }) {
  if (!profile) {
    return <LoadingCard copy={loading ? "Loading signal board..." : "Signal board is unavailable."} />;
  }

  return (
    <article className="grid gap-4 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <div className="grid gap-1">
        <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Signal board</div>
        <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">Operational read</h2>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <MiniStat label="Replay alignment" value={`${profile.drift.score}`} tone="lime" />
        <MiniStat label="Drift state" value={profile.drift.status} tone="neutral" />
        <MiniStat label="Active mirrors" value={`${profile.creator.active_mirror_count}`} tone="lime" />
        <MiniStat label="Public bots" value={`${profile.creator.public_bot_count}`} tone="neutral" />
      </div>

      <div className="grid gap-3 rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Trust summary</span>
          <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
            {profile.trust.health}
          </span>
        </div>
        <p className="text-sm leading-7 text-neutral-400">{profile.trust.summary}</p>
      </div>
    </article>
  );
}

function AccessRibbon({ visibility, accessNote }: { visibility?: string; accessNote?: string }) {
  return (
    <article className="grid gap-3 rounded-[1.4rem] border border-[rgba(220,232,93,0.16)] bg-[linear-gradient(135deg,rgba(220,232,93,0.1),rgba(116,185,127,0.06),rgba(13,15,16,0.2))] px-4 py-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="rounded-full border border-[rgba(220,232,93,0.26)] bg-[#dce85d]/10 px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">
          {formatVisibilityLabel(visibility)} lane
        </span>
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
          Shared by direct link
        </span>
      </div>
      <p className="max-w-3xl text-sm leading-7 text-neutral-300">
        {accessNote?.trim()
          ? accessNote
          : "This strategy stays off the public board. Access follows the creator's invite settings, then opens clone and follow actions from the same page."}
      </p>
    </article>
  );
}

function AccessGate({
  runtimeId,
  authenticated,
  walletAddress,
  error,
  onLogin,
}: {
  runtimeId: string;
  authenticated: boolean;
  walletAddress?: string | null;
  error: string | null;
  onLogin: () => void;
}) {
  const title = authenticated
    ? "This wallet is not cleared for this runtime"
    : "This runtime is not on the public board";
  const copy = authenticated
    ? `Connected wallet ${shortAddress(walletAddress)} could not unlock this shared strategy. Ask the creator to add this wallet to the invite list, or switch to the wallet they invited.`
    : "If a creator shared this strategy with you, connect the invited wallet first. The same link will unlock the runtime, live follow controls, and clone actions.";

  return (
    <section className="grid gap-6 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.12),transparent_22%),radial-gradient(circle_at_82%_18%,rgba(116,185,127,0.14),transparent_28%),linear-gradient(135deg,#171919,#0d0f10)] p-6 md:p-8 xl:grid-cols-[minmax(0,1.1fr)_22rem]">
      <div className="grid gap-5">
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/marketplace"
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-neutral-50 hover:text-neutral-50"
          >
            Back to board
          </Link>
          <span className="rounded-full border border-[rgba(220,232,93,0.24)] bg-[#dce85d]/10 px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">
            Shared runtime
          </span>
        </div>

        <div className="grid gap-3">
          <div className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">
            Runtime ID / {runtimeId.slice(0, 12)}...
          </div>
          <h1 className="max-w-4xl font-mono text-[clamp(2.1rem,5vw,4rem)] font-extrabold uppercase leading-[0.9] tracking-[-0.05em] text-neutral-50">
            {title}
          </h1>
          <p className="max-w-3xl text-sm leading-7 text-neutral-300 md:text-base">
            {copy}
          </p>
        </div>

        {error ? (
          <article className="rounded-[1.45rem] border border-[rgba(255,138,155,0.24)] bg-[#ff8a9b]/10 px-4 py-4 text-sm leading-7 text-neutral-100">
            {error}
          </article>
        ) : null}
      </div>

      <aside className="grid gap-4 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#101213] p-5">
        <div className="grid gap-1">
          <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">Invite access</div>
          <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
            Unlock the shared lane
          </h2>
          <p className="text-sm leading-7 text-neutral-400">
            Owners now share the runtime link directly. Access is checked against the invited wallet after sign-in.
          </p>
        </div>

        {!authenticated ? (
          <button
            type="button"
            onClick={onLogin}
            className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
          >
            Connect invited wallet
          </button>
        ) : (
          <div className="rounded-[1.2rem] border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-4 text-sm leading-7 text-neutral-300">
            Signed in as {shortAddress(walletAddress)}.
          </div>
        )}

        <div className="grid gap-3 border-t border-white/6 pt-4">
          <MiniStat label="Access type" value={authenticated ? "Invite-aware" : "Sign in required"} tone="lime" />
          <MiniStat label="Board status" value="Off public board" tone="neutral" />
          <MiniStat label="Runtime link" value="Shared directly" />
        </div>
      </aside>
    </section>
  );
}

function HeroStat({ label, value, accent, detail }: { label: string; value: string; accent: string; detail: string }) {
  return (
    <article className="grid gap-2 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#111314] p-5">
      <span className="label text-neutral-400">{label}</span>
      <div className={`mt-2 font-mono text-2xl font-bold ${accent}`}>{value}</div>
      <p className="text-xs leading-6 text-neutral-500">{detail}</p>
    </article>
  );
}

function MiniStat({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "neutral" | "lime" }) {
  const valueClass =
    tone === "lime" ? "text-[#dce85d]" : tone === "neutral" ? "text-neutral-50 uppercase" : "text-neutral-50";

  return (
    <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3">
      <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">{label}</div>
      <div className={`mt-1 font-mono text-xl font-bold ${valueClass}`}>{value}</div>
    </div>
  );
}

function LoadingCard({ copy }: { copy: string }) {
  return (
    <article className="rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-6 text-sm text-neutral-400">
      {copy}
    </article>
  );
}
