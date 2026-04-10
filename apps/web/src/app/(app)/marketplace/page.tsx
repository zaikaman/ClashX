"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { TrustBadgeStrip } from "@/components/leaderboard/trust-badge-strip";
import {
  fetchMarketplaceOverview,
  type CreatorHighlight,
  type MarketplaceOverviewDiscoveryRow,
} from "@/lib/public-bots";

const BotMirrorModal = dynamic(
  () => import("@/components/copy/bot-mirror-modal").then((module) => module.BotMirrorModal),
  { ssr: false },
);
const BotCloneModal = dynamic(
  () => import("@/components/copy/bot-clone-modal").then((module) => module.BotCloneModal),
  { ssr: false },
);

function formatSignedPnl(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

export default function MarketplacePage() {
  const [rows, setRows] = useState<MarketplaceOverviewDiscoveryRow[]>([]);
  const [creators, setCreators] = useState<CreatorHighlight[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedForMirror, setSelectedForMirror] = useState<MarketplaceOverviewDiscoveryRow | null>(null);
  const [selectedForClone, setSelectedForClone] = useState<MarketplaceOverviewDiscoveryRow | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadMarketplace() {
      try {
        const overview = await fetchMarketplaceOverview({
          discoverLimit: 36,
          featuredLimit: 4,
          creatorLimit: 6,
          signal: controller.signal,
        });
        if (controller.signal.aborted) {
          return;
        }
        setRows(overview.discover);
        setCreators(overview.creators);
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

  const topThree = useMemo(() => rows.slice(0, 3), [rows]);
  const featuredCreators = useMemo(() => creators.slice(0, 4), [creators]);
  const liveCopies = useMemo(() => rows.reduce((sum, row) => sum + row.copy_stats.active_mirror_count, 0), [rows]);

  return (
    <main className="shell grid gap-6 pb-10 md:gap-8 md:pb-12">
      {error ? (
        <article className="rounded-2xl border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="flex flex-wrap items-end justify-between gap-4 border-b border-[rgba(255,255,255,0.08)] pb-6 md:pb-8">
        <div className="grid gap-2">
          <h1 className="font-mono text-[clamp(2rem,4vw,2.8rem)] font-bold uppercase tracking-tight text-neutral-50">
            Marketplace
          </h1>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400">
            Discover live strategies and the creators behind them.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/copy"
            className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
          >
            Open copy center
          </Link>
          <Link
            href={topThree[0] ? `/marketplace/${topThree[0].runtime_id}` : "/marketplace"}
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
          >
            View top profile
          </Link>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr] xl:items-start">
        <div className="grid self-start gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">
                Front runners
              </span>
              <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
                Top strategies this season
              </h2>
              <p className="max-w-2xl text-sm leading-7 text-neutral-400">
                A quick look at the strongest performers on the board right now.
              </p>
            </div>
          </div>

          {topThree.length > 0 ? (
            <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <TopRuntimeHero
                row={topThree[0]}
                onMirror={() => setSelectedForMirror(topThree[0])}
                onClone={() => setSelectedForClone(topThree[0])}
              />

              <div className="grid gap-4">
                {topThree.slice(1).map((row) => (
                  <CompactRuntimeCard
                    key={row.runtime_id}
                    row={row}
                    onMirror={() => setSelectedForMirror(row)}
                    onClone={() => setSelectedForClone(row)}
                  />
                ))}
              </div>
            </div>
          ) : (
            <EmptyPanel loading={loading} idleCopy="No public strategies are available right now." />
          )}
        </div>

        <div className="grid self-start gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#74b97f]">
              Creator signal
            </span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              Creators to watch
            </h2>
            <p className="text-sm leading-7 text-neutral-400">
              A snapshot of creators with strong reach, active followers, and standout bots.
            </p>
          </div>

          {featuredCreators.length > 0 ? (
            <div className="grid gap-3">
              {featuredCreators.map((creator) => (
                <CreatorSignalRow key={creator.creator_id} creator={creator} />
              ))}
            </div>
          ) : (
            <EmptyPanel loading={loading} idleCopy="No creator profiles are available right now." />
          )}
        </div>
      </section>

      <section className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4 md:p-5">
        <div className="flex flex-wrap items-end justify-between gap-3 px-1">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">
              Full board
            </span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
              Full rankings
            </h2>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400">
              Compare trust, activity, creator reach, and performance across the full board.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <BoardPill label="Strategies" value={loading ? "..." : `${rows.length}`} />
            <BoardPill label="Mirrors" value={loading ? "..." : `${liveCopies}`} />
            <BoardPill label="Creators" value={loading ? "..." : `${creators.length}`} />
          </div>
        </div>

        {rows.length > 0 ? (
          <div className="grid gap-3">
            {rows.map((row, index) => (
              <BoardRow
                key={row.runtime_id}
                row={row}
                index={index}
                onMirror={() => setSelectedForMirror(row)}
                onClone={() => setSelectedForClone(row)}
              />
            ))}
          </div>
        ) : (
          <article className="rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-6 text-sm leading-7 text-neutral-400">
            {loading ? "Loading rankings..." : "No active public strategies are available."}
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


function TopRuntimeHero({
  row,
  onMirror,
  onClone,
}: {
  row: MarketplaceOverviewDiscoveryRow;
  onMirror: () => void;
  onClone: () => void;
}) {
  return (
    <article className="grid gap-5 rounded-[1.8rem] border border-[rgba(220,232,93,0.14)] bg-[linear-gradient(180deg,rgba(220,232,93,0.08),rgba(13,15,16,0)_40%),#0d0f10] p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-mono text-4xl font-extrabold text-[#dce85d]">#{row.rank}</span>
            <span className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[#16181a] px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
              {row.strategy_type}
            </span>
            <span className="rounded-full border border-[rgba(116,185,127,0.18)] bg-[#74b97f]/10 px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">
              {row.publishing.visibility}
            </span>
          </div>

          <div className="grid gap-1">
            <Link
              href={`/marketplace/${row.runtime_id}`}
              className="font-mono text-[clamp(1.7rem,3vw,2.4rem)] font-bold uppercase tracking-[-0.04em] text-neutral-50 transition hover:text-[#dce85d]"
            >
              {row.bot_name}
            </Link>
            <p className="max-w-2xl text-sm leading-7 text-neutral-400">
              {row.publishing.hero_headline || row.creator.summary}
            </p>
          </div>
        </div>

        <Link
          href={`/marketplace/creators/${row.creator.creator_id}`}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
        >
          {row.creator.display_name}
        </Link>
      </div>

      <TrustBadgeStrip trust={row.trust} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile label="Total PnL" value={formatSignedPnl(row.pnl_total)} accent={row.pnl_total >= 0 ? "text-[#74b97f]" : "text-[#ff8a9b]"} />
        <MetricTile label="Trust score" value={`${row.trust.trust_score}`} accent="text-neutral-50" />
        <MetricTile label="Live mirrors" value={`${row.copy_stats.active_mirror_count}`} accent="text-[#dce85d]" />
        <MetricTile label="Creator reach" value={`${row.creator.marketplace_reach_score}`} accent="text-[#74b97f]" />
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onMirror}
          className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
        >
          Follow live
        </button>
        <button
          type="button"
          onClick={onClone}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
        >
          Clone draft
        </button>
      </div>
    </article>
  );
}

function CompactRuntimeCard({
  row,
  onMirror,
  onClone,
}: {
  row: MarketplaceOverviewDiscoveryRow;
  onMirror: () => void;
  onClone: () => void;
}) {
  return (
    <article className="grid gap-4 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-2xl font-extrabold text-[#dce85d]">#{row.rank}</span>
            <span className="text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
              {row.creator.display_name}
            </span>
          </div>
          <Link
            href={`/marketplace/${row.runtime_id}`}
            className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50 transition hover:text-[#dce85d]"
          >
            {row.bot_name}
          </Link>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onMirror}
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
          >
            Follow
          </button>
          <button
            type="button"
            onClick={onClone}
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
          >
            Clone
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricTile label="Trust" value={`${row.trust.trust_score}`} accent="text-neutral-50" />
        <MetricTile label="Mirrors" value={`${row.copy_stats.active_mirror_count}`} accent="text-[#dce85d]" />
        <MetricTile label="PnL" value={formatSignedPnl(row.pnl_total)} accent={row.pnl_total >= 0 ? "text-[#74b97f]" : "text-[#ff8a9b]"} />
      </div>
    </article>
  );
}

function CreatorSignalRow({ creator }: { creator: CreatorHighlight }) {
  return (
    <article className="grid gap-4 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <Link
            href={`/marketplace/creators/${creator.creator_id}`}
            className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50 transition hover:text-[#dce85d]"
          >
            {creator.display_name}
          </Link>
          <p className="text-sm leading-7 text-neutral-400">{creator.headline || creator.summary}</p>
        </div>

        <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
          {creator.reputation_label}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricTile label="Reach" value={`${creator.marketplace_reach_score}`} accent="text-[#dce85d]" />
        <MetricTile label="Followers" value={`${creator.follower_count}`} accent="text-neutral-50" />
        <MetricTile label="Public bots" value={`${creator.public_bot_count}`} accent="text-[#74b97f]" />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1.25rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-4 py-3">
        <div className="grid gap-1">
          <span className="text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
            Spotlight bot
          </span>
          <span className="font-mono text-base font-bold uppercase tracking-tight text-neutral-50">
            {creator.spotlight_bot.bot_name}
          </span>
        </div>
        <div className="text-right">
          <div className="font-mono text-lg font-bold text-neutral-50">
            #{creator.spotlight_bot.rank}
          </div>
          <div className="text-xs text-neutral-500">
            {creator.spotlight_bot.copy_stats.active_mirror_count} live mirrors
          </div>
        </div>
      </div>
    </article>
  );
}

function BoardPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-3 py-1.5 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
      {label}: {value}
    </div>
  );
}

function BoardRow({
  row,
  index,
  onMirror,
  onClone,
}: {
  row: MarketplaceOverviewDiscoveryRow;
  index: number;
  onMirror: () => void;
  onClone: () => void;
}) {
  return (
    <article
      className="stagger-in grid gap-4 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4 transition hover:border-[rgba(220,232,93,0.16)] hover:bg-[#121416]"
      style={{ animationDelay: `${index * 22}ms` }}
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(18rem,0.8fr)] lg:items-start">
        <div className="grid gap-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="grid gap-1">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-mono text-2xl font-extrabold text-[#dce85d]">#{row.rank}</span>
                <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
                  {row.strategy_type}
                </span>
                <span className="rounded-full border border-[rgba(116,185,127,0.18)] bg-[#74b97f]/10 px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">
                  {row.publishing.visibility}
                </span>
              </div>
              <Link
                href={`/marketplace/${row.runtime_id}`}
                className="font-mono text-[1.35rem] font-bold uppercase tracking-tight text-neutral-50 transition hover:text-[#dce85d]"
              >
                {row.bot_name}
              </Link>
              <p className="text-sm text-neutral-500">
                {row.creator.display_name} / {row.creator.reputation_label}
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={onMirror}
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
              >
                Follow
              </button>
              <button
                type="button"
                onClick={onClone}
                className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1.5 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
              >
                Clone
              </button>
            </div>
          </div>

          <TrustBadgeStrip trust={row.trust} />
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricTile label="Trust" value={`${row.trust.trust_score}`} accent="text-neutral-50" />
          <MetricTile label="Mirrors" value={`${row.copy_stats.active_mirror_count}`} accent="text-[#dce85d]" />
          <MetricTile label="Reach" value={`${row.creator.marketplace_reach_score}`} accent="text-[#74b97f]" />
          <MetricTile label="PnL" value={formatSignedPnl(row.pnl_total)} accent={row.pnl_total >= 0 ? "text-[#74b97f]" : "text-[#ff8a9b]"} />
        </div>
      </div>
    </article>
  );
}

function MetricTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-4 py-3">
      <div className="text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</div>
      <div className={`mt-1 font-mono text-xl font-bold ${accent}`}>{value}</div>
    </div>
  );
}

function EmptyPanel({ loading, idleCopy }: { loading: boolean; idleCopy: string }) {
  return (
    <article className="rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-5 py-6 text-sm leading-7 text-neutral-400">
      {loading ? "Loading marketplace..." : idleCopy}
    </article>
  );
}
