import { driftTone, type DriftMetrics } from "@/lib/public-bots";

function buildBar(score: number) {
  return Math.max(8, Math.min(100, score));
}

export function DriftVisual({ drift }: { drift: DriftMetrics }) {
  return (
    <article className="grid gap-4 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Replay drift</div>
          <div className={`mt-1 font-mono text-2xl font-bold uppercase ${driftTone(drift.status)}`}>{drift.status}</div>
        </div>
        <div className="text-right">
          <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Alignment</div>
          <div className="mt-1 font-mono text-2xl font-bold text-neutral-50">{drift.score}</div>
        </div>
      </div>

      <div className="grid gap-2">
        <div className="h-2 rounded-full bg-[#0d0f10]">
          <div
            className="h-full rounded-full bg-gradient-to-r from-[#ff8a9b] via-[#dce85d] to-[#74b97f]"
            style={{ width: `${buildBar(drift.score)}%` }}
          />
        </div>
        <p className="text-sm leading-7 text-neutral-400">{drift.summary}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3">
          <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Return gap</div>
          <div className="mt-1 font-mono text-lg font-bold text-neutral-50">
            {drift.return_gap_pct === null ? "No replay" : `${drift.return_gap_pct.toFixed(2)}%`}
          </div>
        </div>
        <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3">
          <div className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Drawdown gap</div>
          <div className="mt-1 font-mono text-lg font-bold text-neutral-50">
            {drift.drawdown_gap_pct === null ? "No replay" : `${drift.drawdown_gap_pct.toFixed(2)}%`}
          </div>
        </div>
      </div>
    </article>
  );
}
