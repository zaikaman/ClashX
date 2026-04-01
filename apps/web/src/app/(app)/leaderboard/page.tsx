"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { BotCloneModal } from "@/components/copy/bot-clone-modal";
import { BotMirrorModal } from "@/components/copy/bot-mirror-modal";
import { BotRuntimeCard } from "@/components/leaderboard/bot-runtime-card";
import { TrustBadgeStrip } from "@/components/leaderboard/trust-badge-strip";
import { fetchLeaderboard, type LeaderboardRow } from "@/lib/public-bots";

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
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedForMirror, setSelectedForMirror] = useState<LeaderboardRow | null>(null);
  const [selectedForClone, setSelectedForClone] = useState<LeaderboardRow | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadLeaderboard() {
      try {
        setRows(await fetchLeaderboard(50, controller.signal));
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

  const season = useMemo(() => getSeasonContext(), []);
  const topThree = useMemo(() => rows.slice(0, 3), [rows]);
  const mostTrusted = useMemo(() => [...rows].sort((a, b) => b.trust.trust_score - a.trust.trust_score)[0] ?? null, [rows]);
  const lowestDrift = useMemo(() => [...rows].sort((a, b) => b.drift.score - a.drift.score)[0] ?? null, [rows]);

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      {error ? (
        <article className="rounded-2xl border border-[#ff8a9b]/30 bg-[#ff8a9b]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.14),transparent_32%),linear-gradient(135deg,#16181a,#0d0f10)] p-6 md:p-8">
        <span className="label text-[#dce85d]">Leaderboard</span>
        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
          <div className="grid gap-3">
            <h1 className="font-mono text-[clamp(2.2rem,5vw,4.25rem)] font-extrabold uppercase leading-[0.92] tracking-[-0.05em] text-neutral-50">
              Compare live strategies with trust, drift, and release history.
            </h1>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400 md:text-base">
              Public bots are ranked here with live runtime health, replay alignment, creator reputation, and a version trail you can inspect before you copy anything.
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
        <HeroMetric label="Ranked bots" value={loading ? "..." : `${rows.length}`} copy="Public active runtimes on the board." />
        <HeroMetric label="Last snapshot" value={rows[0]?.captured_at ? new Date(rows[0].captured_at).toLocaleDateString() : "Updating"} copy="Scores refresh automatically." />
        <HeroMetric label="Most trusted" value={mostTrusted ? `${mostTrusted.trust.trust_score}` : "--"} copy={mostTrusted?.bot_name ?? "Scanning live trust signals."} />
        <HeroMetric label="Closest to replay" value={lowestDrift ? `${lowestDrift.drift.score}` : "--"} copy={lowestDrift?.bot_name ?? "Comparing replay drift."} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.82fr_1.18fr]">
        <div className="grid gap-4">
          <div className="flex items-center justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Front row</span>
              <span className="text-sm text-neutral-400">Start with the highest-signal public strategies.</span>
            </div>
            <Link
              href="/copy"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
            >
              Manage copied bots
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
            <article className="rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-6 text-sm leading-7 text-neutral-400">
              {loading ? "Loading public strategy passports..." : "No active public bots are ranked right now."}
            </article>
          )}
        </div>

        <section className="grid gap-3 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4 md:p-5">
          <div className="flex items-center justify-between gap-3 px-1">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Full board</span>
              <span className="text-sm text-neutral-400">Scan trust, drift, and creator strength before you open a profile.</span>
            </div>
          </div>

          <div className="grid grid-cols-[minmax(0,0.1fr)_minmax(0,1fr)_minmax(0,0.38fr)_minmax(0,0.38fr)_minmax(0,0.34fr)] gap-3 border-b border-[rgba(255,255,255,0.06)] px-4 pb-3">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Rank</span>
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Strategy</span>
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Trust</span>
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Drift</span>
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500 text-right">Actions</span>
          </div>

          {rows.length > 0 ? (
            rows.map((row, index) => (
              <article
                key={row.runtime_id}
                className="stagger-in grid grid-cols-[minmax(0,0.1fr)_minmax(0,1fr)_minmax(0,0.38fr)_minmax(0,0.38fr)_minmax(0,0.34fr)] items-center gap-3 rounded-[1.5rem] border border-transparent bg-[#0d0f10] px-4 py-3.5 transition hover:border-[#dce85d]/15 hover:bg-[#121416]"
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
                      {row.creator.display_name} / {row.strategy_type}
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
                  <span className="font-mono text-xl font-bold text-neutral-50">{row.drift.score}</span>
                  <span className="text-xs text-neutral-500">{row.drift.status}</span>
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
              {loading ? "Loading leaderboard..." : "No active public bots are available."}
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

function HeroMetric({ label, value, copy }: { label: string; value: string; copy: string }) {
  return (
    <article className="grid gap-1 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <span className="label text-neutral-400">{label}</span>
      <div className="mt-2 font-mono text-2xl font-bold uppercase text-neutral-50">{value}</div>
      <p className="text-sm leading-6 text-neutral-400">{copy}</p>
    </article>
  );
}
