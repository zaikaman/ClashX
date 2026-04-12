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
      {error ? (
        <article className="rounded-2xl border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.14),transparent_30%),linear-gradient(135deg,#16181a,#0d0f10)] p-6 md:p-8">
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/marketplace"
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-neutral-50 hover:text-neutral-50"
          >
            Back to marketplace
          </Link>
          <span className="label text-[#dce85d]">Creator profile</span>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.08fr_0.92fr] lg:items-end">
          <div className="grid gap-3">
            <h1 className="font-mono text-[clamp(2.2rem,5vw,4.1rem)] font-extrabold uppercase leading-[0.92] tracking-[-0.05em] text-neutral-50">
              {profile?.display_name ?? "Loading creator"}
            </h1>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400 md:text-base">
              {profile?.headline ?? "Loading creator publishing profile and live catalogue."}
            </p>

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
          </div>

          <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-5">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Marketplace footprint</span>
            <span className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              {profile ? `${profile.marketplace_reach_score} reach` : "Loading"}
            </span>
            <p className="text-sm leading-7 text-neutral-400">
              {profile ? `${profile.follower_count} followers, ${profile.active_mirror_count} live mirrors, and ${profile.public_bot_count} public strategies.` : "Loading creator footprint."}
            </p>
          </div>
        </div>
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
