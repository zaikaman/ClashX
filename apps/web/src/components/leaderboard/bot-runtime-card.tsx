import Link from "next/link";

import { driftTone, type LeaderboardRow, type MarketplaceDiscoveryRow, type MarketplaceOverviewDiscoveryRow } from "@/lib/public-bots";

import { TrustBadgeStrip } from "./trust-badge-strip";

export function BotRuntimeCard({
  row,
  onMirror,
  onClone,
}: {
  row: LeaderboardRow | MarketplaceDiscoveryRow | MarketplaceOverviewDiscoveryRow;
  onMirror?: () => void;
  onClone?: () => void;
}) {
  const isMarketplaceRow = "copy_stats" in row;
  const marketplaceRow = isMarketplaceRow ? row : null;
  const fourthMetricValue = isMarketplaceRow ? `${row.copy_stats.active_mirror_count}` : row.drift.status;
  const fourthMetricAccent = isMarketplaceRow ? "text-[#74b97f]" : driftTone(row.drift.status);

  return (
    <article className="grid gap-5 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 transition-colors duration-200 hover:border-[rgba(255,255,255,0.12)]">
      <div className="flex items-start justify-between gap-4">
        <div className="grid gap-2">
          <div className="flex items-baseline gap-4">
            <span className="font-mono text-3xl font-extrabold text-[#dce85d]">#{row.rank}</span>
            <div className="grid gap-0.5">
              <h3 className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">{row.bot_name}</h3>
              <p className="text-xs text-neutral-500">
                {row.creator.display_name} / {row.strategy_type}
              </p>
            </div>
          </div>
          <TrustBadgeStrip trust={row.trust} />
        </div>
        <Link
          href={`/marketplace/${row.runtime_id}`}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
        >
          Open profile
        </Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Total PnL" value={`${row.pnl_total >= 0 ? "+" : ""}${row.pnl_total.toFixed(2)}`} accent={row.pnl_total >= 0 ? "text-[#74b97f]" : "text-[#ff8a9b]"} />
        <Metric label="Trust" value={`${row.trust.trust_score}`} accent="text-neutral-50" />
        <Metric label="Risk grade" value={row.trust.risk_grade} accent="text-[#dce85d]" />
        <Metric label={marketplaceRow ? "Live mirrors" : "Drift"} value={fourthMetricValue} accent={fourthMetricAccent} />
      </div>

      <div className="grid gap-2 rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4">
        <div className="flex items-center justify-between gap-3 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
          <span>Creator</span>
        <Link href={`/marketplace/creators/${row.creator.creator_id}`} className="text-neutral-300 transition hover:text-[#dce85d]">
            {row.creator.reputation_label}
          </Link>
        </div>
        <p className="text-sm leading-7 text-neutral-400">{row.creator.summary}</p>
        {marketplaceRow?.publishing.hero_headline ? (
          <p className="text-xs uppercase tracking-[0.12em] text-neutral-500">{marketplaceRow.publishing.hero_headline}</p>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onMirror}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
        >
          Follow live
        </button>
        <button
          type="button"
          onClick={onClone}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
        >
          Clone draft
        </button>
      </div>
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
