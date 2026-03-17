type BotRuntimeCardProps = {
  bot: {
    user_id: string;
    display_name: string;
    wallet_address: string;
    rank: number;
    unrealized_pnl: number;
    realized_pnl: number;
    win_streak: number;
  };
  onCopy: () => void;
};

export function TraderCard({ bot, onCopy }: BotRuntimeCardProps) {
  return (
    <article className="grid gap-4 border-l-2 border-[#dce85d] bg-[#16181a] p-5 transition-colors duration-200 hover:bg-neutral-900">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-baseline gap-4">
          <span className="font-mono text-3xl font-extrabold text-[#dce85d]">
            #{bot.rank}
          </span>
          <div className="grid gap-0.5">
            <h3 className="font-mono text-xl font-bold uppercase tracking-tight">
              {bot.display_name}
            </h3>
            <p className="text-xs text-neutral-500 truncate max-w-[180px]">{bot.wallet_address}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onCopy}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.6rem] font-semibold uppercase tracking-wider text-neutral-400 transition-all duration-200 hover:border-[#dce85d] hover:text-[#dce85d]"
        >
          copy bot
        </button>
      </div>
      <div className="flex flex-wrap gap-8">
        <div>
          <div className="label text-[0.58rem]">live pnl</div>
          <div className={`mt-1 font-mono text-2xl font-bold ${bot.unrealized_pnl >= 0 ? "text-[#74b97f]" : "text-[#dce85d]"}`}>
            {bot.unrealized_pnl >= 0 ? "+" : ""}{bot.unrealized_pnl.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="label text-[0.58rem]">realized</div>
          <div className="mt-1 font-mono text-2xl font-bold">
            {bot.realized_pnl >= 0 ? "+" : ""}{bot.realized_pnl.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="label text-[0.58rem]">streak</div>
          <div className="mt-1 font-mono text-2xl font-bold">{bot.win_streak}</div>
        </div>
      </div>
    </article>
  );
}
