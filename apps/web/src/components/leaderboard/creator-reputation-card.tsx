import Link from "next/link";

import type {
  CreatorHighlight,
  CreatorProfile,
  CreatorSummary,
  MarketplaceCreatorProfile,
} from "@/lib/public-bots";

type CreatorProps = {
  creator: CreatorSummary | CreatorProfile | MarketplaceCreatorProfile | CreatorHighlight;
  showBots?: boolean;
};

export function CreatorReputationCard({ creator, showBots = false }: CreatorProps) {
  const bots = "bots" in creator ? creator.bots : [];
  const followerCount = "follower_count" in creator ? creator.follower_count : 0;
  const reachScore = "marketplace_reach_score" in creator ? creator.marketplace_reach_score : creator.reputation_score;
  const headline = "headline" in creator ? creator.headline : creator.summary;

  return (
    <article className="grid gap-5 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="grid gap-2">
          <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Creator reputation</div>
          <div>
            <h3 className="font-mono text-2xl font-bold uppercase tracking-[-0.03em] text-neutral-50">{creator.display_name}</h3>
            <p className="mt-2 max-w-2xl text-sm leading-7 text-neutral-400">{headline}</p>
          </div>
        </div>
        <Link
          href={`/marketplace/creators/${creator.creator_id}`}
          className="rounded-full border border-white/10 px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f]"
        >
          Open creator
        </Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Reach" value={`${reachScore}`} accent="text-[#dce85d]" />
        <Metric label="Trust avg" value={`${creator.average_trust_score}`} accent="text-[#74b97f]" />
        <Metric label="Followers" value={`${followerCount || creator.active_mirror_count}`} accent="text-neutral-50" />
        <Metric label="Published bots" value={`${creator.public_bot_count}`} accent="text-neutral-50" />
      </div>

      <div className="flex flex-wrap gap-2">
        {creator.tags.map((tag) => (
          <span
            key={tag}
            className="rounded-full border border-[rgba(255,255,255,0.1)] bg-[#0d0f10] px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] text-neutral-300"
          >
            {tag}
          </span>
        ))}
      </div>

      {showBots ? (
        <div className="grid gap-2">
          {bots.length > 0 ? (
            bots.map((bot) => (
              <Link
                key={bot.runtime_id}
                href={`/marketplace/${bot.runtime_id}`}
                className="grid gap-2 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3 transition hover:border-[#dce85d]/20 hover:bg-[#111315] md:grid-cols-[1fr_0.3fr_0.3fr_0.3fr] md:items-center"
              >
                <div>
                  <div className="font-mono text-base font-bold uppercase tracking-tight text-neutral-50">{bot.bot_name}</div>
                  <div className="text-xs text-neutral-500">{bot.strategy_type}</div>
                </div>
                <div className="text-sm font-semibold text-neutral-50">{bot.rank ? `#${bot.rank}` : "Unranked"}</div>
                <div className="text-sm font-semibold text-[#74b97f]">
                  {"trust" in bot ? `${bot.trust.trust_score} trust` : `${bot.trust_score} trust`}
                </div>
                <div className="text-sm text-neutral-400">
                  {"drift" in bot ? bot.drift.status : bot.drift_status}
                </div>
              </Link>
            ))
          ) : (
            <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4 text-sm text-neutral-400">
              No public strategies are available on this creator profile yet.
            </div>
          )}
        </div>
      ) : null}
    </article>
  );
}

function Metric({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3">
      <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">{label}</div>
      <div className={`mt-1 font-mono text-xl font-bold ${accent}`}>{value}</div>
    </div>
  );
}
