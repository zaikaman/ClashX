export type TradingMarket = {
  symbol: string;
  display_symbol: string;
  mark_price: number;
  oracle_price?: number;
  volume_24h?: number;
  funding_rate: number;
  updated_at?: string;
  open_interest?: number;
  min_order_size?: number;
};
