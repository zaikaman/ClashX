"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { BotCloneModal } from "@/components/copy/bot-clone-modal";
import { BotMirrorModal } from "@/components/copy/bot-mirror-modal";
import { BotRuntimeCard } from "@/components/leaderboard/bot-runtime-card";

type BotLeaderboardRow = {
  runtime_id: string;
  bot_definition_id: string;
  bot_name: string;
  strategy_type: string;
  authoring_mode: string;
  rank: number;
  pnl_total: number;
  pnl_unrealized: number;
  win_streak: number;
  drawdown: number;
  captured_at: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
  const [rows, setRows] = useState<BotLeaderboardRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedForMirror, setSelectedForMirror] = useState<BotLeaderboardRow | null>(null);
  const [selectedForClone, setSelectedForClone] = useState<BotLeaderboardRow | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadLeaderboard() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/bot-copy/leaderboard?limit=50`, { signal: controller.signal });
        const payload = (await response.json()) as BotLeaderboardRow[] | { detail?: string };
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Could not load leaderboard" : "Could not load leaderboard");
        }
        setRows(payload as BotLeaderboardRow[]);
      } catch (loadError) {
        if (controller.signal.aborted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Could not load leaderboard");
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void loadLeaderboard();
    return () => controller.abort();
  }, []);

  const topThree = useMemo(() => rows.slice(0, 3), [rows]);
  const season = useMemo(() => getSeasonContext(), []);

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      {error ? (
        <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-4 md:grid-cols-3">
        <article className="grid gap-1 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
          <span className="label text-[#dce85d]">Active Season</span>
          <span className="font-mono text-4xl font-bold uppercase text-neutral-50">
            {`Season ${season.seasonNumber}`}
          </span>
          <p className="text-sm leading-6 text-neutral-400">
            The {season.quarterLabel} leaderboard. All actively deployed bots are ranked here.
          </p>
        </article>
        <article className="grid gap-1 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
          <span className="label text-[#74b97f]">Next Season Starts</span>
          <span className="font-mono text-xl font-bold uppercase text-neutral-50">
            {season.nextSeasonStart.toLocaleDateString()}
          </span>
          <p className="text-sm leading-6 text-neutral-400">
            The current season ends and rankings reset every three months.
          </p>
        </article>
        <article className="grid gap-1 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Total Bots Ranked</span>
          <span className="font-mono text-xl font-bold uppercase text-neutral-50">
            {loading ? <div className="skeleton h-6 w-12 rounded-sm inline-block translate-y-1"></div> : rows.length}
          </span>
          <p className="text-sm leading-6 text-neutral-400">
            Last updated: {rows[0]?.captured_at ? new Date(rows[0].captured_at).toLocaleString() : "Updating"}
          </p>
        </article>
      </section>

      <section className="grid gap-4 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-gradient-to-br from-[#16181a] via-[#16181a] to-[#dce85d]/10 p-6 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
        <div className="grid gap-3">
          <span className="label text-[#74b97f]">Global Seasonal Rankings</span>
          <h2 className="max-w-3xl font-mono text-[clamp(2rem,4vw,3.6rem)] font-extrabold uppercase leading-[0.9] tracking-[-0.04em] text-neutral-50">
            The global trading ladder.
          </h2>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400 md:text-base">
            Explore the top performing algorithms on our public leaderboard. Season {season.seasonNumber} began on {season.seasonStart.toLocaleDateString()} and will continue until Season {season.seasonNumber + 1} launches on {season.nextSeasonStart.toLocaleDateString()}.
          </p>
        </div>
        <div className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#090a0a]/80 p-4">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">How it works</span>
          <p className="text-sm leading-7 text-neutral-400">
            All bots compete globally in a single ladder. You can discover top strategies, inspect their performance, and clone them for your own use.
          </p>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.78fr_1.22fr]">
        <div className="grid gap-4 self-start">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Top Performers</span>
            <Link
              href="/copy"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
            >
              Browse Strategies
            </Link>
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
            <article className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-6 text-sm leading-7 text-neutral-400">
              {loading ? (
                <>
                  
<article className="grid gap-4 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
  <div className="flex items-start justify-between gap-4">
    <div className="flex items-baseline gap-4">
      <div className="skeleton h-8 w-12 rounded-lg"></div>
      <div className="grid gap-1">
        <div className="skeleton h-6 w-32 rounded-md"></div>
        <div className="skeleton h-3 w-20 rounded-md mt-1"></div>
      </div>
    </div>
    <div className="skeleton h-8 w-24 rounded-full"></div>
  </div>
  <div className="flex flex-wrap gap-8 my-2">
    {[1,2,3,4].map(i => (
      <div key={i} className="flex flex-col gap-1">
        <div className="skeleton h-3 w-12 rounded-sm"></div>
        <div className="skeleton h-6 w-16 rounded-md"></div>
      </div>
    ))}
  </div>
  <div className="flex flex-wrap gap-2">
    <div className="skeleton h-8 w-24 rounded-full"></div>
    <div className="skeleton h-8 w-24 rounded-full"></div>
  </div>
</article>

                  
<article className="grid gap-4 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
  <div className="flex items-start justify-between gap-4">
    <div className="flex items-baseline gap-4">
      <div className="skeleton h-8 w-12 rounded-lg"></div>
      <div className="grid gap-1">
        <div className="skeleton h-6 w-32 rounded-md"></div>
        <div className="skeleton h-3 w-20 rounded-md mt-1"></div>
      </div>
    </div>
    <div className="skeleton h-8 w-24 rounded-full"></div>
  </div>
  <div className="flex flex-wrap gap-8 my-2">
    {[1,2,3,4].map(i => (
      <div key={i} className="flex flex-col gap-1">
        <div className="skeleton h-3 w-12 rounded-sm"></div>
        <div className="skeleton h-6 w-16 rounded-md"></div>
      </div>
    ))}
  </div>
  <div className="flex flex-wrap gap-2">
    <div className="skeleton h-8 w-24 rounded-full"></div>
    <div className="skeleton h-8 w-24 rounded-full"></div>
  </div>
</article>

                  
<article className="grid gap-4 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
  <div className="flex items-start justify-between gap-4">
    <div className="flex items-baseline gap-4">
      <div className="skeleton h-8 w-12 rounded-lg"></div>
      <div className="grid gap-1">
        <div className="skeleton h-6 w-32 rounded-md"></div>
        <div className="skeleton h-3 w-20 rounded-md mt-1"></div>
      </div>
    </div>
    <div className="skeleton h-8 w-24 rounded-full"></div>
  </div>
  <div className="flex flex-wrap gap-8 my-2">
    {[1,2,3,4].map(i => (
      <div key={i} className="flex flex-col gap-1">
        <div className="skeleton h-3 w-12 rounded-sm"></div>
        <div className="skeleton h-6 w-16 rounded-md"></div>
      </div>
    ))}
  </div>
  <div className="flex flex-wrap gap-2">
    <div className="skeleton h-8 w-24 rounded-full"></div>
    <div className="skeleton h-8 w-24 rounded-full"></div>
  </div>
</article>

                </>
              ) : "No active bots found."}
            </article>
          )}
        </div>

        <section className="grid gap-2">
          <div className="grid grid-cols-[minmax(0,0.14fr)_minmax(0,1.2fr)_minmax(0,0.55fr)_minmax(0,0.5fr)_minmax(0,0.7fr)] gap-3 border-b border-[rgba(255,255,255,0.06)] px-4 pb-3">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Rank</span>
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Bot</span>
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Net PnL</span>
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Streak</span>
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 text-right">Actions</span>
          </div>

          {rows.length > 0 ? (
            rows.map((row, index) => (
              <article
                key={row.runtime_id}
                className="stagger-in grid grid-cols-[minmax(0,0.14fr)_minmax(0,1.2fr)_minmax(0,0.55fr)_minmax(0,0.5fr)_minmax(0,0.7fr)] items-center gap-3 rounded-2xl bg-[#16181a] px-4 py-3.5 transition-colors duration-200 hover:bg-neutral-900"
                style={{ animationDelay: `${index * 30}ms` }}
              >
                <span className="font-mono text-lg font-extrabold text-[#dce85d]">
                  {row.rank}
                </span>

                <div className="grid gap-0.5">
                  <Link
                    href={`/leaderboard/${row.runtime_id}`}
                    className="font-mono text-base font-bold uppercase tracking-tight text-neutral-50 transition hover:text-[#dce85d]"
                  >
                    {row.bot_name}
                  </Link>
                  <span className="text-xs text-neutral-500">
                    Builder / {row.strategy_type}
                  </span>
                </div>

                <span className={row.pnl_total >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}>
                  {row.pnl_total >= 0 ? "+" : ""}
                  {row.pnl_total.toFixed(2)}
                </span>

                <span className="font-semibold text-neutral-50">{row.win_streak}</span>

                <div className="flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedForMirror(row)}
                    className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
                  >
                    Follow live
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
            <article className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-6 text-sm leading-7 text-neutral-400">
              {loading ? (
                <div className="grid gap-2">
                  
<article className="grid grid-cols-[minmax(0,0.14fr)_minmax(0,1.2fr)_minmax(0,0.55fr)_minmax(0,0.5fr)_minmax(0,0.7fr)] items-center gap-3 rounded-2xl bg-[#16181a] px-4 py-3.5">
  <div className="skeleton h-6 w-6 rounded-md"></div>
  <div className="grid gap-1">
    <div className="skeleton h-5 w-28 rounded-md"></div>
    <div className="skeleton h-3 w-16 rounded-md"></div>
  </div>
  <div className="skeleton h-5 w-16 rounded-md"></div>
  <div className="skeleton h-5 w-8 rounded-md"></div>
  <div className="flex items-center justify-end gap-2">
    <div className="skeleton h-6 w-16 rounded-full"></div>
    <div className="skeleton h-6 w-16 rounded-full"></div>
  </div>
</article>

                  
<article className="grid grid-cols-[minmax(0,0.14fr)_minmax(0,1.2fr)_minmax(0,0.55fr)_minmax(0,0.5fr)_minmax(0,0.7fr)] items-center gap-3 rounded-2xl bg-[#16181a] px-4 py-3.5">
  <div className="skeleton h-6 w-6 rounded-md"></div>
  <div className="grid gap-1">
    <div className="skeleton h-5 w-28 rounded-md"></div>
    <div className="skeleton h-3 w-16 rounded-md"></div>
  </div>
  <div className="skeleton h-5 w-16 rounded-md"></div>
  <div className="skeleton h-5 w-8 rounded-md"></div>
  <div className="flex items-center justify-end gap-2">
    <div className="skeleton h-6 w-16 rounded-full"></div>
    <div className="skeleton h-6 w-16 rounded-full"></div>
  </div>
</article>

                  
<article className="grid grid-cols-[minmax(0,0.14fr)_minmax(0,1.2fr)_minmax(0,0.55fr)_minmax(0,0.5fr)_minmax(0,0.7fr)] items-center gap-3 rounded-2xl bg-[#16181a] px-4 py-3.5">
  <div className="skeleton h-6 w-6 rounded-md"></div>
  <div className="grid gap-1">
    <div className="skeleton h-5 w-28 rounded-md"></div>
    <div className="skeleton h-3 w-16 rounded-md"></div>
  </div>
  <div className="skeleton h-5 w-16 rounded-md"></div>
  <div className="skeleton h-5 w-8 rounded-md"></div>
  <div className="flex items-center justify-end gap-2">
    <div className="skeleton h-6 w-16 rounded-full"></div>
    <div className="skeleton h-6 w-16 rounded-full"></div>
  </div>
</article>

                  
<article className="grid grid-cols-[minmax(0,0.14fr)_minmax(0,1.2fr)_minmax(0,0.55fr)_minmax(0,0.5fr)_minmax(0,0.7fr)] items-center gap-3 rounded-2xl bg-[#16181a] px-4 py-3.5">
  <div className="skeleton h-6 w-6 rounded-md"></div>
  <div className="grid gap-1">
    <div className="skeleton h-5 w-28 rounded-md"></div>
    <div className="skeleton h-3 w-16 rounded-md"></div>
  </div>
  <div className="skeleton h-5 w-16 rounded-md"></div>
  <div className="skeleton h-5 w-8 rounded-md"></div>
  <div className="flex items-center justify-end gap-2">
    <div className="skeleton h-6 w-16 rounded-full"></div>
    <div className="skeleton h-6 w-16 rounded-full"></div>
  </div>
</article>

                  
<article className="grid grid-cols-[minmax(0,0.14fr)_minmax(0,1.2fr)_minmax(0,0.55fr)_minmax(0,0.5fr)_minmax(0,0.7fr)] items-center gap-3 rounded-2xl bg-[#16181a] px-4 py-3.5">
  <div className="skeleton h-6 w-6 rounded-md"></div>
  <div className="grid gap-1">
    <div className="skeleton h-5 w-28 rounded-md"></div>
    <div className="skeleton h-3 w-16 rounded-md"></div>
  </div>
  <div className="skeleton h-5 w-16 rounded-md"></div>
  <div className="skeleton h-5 w-8 rounded-md"></div>
  <div className="flex items-center justify-end gap-2">
    <div className="skeleton h-6 w-16 rounded-full"></div>
    <div className="skeleton h-6 w-16 rounded-full"></div>
  </div>
</article>

                </div>
              ) : "No active bots found."}
            </article>
          )}
        </section>
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
