"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { BotCloneModal } from "@/components/copy/bot-clone-modal";
import { BotMirrorModal } from "@/components/copy/bot-mirror-modal";
import { BotRuntimeCard } from "@/components/leaderboard/bot-runtime-card";
import { CreatorSpotlightCard } from "@/components/leaderboard/creator-spotlight-card";
import { FeaturedBotShelf } from "@/components/leaderboard/featured-bot-shelf";
import { TrustBadgeStrip } from "@/components/leaderboard/trust-badge-strip";
import {
  fetchCreatorHighlights,
  fetchFeaturedShelves,
  fetchMarketplaceDiscover,
  type CreatorHighlight,
  type FeaturedShelf,
  type MarketplaceDiscoveryRow,
} from "@/lib/public-bots";

const SEASON_ZERO_YEAR = 2026;

function getSeasonContext(now = new Date()) {
  const month = now.getMonth();
  const quarterIndex = Math.floor(month / 3);
  const seasonNumber = (now.getFullYear() - SEASON_ZERO_YEAR) * 4 + quarterIndex + 1;
  const seasonStart = new Date(now.getFullYear(), quarterIndex * 3, 1);
  const nextSeasonStart = new Date(now.getFullYear(), (quarterIndex + 1) * 3, 1);

  return {
    seasonNumber,
    seasonStart,
    nextSeasonStart,
    quarterLabel: `Q${quarterIndex + 1} ${now.getFullYear()}`,
  };
}

export default function BotLeaderboardPage() {
  const [rows, setRows] = useState<MarketplaceDiscoveryRow[]>([]);
  const [featuredShelves, setFeaturedShelves] = useState<FeaturedShelf[]>([]);
  const [creators, setCreators] = useState<CreatorHighlight[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedForMirror, setSelectedForMirror] = useState<MarketplaceDiscoveryRow | null>(null);
  const [selectedForClone, setSelectedForClone] = useState<MarketplaceDiscoveryRow | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadMarketplace() {
      try {
        const [discoverRows, shelves, creatorRows] = await Promise.all([
          fetchMarketplaceDiscover(36, { signal: controller.signal }),
          fetchFeaturedShelves(4, controller.signal),
          fetchCreatorHighlights(6, controller.signal),
        ]);
        if (controller.signal.aborted) {
          return;
        }
        setRows(discoverRows);
        setFeaturedShelves(shelves);
        setCreators(creatorRows);
        setError(null);
      } catch (loadError) {
        if (!controller.signal.aborted) {
          setError(loadError instanceof Error ? loadError.message : "Could not load marketplace");
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void loadMarketplace();
    return () => controller.abort();
  }, []);

  const season = useMemo(() => getSeasonContext(), []);
  const topThree = useMemo(() => rows.slice(0, 3), [rows]);
  const liveCopies = useMemo(
    () => rows.reduce((sum, row) => sum + row.copy_stats.active_mirror_count, 0),
    [rows],
  );
  const mostFollowedCreator = useMemo(
    () => [...creators].sort((left, right) => right.follower_count - left.follower_count)[0] ?? null,
    [creators],
  );
  const strongestShelf = featuredShelves[0] ?? null;

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      {error ? (
        <article className="rounded-2xl border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.14),transparent_32%),linear-gradient(135deg,#16181a,#0d0f10)] p-6 md:p-8">
        <span className="label text-[#dce85d]">Creator marketplace</span>
        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
          <div className="grid gap-3">
            <h1 className="font-mono text-[clamp(2.2rem,5vw,4.25rem)] font-extrabold uppercase leading-[0.92] tracking-[-0.05em] text-neutral-50">
              Discover creator shelves, trust signals, and copy-ready live bots.
            </h1>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400 md:text-base">
              The board now blends live rank, creator reach, featured collections, and publishing access so you can find the right strategy faster.
            </p>
          </div>

          <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-5">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Current season</span>
              <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">
                {season.quarterLabel}
              </span>
            </div>
            <span className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              Season {season.seasonNumber}
            </span>
            <p className="text-sm leading-7 text-neutral-400">
              Started {season.seasonStart.toLocaleDateString()} and resets on {season.nextSeasonStart.toLocaleDateString()}.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/copy"
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
              >
                Open copy center
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-4">
        <HeroMetric label="Published bots" value={loading ? "..." : `${rows.length}`} copy="Live public strategies on the board." />
        <HeroMetric label="Live copies" value={loading ? "..." : `${liveCopies}`} copy="Active mirror relationships right now." />
        <HeroMetric
          label="Top shelf"
          value={strongestShelf ? `${strongestShelf.bots.length}` : "--"}
          copy={strongestShelf?.title ?? "Loading featured collections."}
        />
        <HeroMetric
          label="Most followed"
          value={mostFollowedCreator ? `${mostFollowedCreator.follower_count}` : "--"}
          copy={mostFollowedCreator?.display_name ?? "Scanning creator reach."}
        />
      </section>

      {featuredShelves.length > 0 ? (
        <section className="grid gap-5">
          {featuredShelves.map((shelf) => (
            <FeaturedBotShelf
              key={shelf.collection_key}
              shelf={shelf}
              onMirror={(runtimeId) => {
                const row = rows.find((item) => item.runtime_id === runtimeId) ?? null;
                setSelectedForMirror(row);
              }}
              onClone={(runtimeId) => {
                const row = rows.find((item) => item.runtime_id === runtimeId) ?? null;
                setSelectedForClone(row);
              }}
            />
          ))}
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <div className="grid gap-4">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Front row</span>
            <span className="text-sm text-neutral-400">Start with the public strategies carrying the strongest live signal.</span>
          </div>

          {topThree.length > 0 ? (
            topThree.map((row) => (
              <BotRuntimeCard
                key={row.runtime_id}
                row={row}
                onMirror={() => setSelectedForMirror(row)}
                onClone={() => setSelectedForClone(row)}
              />
            ))
          ) : (
            <article className="rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-6 text-sm leading-7 text-neutral-400">
              {loading ? "Loading public marketplace..." : "No public bots are available right now."}
            </article>
          )}
        </div>

        <div className="grid gap-4">
          <div className="flex items-center justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Creator radar</span>
              <span className="text-sm text-neutral-400">Follow the creators building sustained trust and audience pull.</span>
            </div>
          </div>

          {creators.length > 0 ? (
            creators.map((creator) => <CreatorSpotlightCard key={creator.creator_id} creator={creator} />)
          ) : (
            <article className="rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-6 text-sm leading-7 text-neutral-400">
              {loading ? "Loading creator spotlights..." : "No creator spotlights are ready yet."}
            </article>
          )}
        </div>
      </section>

      <section className="grid gap-3 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4 md:p-5">
        <div className="flex items-center justify-between gap-3 px-1">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Full board</span>
            <span className="text-sm text-neutral-400">Scan trust, creator reach, and copy demand before opening a profile.</span>
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,0.1fr)_minmax(0,1fr)_minmax(0,0.28fr)_minmax(0,0.28fr)_minmax(0,0.28fr)_minmax(0,0.26fr)] gap-3 border-b border-[rgba(255,255,255,0.06)] px-4 pb-3">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Rank</span>
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Strategy</span>
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Trust</span>
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Copies</span>
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Creator</span>
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500 text-right">Actions</span>
        </div>

        {rows.length > 0 ? (
          rows.map((row, index) => (
            <article
              key={row.runtime_id}
              className="stagger-in grid grid-cols-[minmax(0,0.1fr)_minmax(0,1fr)_minmax(0,0.28fr)_minmax(0,0.28fr)_minmax(0,0.28fr)_minmax(0,0.26fr)] items-center gap-3 rounded-[1.5rem] border border-transparent bg-[#0d0f10] px-4 py-3.5 transition hover:border-[#dce85d]/15 hover:bg-[#121416]"
              style={{ animationDelay: `${index * 24}ms` }}
            >
              <span className="font-mono text-lg font-extrabold text-[#dce85d]">{row.rank}</span>

              <div className="grid gap-2">
                <div className="grid gap-0.5">
                  <Link
                    href={`/leaderboard/${row.runtime_id}`}
                    className="font-mono text-base font-bold uppercase tracking-tight text-neutral-50 transition hover:text-[#dce85d]"
                  >
                    {row.bot_name}
                  </Link>
                  <span className="text-xs text-neutral-500">
                    {row.creator.display_name} / {row.strategy_type} / {row.publishing.visibility}
                  </span>
                </div>
                <TrustBadgeStrip trust={row.trust} />
              </div>

              <div className="grid gap-0.5">
                <span className="font-mono text-xl font-bold text-neutral-50">{row.trust.trust_score}</span>
                <span className="text-xs text-neutral-500">
                  {row.trust.health} / risk {row.trust.risk_grade}
                </span>
              </div>

              <div className="grid gap-0.5">
                <span className="font-mono text-xl font-bold text-neutral-50">{row.copy_stats.active_mirror_count}</span>
                <span className="text-xs text-neutral-500">{row.copy_stats.clone_count} clones</span>
              </div>

              <div className="grid gap-0.5">
                <span className="font-mono text-xl font-bold text-neutral-50">{row.creator.marketplace_reach_score}</span>
                <span className="text-xs text-neutral-500">{row.creator.reputation_label}</span>
              </div>

              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedForMirror(row)}
                  className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
                >
                  Follow
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedForClone(row)}
                  className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
                >
                  Clone
                </button>
              </div>
            </article>
          ))
        ) : (
          <article className="rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-6 text-sm leading-7 text-neutral-400">
            {loading ? "Loading board..." : "No active public bots are available."}
          </article>
        )}
      </section>

      <BotMirrorModal
        runtime={selectedForMirror ? { runtime_id: selectedForMirror.runtime_id, bot_name: selectedForMirror.bot_name, rank: selectedForMirror.rank } : null}
        open={selectedForMirror !== null}
        onClose={() => setSelectedForMirror(null)}
      />

      <BotCloneModal
        runtime={selectedForClone ? { runtime_id: selectedForClone.runtime_id, bot_name: selectedForClone.bot_name } : null}
        open={selectedForClone !== null}
        onClose={() => setSelectedForClone(null)}
      />
    </main>
  );
}

function HeroMetric({ label, value, copy }: { label: string; value: string; copy: string }) {
  return (
    <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <span className="label text-neutral-400">{label}</span>
      <div className="mt-2 font-mono text-2xl font-bold uppercase text-neutral-50">{value}</div>
      <p className="text-sm leading-6 text-neutral-400">{copy}</p>
    </article>
  );
}
