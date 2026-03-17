import Link from "next/link";

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
};

export function BotRuntimeCard({
  row,
  onMirror,
  onClone,
}: {
  row: BotLeaderboardRow;
  onMirror?: () => void;
  onClone?: () => void;
}) {
  return (
    <article className="grid gap-4 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 transition-colors duration-200 hover:border-[rgba(255,255,255,0.12)] hover:bg-neutral-900">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-baseline gap-4">
          <span className="font-mono text-3xl font-extrabold text-[#dce85d]">#{row.rank}</span>
          <div className="grid gap-0.5">
            <h3 className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">
              {row.bot_name}
            </h3>
            <p className="text-xs text-neutral-500">
              Builder / {row.strategy_type}
            </p>
          </div>
        </div>
        <Link
          href={`/leaderboard/${row.runtime_id}`}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f]"
        >
          Open profile
        </Link>
      </div>

      <div className="flex flex-wrap gap-8">
        <div>
          <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Total PnL</div>
          <div className={`mt-1 font-mono text-2xl font-bold ${row.pnl_total >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}`}>
            {row.pnl_total >= 0 ? "+" : ""}
            {row.pnl_total.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Live PnL</div>
          <div className={`mt-1 font-mono text-2xl font-bold ${row.pnl_unrealized >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}`}>
            {row.pnl_unrealized >= 0 ? "+" : ""}
            {row.pnl_unrealized.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Streak</div>
          <div className="mt-1 font-mono text-2xl font-bold text-neutral-50">{row.win_streak}</div>
        </div>
        <div>
          <div className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Drawdown</div>
          <div className="mt-1 font-mono text-2xl font-bold text-neutral-400">
            {row.drawdown.toFixed(2)}%
          </div>
        </div>
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
