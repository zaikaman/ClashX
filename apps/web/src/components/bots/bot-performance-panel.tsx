"use client";

import type { BotPerformance } from "@/lib/bot-performance";

function formatSigned(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function tone(value: number) {
  return value >= 0 ? "text-[#74b97f]" : "text-[#dce85d]";
}

export function BotPerformancePanel({ performance }: { performance: BotPerformance | null }) {
  if (!performance) {
    return (
      <article className="grid gap-3 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
        <span className="label text-[#dce85d]">Performance snapshot</span>
        <h3 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">No runtime PnL yet</h3>
        <p className="max-w-3xl text-sm leading-7 text-neutral-400">
          Deploy this bot to start tracking realized trades, live exposure, and current positions.
        </p>
      </article>
    );
  }

  return (
    <article className="grid gap-5 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
      <div className="flex items-center justify-between gap-3">
        <div className="grid gap-1">
          <span className="label text-[#74b97f]">Performance snapshot</span>
          <h3 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">How this bot is performing</h3>
        </div>
        <span className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
          {performance.positions.length} open {performance.positions.length === 1 ? "position" : "positions"}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl bg-[#090a0a] px-4 py-3">
          <div className="label text-[0.6rem]">Net PnL</div>
          <div className={`mt-1 font-mono text-2xl font-bold ${tone(performance.pnl_total)}`}>{formatSigned(performance.pnl_total)}</div>
        </div>
        <div className="rounded-xl bg-[#090a0a] px-4 py-3">
          <div className="label text-[0.6rem]">Realized</div>
          <div className={`mt-1 font-mono text-2xl font-bold ${tone(performance.pnl_realized)}`}>{formatSigned(performance.pnl_realized)}</div>
        </div>
        <div className="rounded-xl bg-[#090a0a] px-4 py-3">
          <div className="label text-[0.6rem]">Live PnL</div>
          <div className={`mt-1 font-mono text-2xl font-bold ${tone(performance.pnl_unrealized)}`}>{formatSigned(performance.pnl_unrealized)}</div>
        </div>
        <div className="rounded-xl bg-[#090a0a] px-4 py-3">
          <div className="label text-[0.6rem]">Win streak</div>
          <div className="mt-1 font-mono text-2xl font-bold text-neutral-50">{performance.win_streak}</div>
        </div>
      </div>

      <div className="grid gap-2">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Open positions</span>
          <span className="text-xs text-neutral-500">Live mark-to-market exposure</span>
        </div>
        {performance.positions.length > 0 ? (
          performance.positions.map((position) => (
            <div
              key={`${position.symbol}-${position.side}`}
              className="grid gap-2 rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#101214] px-4 py-4 md:grid-cols-[minmax(0,0.9fr)_minmax(0,0.8fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] md:items-center"
            >
              <div>
                <div className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">{position.symbol}</div>
                <div className="text-xs uppercase tracking-[0.16em] text-neutral-500">{position.side}</div>
              </div>
              <div className="text-sm text-neutral-300">{position.amount.toFixed(4)} size</div>
              <div className="text-sm text-neutral-400">Entry {position.entry_price.toFixed(2)}</div>
              <div className="text-sm text-neutral-400">Mark {position.mark_price.toFixed(2)}</div>
              <div className={`font-mono text-sm font-bold ${tone(position.unrealized_pnl)}`}>{formatSigned(position.unrealized_pnl)}</div>
            </div>
          ))
        ) : (
          <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#101214] px-4 py-4 text-sm text-neutral-400">
            No open positions right now. This runtime is flat at the moment.
          </div>
        )}
      </div>
    </article>
  );
}
