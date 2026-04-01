import { toneToClasses, type TrustMetrics } from "@/lib/public-bots";

export function TrustBadgeStrip({ trust }: { trust: TrustMetrics }) {
  return (
    <div className="flex flex-wrap gap-2">
      {trust.badges.map((badge) => (
        <span
          key={`${badge.label}-${badge.detail}`}
          className={`inline-flex items-center rounded-full border px-3 py-1 text-[0.56rem] font-semibold uppercase tracking-[0.16em] ${toneToClasses(badge.tone)}`}
          title={badge.detail}
        >
          {badge.label}
        </span>
      ))}
    </div>
  );
}
