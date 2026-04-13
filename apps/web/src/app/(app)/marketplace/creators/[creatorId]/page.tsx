"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { CreatorReputationCard } from "@/components/leaderboard/creator-reputation-card";
import {
  fetchMarketplaceCreatorProfile,
  type MarketplaceCreatorProfile,
} from "@/lib/public-bots";

export default function MarketplaceCreatorPage({ params: paramsPromise }: { params: Promise<{ creatorId: string }> }) {
  const params = use(paramsPromise);
  const [profile, setProfile] = useState<MarketplaceCreatorProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();

    async function loadCreator() {
      try {
        setProfile(await fetchMarketplaceCreatorProfile(params.creatorId, controller.signal));
      } catch (loadError) {
        if (!controller.signal.aborted) {
          setError(loadError instanceof Error ? loadError.message : "Could not load creator profile");
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void loadCreator();
    return () => controller.abort();
  }, [params.creatorId]);

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      <section className="flex flex-wrap items-end justify-between gap-4 border-b border-[rgba(255,255,255,0.08)] pb-6 md:pb-8">
        <div className="grid gap-2">
          <h1 className="font-mono text-[clamp(2rem,4vw,2.8rem)] font-bold uppercase tracking-tight text-neutral-50">
            {profile?.display_name ?? "Creator"}
          </h1>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400">
            {profile?.headline ?? "See the creator's public strategies, audience reach, and trust profile."}
          </p>
        </div>
        <Link
          href="/marketplace"
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-neutral-50 hover:text-neutral-50"
        >
          Back to marketplace
        </Link>
      </section>

      {error ? (
        <article className="rounded-2xl border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-[1.08fr_0.92fr] lg:items-start">
        <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">
              Creator profile
            </span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              Public catalogue and publishing footprint
            </h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {(profile?.tags ?? []).map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-[rgba(255,255,255,0.1)] bg-[#0d0f10] px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300"
              >
                {tag}
              </span>
            ))}
          </div>
        </article>

        <article className="grid gap-3 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Marketplace footprint</span>
          <span className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
            {profile ? `${profile.marketplace_reach_score} reach` : "Loading"}
          </span>
          <p className="text-sm leading-7 text-neutral-400">
            {profile
              ? `${profile.follower_count} followers, ${profile.active_mirror_count} live mirrors, and ${profile.public_bot_count} public strategies.`
              : "Loading creator footprint."}
          </p>
        </article>
      </section>

      <section className="grid gap-4 md:grid-cols-4">
        <HeroStat label="Reach" value={profile ? `${profile.marketplace_reach_score}` : loading ? "..." : "--"} accent="text-[#dce85d]" />
        <HeroStat label="Trust avg" value={profile ? `${profile.average_trust_score}` : "--"} accent="text-[#74b97f]" />
        <HeroStat label="Followers" value={profile ? `${profile.follower_count}` : "--"} accent="text-neutral-50" />
        <HeroStat label="Best rank" value={profile?.best_rank ? `#${profile.best_rank}` : loading ? "..." : "Unranked"} accent="text-neutral-50" />
      </section>

      {profile ? (
        <CreatorReputationCard creator={profile} showBots showCreatorLink={false} />
      ) : (
        <article className="rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-6 text-sm text-neutral-400">
          Loading creator strategies...
        </article>
      )}
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
