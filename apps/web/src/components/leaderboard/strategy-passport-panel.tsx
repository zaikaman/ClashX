import type { StrategyPassport } from "@/lib/public-bots";

export function StrategyPassportPanel({ passport }: { passport: StrategyPassport }) {
  return (
    <article className="grid gap-5 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Strategy passport</div>
          <h3 className="mt-2 font-mono text-2xl font-bold uppercase tracking-[-0.03em] text-neutral-50">
            Version trail
          </h3>
        </div>
        <div className="rounded-full border border-[#dce85d]/20 bg-[#dce85d]/10 px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#ecf4a8]">
          v{passport.current_version}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <PassportMetric label="Market scope" value={passport.market_scope} />
        <PassportMetric label="Build flow" value={passport.authoring_mode} />
        <PassportMetric label="Release count" value={`${passport.release_count}`} />
        <PassportMetric label="Rules schema" value={`v${passport.rules_version}`} />
      </div>

      <div className="grid gap-2">
        {passport.version_history.length > 0 ? (
          passport.version_history.map((version) => (
            <div
              key={version.id}
              className="grid gap-2 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3 md:grid-cols-[0.22fr_0.28fr_0.5fr] md:items-center"
            >
              <div className="font-mono text-base font-bold text-neutral-50">{version.label}</div>
              <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
                {version.change_kind.replaceAll("_", " ")}
                {version.is_public_release ? " / public" : ""}
              </div>
              <div className="text-sm text-neutral-400">{new Date(version.created_at).toLocaleString()}</div>
            </div>
          ))
        ) : (
          <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4 text-sm text-neutral-400">
            No version history is available yet.
          </div>
        )}
      </div>
    </article>
  );
}

function PassportMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3">
      <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">{label}</div>
      <div className="mt-1 text-sm font-semibold text-neutral-50">{value}</div>
    </div>
  );
}
