"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { BotCloneModal } from "@/components/copy/bot-clone-modal";
import { BotMirrorModal } from "@/components/copy/bot-mirror-modal";

type RuntimeProfile = {
  runtime_id: string;
  bot_definition_id: string;
  bot_name: string;
  description: string;
  strategy_type: string;
  authoring_mode: string;
  status: string;
  mode: string;
  risk_policy_json: Record<string, unknown>;
  rank: number | null;
  pnl_total: number;
  pnl_unrealized: number;
  win_streak: number;
  drawdown: number;
  recent_events: Array<{
    id: string;
    event_type: string;
    decision_summary: string;
    status: string;
    created_at: string;
  }>;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function LeaderboardRuntimePage({ params: paramsPromise }: { params: Promise<{ runtimeId: string }> }) {
  const params = use(paramsPromise);
  const [profile, setProfile] = useState<RuntimeProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [openMirror, setOpenMirror] = useState(false);
  const [openClone, setOpenClone] = useState(false);

  useEffect(() => {
    async function loadProfile() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/bot-copy/leaderboard/${params.runtimeId}`, { cache: "no-store" });
        const payload = (await response.json()) as RuntimeProfile | { detail?: string };
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Could not load runtime profile" : "Could not load runtime profile");
        }
        setProfile(payload as RuntimeProfile);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load runtime profile");
      } finally {
        setLoading(false);
      }
    }

    void loadProfile();
  }, [params.runtimeId]);

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      {error ? (
        <article className="rounded-2xl border border-[#dce85d]/30 bg-[#dce85d]/10 px-5 py-4 text-sm text-neutral-50">
          {error}
        </article>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <article className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <span className="label text-[#dce85d]">Bot profile</span>
          <h2 className="font-mono text-3xl font-bold uppercase tracking-tight text-neutral-50">
            {profile?.bot_name ?? "Loading bot"}
          </h2>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            {profile?.description ?? "Loading the public runtime profile and recent execution context."}
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Rank</div>
              <div className="mt-1 font-mono text-xl font-bold uppercase text-neutral-50">
                #{profile?.rank ?? "-"}
              </div>
            </div>
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Build flow</div>
              <div className="mt-1 text-sm font-semibold text-neutral-50">Builder</div>
            </div>
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Strategy type</div>
              <div className="mt-1 text-sm font-semibold text-neutral-50">{profile?.strategy_type ?? "--"}</div>
            </div>
          </div>
        </article>

        <article className="grid gap-4 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
          <div className="flex items-center justify-between gap-3">
            <span className="label text-[#74b97f]">Performance snapshot</span>
            <Link
              href="/leaderboard"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-neutral-50 hover:text-neutral-50"
            >
              Back to board
            </Link>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Total PnL</div>
              <div className={`mt-1 font-mono text-2xl font-bold ${profile && profile.pnl_total >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}`}>
                {profile ? `${profile.pnl_total >= 0 ? "+" : ""}${profile.pnl_total.toFixed(2)}` : "--"}
              </div>
            </div>
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Live PnL</div>
              <div className={`mt-1 font-mono text-2xl font-bold ${profile && profile.pnl_unrealized >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}`}>
                {profile ? `${profile.pnl_unrealized >= 0 ? "+" : ""}${profile.pnl_unrealized.toFixed(2)}` : "--"}
              </div>
            </div>
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Win streak</div>
              <div className="mt-1 font-mono text-2xl font-bold text-neutral-50">
                {profile?.win_streak ?? "--"}
              </div>
            </div>
            <div className="rounded-xl bg-[#090a0a] px-4 py-3">
              <div className="label text-[0.6rem]">Drawdown</div>
              <div className="mt-1 font-mono text-2xl font-bold text-neutral-50">
                {profile ? `${profile.drawdown.toFixed(2)}%` : "--"}
              </div>
            </div>
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
      </section>

      <section className="grid gap-3">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Recent runtime events</span>
        {(profile?.recent_events ?? []).length > 0 ? (
          profile?.recent_events.map((event, index) => (
            <article
              key={event.id}
              className="stagger-in grid gap-2 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-4 py-4 md:grid-cols-[0.8fr_1fr_0.5fr_1fr] md:items-center"
              style={{ animationDelay: `${index * 25}ms` }}
            >
              <div className="font-mono text-base font-bold uppercase tracking-tight text-neutral-50">
                {event.event_type}
              </div>
              <div className="text-sm text-neutral-400">{event.decision_summary}</div>
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-neutral-400">
                {event.status}
              </div>
              <div className="text-xs text-neutral-500">{new Date(event.created_at).toLocaleString()}</div>
            </article>
          ))
        ) : (
          <article className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-5 py-6 text-sm text-neutral-400">
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
