"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { BotCloneModal } from "@/components/copy/bot-clone-modal";
import { BotMirrorModal } from "@/components/copy/bot-mirror-modal";
import { CreatorReputationCard } from "@/components/leaderboard/creator-reputation-card";
import { DriftVisual } from "@/components/leaderboard/drift-visual";
import { StrategyPassportPanel } from "@/components/leaderboard/strategy-passport-panel";
import { TrustBadgeStrip } from "@/components/leaderboard/trust-badge-strip";
import { fetchRuntimeProfile, type RuntimeProfile } from "@/lib/public-bots";

export default function MarketplaceRuntimePage({ params: paramsPromise }: { params: Promise<{ runtimeId: string }> }) {
  const params = use(paramsPromise);
  const [profile, setProfile] = useState<RuntimeProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [openMirror, setOpenMirror] = useState(false);
  const [openClone, setOpenClone] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    async function loadProfile() {
      try {
        setProfile(await fetchRuntimeProfile(params.runtimeId, controller.signal));
      } catch (loadError) {
        if (controller.signal.aborted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Could not load runtime profile");
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void loadProfile();
    return () => controller.abort();
  }, [params.runtimeId]);

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      {error ? (
        <article className="rounded-2xl border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(116,185,127,0.14),transparent_26%),radial-gradient(circle_at_bottom_right,rgba(220,232,93,0.12),transparent_24%),linear-gradient(135deg,#16181a,#0d0f10)] p-6 md:p-8">
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/marketplace"
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-neutral-50 hover:text-neutral-50"
          >
            Back to board
          </Link>
          <span className="label text-[#74b97f]">Strategy passport</span>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
          <div className="grid gap-3">
            <h1 className="font-mono text-[clamp(2.2rem,5vw,4.1rem)] font-extrabold uppercase leading-[0.92] tracking-[-0.05em] text-neutral-50">
              {profile?.bot_name ?? "Loading strategy"}
            </h1>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400 md:text-base">
              {profile?.description ?? "Loading the public runtime profile, replay drift, and creator trust signals."}
            </p>
            {profile ? <TrustBadgeStrip trust={profile.trust} /> : null}
          </div>

          <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-5">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Creator</span>
              {profile?.creator ? (
                <Link
                  href={`/marketplace/creators/${profile.creator.creator_id}`}
                  className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
                >
                  Open creator
                </Link>
              ) : null}
            </div>
            <div className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              {profile?.creator.display_name ?? "Loading"}
            </div>
            <p className="text-sm leading-7 text-neutral-400">
              {profile?.creator.summary ?? "Loading creator context."}
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-4">
          <HeroStat label="Marketplace rank" value={profile?.rank ? `#${profile.rank}` : loading ? "..." : "Unranked"} accent="text-[#dce85d]" />
          <HeroStat label="Trust score" value={profile ? `${profile.trust.trust_score}` : "--"} accent="text-neutral-50" />
          <HeroStat label="Total PnL" value={profile ? `${profile.pnl_total >= 0 ? "+" : ""}${profile.pnl_total.toFixed(2)}` : "--"} accent={profile && profile.pnl_total < 0 ? "text-[#ff8a9b]" : "text-[#74b97f]"} />
          <HeroStat label="Risk grade" value={profile?.trust.risk_grade ?? "--"} accent="text-[#74b97f]" />
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <div className="grid gap-5">
          {profile ? <DriftVisual drift={profile.drift} /> : <LoadingCard copy="Loading replay drift..." />}
          {profile ? <StrategyPassportPanel passport={profile.passport} /> : <LoadingCard copy="Loading strategy passport..." />}
        </div>

        <div className="grid gap-5">
          <article className="grid gap-4 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Live controls</div>
                <h2 className="mt-2 font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">Copy or clone</h2>
              </div>
              <div className="rounded-full border border-white/10 px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
                {profile?.status ?? "loading"}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <MiniStat label="Live PnL" value={profile ? `${profile.pnl_unrealized >= 0 ? "+" : ""}${profile.pnl_unrealized.toFixed(2)}` : "--"} />
              <MiniStat label="Win streak" value={profile ? `${profile.win_streak}` : "--"} />
              <MiniStat label="Failure rate" value={profile ? `${profile.trust.failure_rate_pct.toFixed(2)}%` : "--"} />
              <MiniStat label="Uptime model" value={profile ? `${profile.trust.uptime_pct.toFixed(1)}%` : "--"} />
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setOpenMirror(true)}
                disabled={!profile || loading}
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d] disabled:opacity-60"
              >
                Follow live
              </button>
              <button
                type="button"
                onClick={() => setOpenClone(true)}
                disabled={!profile || loading}
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f] disabled:opacity-60"
              >
                Clone draft
              </button>
            </div>
          </article>

          {profile ? <CreatorReputationCard creator={profile.creator} /> : <LoadingCard copy="Loading creator reputation..." />}
        </div>
      </section>

      <section className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Recent runtime events</span>
          {profile?.creator ? (
            <Link
              href={`/marketplace/creators/${profile.creator.creator_id}`}
              className="rounded-full border border-white/10 px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
            >
              Creator page
            </Link>
          ) : null}
        </div>

        {(profile?.recent_events ?? []).length > 0 ? (
          profile?.recent_events.map((event, index) => (
            <article
              key={event.id}
              className="stagger-in grid gap-2 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-4 py-4 md:grid-cols-[0.8fr_1fr_0.5fr_1fr] md:items-center"
              style={{ animationDelay: `${index * 25}ms` }}
            >
              <div className="font-mono text-base font-bold uppercase tracking-tight text-neutral-50">{event.event_type}</div>
              <div className="text-sm text-neutral-400">{event.decision_summary}</div>
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-neutral-400">{event.status}</div>
              <div className="text-xs text-neutral-500">{new Date(event.created_at).toLocaleString()}</div>
            </article>
          ))
        ) : (
          <article className="rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-6 text-sm text-neutral-400">
            {loading ? "Loading recent events..." : "No recent runtime events are available for this profile."}
          </article>
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

function HeroStat({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <span className="label text-neutral-400">{label}</span>
      <div className={`mt-2 font-mono text-2xl font-bold ${accent}`}>{value}</div>
    </article>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3">
      <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">{label}</div>
      <div className="mt-1 font-mono text-xl font-bold text-neutral-50">{value}</div>
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
