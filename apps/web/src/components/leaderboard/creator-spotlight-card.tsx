import Link from "next/link";

import { type CreatorHighlight } from "@/lib/public-bots";

export function CreatorSpotlightCard({ creator }: { creator: CreatorHighlight }) {
  return (
    <article className="grid gap-4 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="grid gap-1">
          <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#74b97f]">
            Creator spotlight
          </span>
          <h3 className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">
            {creator.display_name}
          </h3>
          <p className="text-sm leading-7 text-neutral-400">{creator.headline || creator.summary}</p>
        </div>
        <Link
          href={`/marketplace/creators/${creator.creator_id}`}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
        >
          Open creator
        </Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="Reach" value={`${creator.marketplace_reach_score}`} />
        <Metric label="Followers" value={`${creator.follower_count}`} />
        <Metric label="Public bots" value={`${creator.public_bot_count}`} />
      </div>

      <div className="rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4">
        <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Current spotlight</div>
        <div className="mt-2 flex items-center justify-between gap-3">
          <div>
            <div className="font-mono text-base font-bold uppercase tracking-tight text-neutral-50">
              {creator.spotlight_bot.bot_name}
            </div>
            <div className="text-xs text-neutral-500">
              #{creator.spotlight_bot.rank} / {creator.spotlight_bot.trust_score} trust
            </div>
          </div>
          <div className="text-sm text-neutral-300">
            {creator.spotlight_bot.copy_stats.active_mirror_count} live mirrors
          </div>
        </div>
      </div>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3">
      <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</div>
      <div className="mt-1 font-mono text-xl font-bold text-neutral-50">{value}</div>
    </div>
  );
}
