export type BotPosition = {
  symbol: string;
  side: string;
  amount: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
};

export type BotPerformance = {
  pnl_total: number;
  pnl_total_pct: number;
  pnl_realized: number;
  pnl_unrealized: number;
  win_streak: number;
  positions: BotPosition[];
};
