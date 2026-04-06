import Link from "next/link";

import { type FeaturedShelf, type MarketplaceOverviewFeaturedShelf } from "@/lib/public-bots";

import { TrustBadgeStrip } from "./trust-badge-strip";

export function FeaturedBotShelf({
  shelf,
  onMirror,
  onClone,
}: {
  shelf: FeaturedShelf | MarketplaceOverviewFeaturedShelf;
  onMirror?: (runtimeId: string) => void;
  onClone?: (runtimeId: string) => void;
}) {
  return (
    <section className="grid gap-4 rounded-[1.9rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="grid gap-1">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d]">
            Featured shelf
          </span>
          <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">{shelf.title}</h2>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">{shelf.subtitle}</p>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {shelf.bots.map((bot) => (
          <article
            key={`${shelf.collection_key}-${bot.runtime_id}`}
            className="grid gap-4 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="grid gap-1">
                <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">
                  #{bot.rank} / {bot.strategy_type}
                </span>
                <Link
                  href={`/leaderboard/${bot.runtime_id}`}
                  className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50 transition hover:text-[#dce85d]"
                >
                  {bot.bot_name}
                </Link>
                <span className="text-xs text-neutral-500">{bot.creator.display_name}</span>
              </div>
              <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
                {bot.publishing.visibility}
              </span>
            </div>

            <TrustBadgeStrip trust={bot.trust} />

            <div className="grid gap-3 sm:grid-cols-3">
              <Metric label="Trust" value={`${bot.trust.trust_score}`} accent="text-neutral-50" />
              <Metric label="Live mirrors" value={`${bot.copy_stats.active_mirror_count}`} accent="text-[#dce85d]" />
              <Metric label="Clones" value={`${bot.copy_stats.clone_count}`} accent="text-[#74b97f]" />
            </div>

            {onMirror || onClone ? (
              <div className="flex flex-wrap gap-2">
                {onMirror ? (
                  <button
                    type="button"
                    onClick={() => onMirror(bot.runtime_id)}
                    className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
                  >
                    Follow live
                  </button>
                ) : null}
                {onClone ? (
                  <button
                    type="button"
                    onClick={() => onClone(bot.runtime_id)}
                    className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
                  >
                    Clone draft
                  </button>
                ) : null}
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function Metric({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#121416] px-4 py-3">
      <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</div>
      <div className={`mt-1 font-mono text-xl font-bold ${accent}`}>{value}</div>
    </div>
  );
}
