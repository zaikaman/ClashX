import { MarkerType, type Edge, type Node, type XYPosition } from "@xyflow/react";

export type VisualCondition = {
  id: string;
  type: string;
  symbol: string;
  value?: number;
  side?: "long" | "short";
  seconds?: number;
  timeframe?: string;
  secondary_timeframe?: string;
  period?: number;
  fast_period?: number;
  slow_period?: number;
  signal_period?: number;
};

export type VisualAction = {
  id: string;
  type: string;
  symbol: string;
  side?: "long" | "short";
  size_usd?: number;
  quantity?: number;
  leverage?: number;
  take_profit_pct?: number;
  stop_loss_pct?: number;
  price?: number;
  duration_seconds?: number;
  slippage_percent?: number;
  tif?: string;
  client_order_id?: string;
  order_id?: string;
  reduce_only?: boolean;
  all_symbols?: boolean;
  exclude_reduce_only?: boolean;
};

export type EntryNodeData = {
  kind: "entry";
  active: boolean;
  primary: boolean;
  branchCount: number;
  stageLabel?: string;
  issueCount?: number;
};

export type ConditionNodeData = {
  kind: "condition";
  condition: VisualCondition;
  active: boolean;
  primary: boolean;
  branchCount: number;
  stageLabel?: string;
  issueCount?: number;
};

export type ActionNodeData = {
  kind: "action";
  action: VisualAction;
  active: boolean;
  primary: boolean;
  branchCount: number;
  stageLabel?: string;
  issueCount?: number;
};

export type BuilderNodeData = EntryNodeData | ConditionNodeData | ActionNodeData;
export type BuilderFlowNode = Node<BuilderNodeData, "builderNode">;
export type BuilderFlowEdge = Edge;

export type PaletteDragPayload = {
  kind: "condition" | "action";
  blockType: string;
};

export type BuilderGraphData = {
  nodes: BuilderFlowNode[];
  edges: BuilderFlowEdge[];
};

export type BuilderAiRoute = {
  name?: string;
  conditions: Array<Partial<VisualCondition> & { type: string }>;
  actions: Array<Partial<VisualAction> & { type: string }>;
};

export type BuilderAiDraft = {
  name: string;
  description: string;
  marketSelection: "selected" | "all";
  markets: string[];
  conditions: Array<Partial<VisualCondition> & { type: string }>;
  actions: Array<Partial<VisualAction> & { type: string }>;
  routes?: BuilderAiRoute[];
};

export type BuilderStarterTemplate = {
  id: string;
  name: string;
  description: string;
  marketScope: string;
  setupLabel: string;
  riskProfile: string;
  conditionCount: number;
  actionCount: number;
  buildGraph: () => BuilderGraphData;
};

export const ENTRY_NODE_ID = "builder-entry";
export const PALETTE_MIME = "application/clashx-builder";
export const DEFAULT_BUILDER_TEMPLATE_ID = "momentum-breakout-v1";
export const BLANK_BUILDER_TEMPLATE_ID = "blank-builder-draft";
export const BOT_MARKET_UNIVERSE_SYMBOL = "__BOT_MARKET_UNIVERSE__";

export const CONDITION_OPTIONS = [
  "price_above",
  "price_below",
  "price_change_pct_above",
  "price_change_pct_below",
  "has_position",
  "position_side_is",
  "cooldown_elapsed",
  "funding_rate_above",
  "funding_rate_below",
  "volume_above",
  "volume_below",
  "rsi_above",
  "rsi_below",
  "sma_above",
  "sma_below",
  "volatility_above",
  "volatility_below",
  "bollinger_above_upper",
  "bollinger_below_lower",
  "breakout_above_recent_high",
  "breakout_below_recent_low",
  "atr_above",
  "atr_below",
  "vwap_above",
  "vwap_below",
  "higher_timeframe_sma_above",
  "higher_timeframe_sma_below",
  "ema_crosses_above",
  "ema_crosses_below",
  "macd_crosses_above_signal",
  "macd_crosses_below_signal",
  "position_pnl_above",
  "position_pnl_below",
  "position_pnl_pct_above",
  "position_pnl_pct_below",
  "position_in_profit",
  "position_in_loss",
] as const;

export const ACTION_OPTIONS = [
  "open_long",
  "open_short",
  "place_market_order",
  "place_limit_order",
  "place_twap_order",
  "close_position",
  "set_tpsl",
  "update_leverage",
  "cancel_order",
  "cancel_twap_order",
  "cancel_all_orders",
] as const;

export const CONDITION_COPY: Record<string, { label: string; helper: string }> = {
  price_above: { label: "Price above", helper: "Trigger when price rises through a chosen level." },
  price_below: { label: "Price below", helper: "Trigger when price falls through a chosen level." },
  price_change_pct_above: { label: "Price change up", helper: "Trigger when price has gained more than a chosen percent over a lookback window." },
  price_change_pct_below: { label: "Price change down", helper: "Trigger when price has lost more than a chosen percent over a lookback window." },
  has_position: { label: "Has position", helper: "Only continue if the bot already has a live position." },
  position_side_is: { label: "Position side", helper: "Check whether the open position is long or short." },
  cooldown_elapsed: { label: "Cooldown elapsed", helper: "Wait before letting the bot act again." },
  funding_rate_above: { label: "Funding above", helper: "Gate entries when funding is rich enough to confirm one-sided positioning." },
  funding_rate_below: { label: "Funding below", helper: "Gate entries when funding is sufficiently negative or compressed." },
  volume_above: { label: "Volume above", helper: "Require 24h market participation to clear a chosen liquidity threshold." },
  volume_below: { label: "Volume below", helper: "Trade only when the market stays under a chosen 24h volume ceiling." },
  rsi_above: { label: "RSI above", helper: "Trigger when momentum overheats beyond an RSI threshold." },
  rsi_below: { label: "RSI below", helper: "Trigger when momentum dips beneath an RSI threshold." },
  sma_above: { label: "Above SMA", helper: "Require the latest close to stay above a simple moving average." },
  sma_below: { label: "Below SMA", helper: "Require the latest close to stay below a simple moving average." },
  volatility_above: { label: "Volatility above", helper: "Only act when recent realized volatility expands beyond a threshold." },
  volatility_below: { label: "Volatility below", helper: "Only act when recent realized volatility compresses below a threshold." },
  bollinger_above_upper: { label: "Bollinger upper break", helper: "Trigger when price closes above the upper Bollinger band." },
  bollinger_below_lower: { label: "Bollinger lower break", helper: "Trigger when price closes below the lower Bollinger band." },
  breakout_above_recent_high: { label: "Breaks recent high", helper: "Require price to clear the highest high from a recent lookback window." },
  breakout_below_recent_low: { label: "Breaks recent low", helper: "Require price to break below the lowest low from a recent lookback window." },
  atr_above: { label: "ATR above", helper: "Only act when average true range as a percent of price expands beyond a threshold." },
  atr_below: { label: "ATR below", helper: "Only act when average true range as a percent of price stays below a threshold." },
  vwap_above: { label: "Above VWAP", helper: "Require the latest close to stay above rolling VWAP." },
  vwap_below: { label: "Below VWAP", helper: "Require the latest close to stay below rolling VWAP." },
  higher_timeframe_sma_above: { label: "HTF SMA long", helper: "Confirm the lower timeframe setup with higher timeframe trend strength." },
  higher_timeframe_sma_below: { label: "HTF SMA short", helper: "Confirm the lower timeframe setup with higher timeframe trend weakness." },
  ema_crosses_above: { label: "EMA cross up", helper: "Detect a fast EMA crossing above a slower trend EMA." },
  ema_crosses_below: { label: "EMA cross down", helper: "Detect a fast EMA crossing below a slower trend EMA." },
  macd_crosses_above_signal: { label: "MACD cross up", helper: "Trigger when MACD crosses above its signal line." },
  macd_crosses_below_signal: { label: "MACD cross down", helper: "Trigger when MACD crosses below its signal line." },
  position_pnl_above: { label: "PnL above", helper: "Continue only when unrealized PnL is above a chosen USD threshold." },
  position_pnl_below: { label: "PnL below", helper: "Continue only when unrealized PnL is below a chosen USD threshold." },
  position_pnl_pct_above: { label: "PnL % above", helper: "Continue only when unrealized PnL on margin is above a chosen percent." },
  position_pnl_pct_below: { label: "PnL % below", helper: "Continue only when unrealized PnL on margin is below a chosen percent." },
  position_in_profit: { label: "Position in profit", helper: "Check whether the open position is currently green." },
  position_in_loss: { label: "Position in loss", helper: "Check whether the open position is currently red." },
};

export const ACTION_COPY: Record<string, { label: string; helper: string }> = {
  open_long: { label: "Open long", helper: "Enter a long position using the live runtime leverage and sizing policy." },
  open_short: { label: "Open short", helper: "Enter a short position using the live runtime leverage and sizing policy." },
  place_market_order: { label: "Market order", helper: "Send a custom market order. Live entries inherit runtime leverage and sizing, while reduce-only exits can set their own amount." },
  place_limit_order: { label: "Limit order", helper: "Work an entry or exit at a specific price. Live entries inherit runtime leverage and sizing, while reduce-only exits can set their own amount." },
  place_twap_order: { label: "TWAP execution", helper: "Drip into the market over time. Live entries inherit runtime leverage and sizing, while reduce-only exits can set their own amount." },
  close_position: { label: "Close position", helper: "Exit the current market position." },
  set_tpsl: { label: "Set TP / SL", helper: "Add take profit and stop loss levels." },
  update_leverage: { label: "Update leverage", helper: "Change leverage on an existing position." },
  cancel_order: { label: "Cancel order", helper: "Cancel a specific resting order by ID or client order ID." },
  cancel_twap_order: { label: "Cancel TWAP", helper: "Stop a running TWAP execution before it completes." },
  cancel_all_orders: { label: "Cancel all orders", helper: "Clear resting orders on one market or across the account." },
};

let blockCounter = 0;
let edgeCounter = 0;

function nextBlockId(prefix: string) {
  blockCounter += 1;
  return `${prefix}-${blockCounter}`;
}

function nextEdgeId() {
  edgeCounter += 1;
  return `edge-${edgeCounter}`;
}

export function createCondition(type: (typeof CONDITION_OPTIONS)[number] = "price_above"): VisualCondition {
  if (type === "cooldown_elapsed") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", seconds: 60 };
  }
  if (type === "funding_rate_above") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", value: 0.01 };
  }
  if (type === "funding_rate_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", value: -0.01 };
  }
  if (type === "volume_above") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", value: 100000000 };
  }
  if (type === "volume_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", value: 25000000 };
  }
  if (type === "price_change_pct_above") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 5, value: 1.2 };
  }
  if (type === "price_change_pct_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 5, value: -1.2 };
  }
  if (type === "rsi_above") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 14, value: 70 };
  }
  if (type === "rsi_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 14, value: 30 };
  }
  if (type === "sma_above") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 20 };
  }
  if (type === "sma_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 20 };
  }
  if (type === "volatility_above") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 20, value: 1.5 };
  }
  if (type === "volatility_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 20, value: 0.7 };
  }
  if (type === "bollinger_above_upper" || type === "bollinger_below_lower") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 20, value: 2 };
  }
  if (type === "breakout_above_recent_high" || type === "breakout_below_recent_low") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 20 };
  }
  if (type === "atr_above") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 14, value: 1.1 };
  }
  if (type === "atr_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 14, value: 0.6 };
  }
  if (type === "vwap_above" || type === "vwap_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", period: 24 };
  }
  if (type === "higher_timeframe_sma_above" || type === "higher_timeframe_sma_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", secondary_timeframe: "1h", period: 20 };
  }
  if (type === "ema_crosses_above" || type === "ema_crosses_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "15m", fast_period: 9, slow_period: 21 };
  }
  if (type === "macd_crosses_above_signal" || type === "macd_crosses_below_signal") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", timeframe: "1h", fast_period: 12, slow_period: 26, signal_period: 9 };
  }
  if (type === "position_side_is") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", side: "long" };
  }
  if (type === "has_position") {
    return { id: nextBlockId("condition"), type, symbol: "BTC" };
  }
  if (type === "position_pnl_above") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", value: 75 };
  }
  if (type === "position_pnl_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", value: -75 };
  }
  if (type === "position_pnl_pct_above") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", value: 8 };
  }
  if (type === "position_pnl_pct_below") {
    return { id: nextBlockId("condition"), type, symbol: "BTC", value: -5 };
  }
  if (type === "position_in_profit" || type === "position_in_loss") {
    return { id: nextBlockId("condition"), type, symbol: "BTC" };
  }
  return { id: nextBlockId("condition"), type, symbol: "BTC", value: 100000 };
}

export function createAction(type: (typeof ACTION_OPTIONS)[number] = "open_long"): VisualAction {
  if (type === "set_tpsl") {
    return { id: nextBlockId("action"), type, symbol: "BTC", take_profit_pct: 1.8, stop_loss_pct: 0.9 };
  }
  if (type === "update_leverage") {
    return { id: nextBlockId("action"), type, symbol: "BTC", leverage: 3 };
  }
  if (type === "close_position") {
    return { id: nextBlockId("action"), type, symbol: "BTC" };
  }
  if (type === "place_market_order") {
    return {
      id: nextBlockId("action"),
      type,
      symbol: "BTC",
      side: "long",
      size_usd: 180,
      leverage: 3,
      slippage_percent: 0.25,
      reduce_only: false,
    };
  }
  if (type === "place_limit_order") {
    return {
      id: nextBlockId("action"),
      type,
      symbol: "BTC",
      side: "long",
      quantity: 0.01,
      leverage: 3,
      price: 99500,
      tif: "GTC",
      reduce_only: false,
      client_order_id: `limit-${blockCounter + 1}`,
    };
  }
  if (type === "place_twap_order") {
    return {
      id: nextBlockId("action"),
      type,
      symbol: "BTC",
      side: "long",
      quantity: 0.03,
      leverage: 3,
      duration_seconds: 900,
      slippage_percent: 0.35,
      reduce_only: false,
      client_order_id: `twap-${blockCounter + 1}`,
    };
  }
  if (type === "cancel_order") {
    return {
      id: nextBlockId("action"),
      type,
      symbol: "BTC",
      order_id: "order-001",
      client_order_id: "maker-entry-001",
    };
  }
  if (type === "cancel_twap_order") {
    return {
      id: nextBlockId("action"),
      type,
      symbol: "BTC",
      order_id: "twap-001",
      client_order_id: "twap-entry-001",
    };
  }
  if (type === "cancel_all_orders") {
    return {
      id: nextBlockId("action"),
      type,
      symbol: "BTC",
      all_symbols: false,
      exclude_reduce_only: true,
    };
  }
  return { id: nextBlockId("action"), type, symbol: "BTC", size_usd: 150, leverage: 3 };
}

export function createEntryNode(): BuilderFlowNode {
  return {
    id: ENTRY_NODE_ID,
    type: "builderNode",
    position: { x: 80, y: 220 },
    data: {
      kind: "entry",
      active: false,
      primary: true,
      branchCount: 0,
    },
    draggable: false,
    deletable: false,
    selectable: false,
  };
}

export function createConditionNode(condition: VisualCondition, position: XYPosition): BuilderFlowNode {
  return {
    id: condition.id,
    type: "builderNode",
    position,
    data: {
      kind: "condition",
      condition,
      active: false,
      primary: false,
      branchCount: 0,
    },
  };
}

export function createActionNode(action: VisualAction, position: XYPosition): BuilderFlowNode {
  return {
    id: action.id,
    type: "builderNode",
    position,
    data: {
      kind: "action",
      action,
      active: false,
      primary: false,
      branchCount: 0,
    },
  };
}

export function createCanvasEdge(source: string, target: string): BuilderFlowEdge {
  return {
    id: nextEdgeId(),
    source,
    target,
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed },
  };
}

export function snapPosition(position: XYPosition): XYPosition {
  return {
    x: Math.round(position.x / 24) * 24,
    y: Math.round(position.y / 24) * 24,
  };
}

export function parseOptionalNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function formatMarketReference(symbol: string) {
  return symbol === BOT_MARKET_UNIVERSE_SYMBOL ? "selected markets" : symbol || "Market";
}

export function shortWallet(value: string) {
  return value ? `${value.slice(0, 6)}...${value.slice(-4)}` : "No wallet";
}

export function conditionTitle(type: string) {
  return CONDITION_COPY[type]?.label ?? type;
}

export function actionTitle(type: string) {
  return ACTION_COPY[type]?.label ?? type;
}

export function conditionHelper(type: string) {
  return CONDITION_COPY[type]?.helper ?? "Adjust the trigger details for this condition.";
}

export function actionHelper(type: string) {
  return ACTION_COPY[type]?.helper ?? "Adjust the behavior for this action.";
}

export function conditionSummary(condition: VisualCondition) {
  const marketLabel = formatMarketReference(condition.symbol);
  if (condition.type === "price_above") {
    return `${marketLabel} move above ${condition.value ?? 0}.`;
  }
  if (condition.type === "price_below") {
    return `${marketLabel} move below ${condition.value ?? 0}.`;
  }
  if (condition.type === "price_change_pct_above") {
    return `${marketLabel} ${condition.timeframe ?? "15m"} change over ${condition.period ?? 5} bars rises above ${condition.value ?? 0}%.`;
  }
  if (condition.type === "price_change_pct_below") {
    return `${marketLabel} ${condition.timeframe ?? "15m"} change over ${condition.period ?? 5} bars falls below ${condition.value ?? 0}%.`;
  }
  if (condition.type === "has_position") {
    return `${marketLabel} already have an open position.`;
  }
  if (condition.type === "position_side_is") {
    return `${marketLabel} position is ${condition.side ?? "long"}.`;
  }
  if (condition.type === "funding_rate_above") {
    return `${marketLabel} funding rises above ${condition.value ?? 0}.`;
  }
  if (condition.type === "funding_rate_below") {
    return `${marketLabel} funding falls below ${condition.value ?? 0}.`;
  }
  if (condition.type === "volume_above") {
    return `${marketLabel} 24h volume rises above ${condition.value ?? 0}.`;
  }
  if (condition.type === "volume_below") {
    return `${marketLabel} 24h volume falls below ${condition.value ?? 0}.`;
  }
  if (condition.type === "rsi_above") {
    return `${marketLabel} ${condition.timeframe ?? "15m"} RSI(${condition.period ?? 14}) rises above ${condition.value ?? 70}.`;
  }
  if (condition.type === "rsi_below") {
    return `${marketLabel} ${condition.timeframe ?? "15m"} RSI(${condition.period ?? 14}) falls below ${condition.value ?? 30}.`;
  }
  if (condition.type === "sma_above") {
    return `${marketLabel} ${condition.timeframe ?? "15m"} close stays above SMA(${condition.period ?? 20}).`;
  }
  if (condition.type === "sma_below") {
    return `${marketLabel} ${condition.timeframe ?? "15m"} close stays below SMA(${condition.period ?? 20}).`;
  }
  if (condition.type === "volatility_above") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} realized volatility rises above ${condition.value ?? 0}% over ${condition.period ?? 20} bars.`;
  }
  if (condition.type === "volatility_below") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} realized volatility falls below ${condition.value ?? 0}% over ${condition.period ?? 20} bars.`;
  }
  if (condition.type === "bollinger_above_upper") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} closes above the upper Bollinger band using ${condition.period ?? 20} bars and ${condition.value ?? 2} standard deviations.`;
  }
  if (condition.type === "bollinger_below_lower") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} closes below the lower Bollinger band using ${condition.period ?? 20} bars and ${condition.value ?? 2} standard deviations.`;
  }
  if (condition.type === "breakout_above_recent_high") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} closes above the highest high from the last ${condition.period ?? 20} bars.`;
  }
  if (condition.type === "breakout_below_recent_low") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} closes below the lowest low from the last ${condition.period ?? 20} bars.`;
  }
  if (condition.type === "atr_above") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} ATR rises above ${condition.value ?? 0}% of price over ${condition.period ?? 14} bars.`;
  }
  if (condition.type === "atr_below") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} ATR falls below ${condition.value ?? 0}% of price over ${condition.period ?? 14} bars.`;
  }
  if (condition.type === "vwap_above") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} close stays above rolling VWAP over ${condition.period ?? 24} bars.`;
  }
  if (condition.type === "vwap_below") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} close stays below rolling VWAP over ${condition.period ?? 24} bars.`;
  }
  if (condition.type === "higher_timeframe_sma_above") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} setup is confirmed by a ${condition.secondary_timeframe ?? "1h"} SMA(${condition.period ?? 20}) trend bias to the upside.`;
  }
  if (condition.type === "higher_timeframe_sma_below") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} setup is confirmed by a ${condition.secondary_timeframe ?? "1h"} SMA(${condition.period ?? 20}) trend bias to the downside.`;
  }
  if (condition.type === "ema_crosses_above") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} EMA ${condition.fast_period ?? 9} crosses above EMA ${condition.slow_period ?? 21}.`;
  }
  if (condition.type === "ema_crosses_below") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "15m"} EMA ${condition.fast_period ?? 9} crosses below EMA ${condition.slow_period ?? 21}.`;
  }
  if (condition.type === "macd_crosses_above_signal") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "1h"} MACD crosses above signal (${condition.fast_period ?? 12}/${condition.slow_period ?? 26}/${condition.signal_period ?? 9}).`;
  }
  if (condition.type === "macd_crosses_below_signal") {
    return `${condition.symbol || "Market"} ${condition.timeframe ?? "1h"} MACD crosses below signal (${condition.fast_period ?? 12}/${condition.slow_period ?? 26}/${condition.signal_period ?? 9}).`;
  }
  if (condition.type === "position_pnl_above") {
    return `${condition.symbol || "Market"} unrealized PnL rises above ${condition.value ?? 0} USD.`;
  }
  if (condition.type === "position_pnl_below") {
    return `${condition.symbol || "Market"} unrealized PnL falls below ${condition.value ?? 0} USD.`;
  }
  if (condition.type === "position_pnl_pct_above") {
    return `${condition.symbol || "Market"} unrealized PnL rises above ${condition.value ?? 0}% on margin.`;
  }
  if (condition.type === "position_pnl_pct_below") {
    return `${condition.symbol || "Market"} unrealized PnL falls below ${condition.value ?? 0}% on margin.`;
  }
  if (condition.type === "position_in_profit") {
    return `${condition.symbol || "Market"} has an open position that is currently in profit.`;
  }
  if (condition.type === "position_in_loss") {
    return `${condition.symbol || "Market"} has an open position that is currently in loss.`;
  }
  return `${condition.seconds ?? 0} seconds have passed since the last action on ${marketLabel}.`;
}

export function actionSummary(action: VisualAction) {
  const marketLabel = formatMarketReference(action.symbol);
  const reduceOnlySuffix = action.reduce_only ? " as a reduce-only exit" : "";
  if (action.type === "open_long") {
    return `Open long on ${marketLabel} using the live runtime sizing and leverage policy.`;
  }
  if (action.type === "open_short") {
    return `Open short on ${marketLabel} using the live runtime sizing and leverage policy.`;
  }
  if (action.type === "place_market_order") {
    if (action.reduce_only) {
      return `Send a ${action.side ?? "long"} reduce-only market order on ${marketLabel} for ${action.size_usd ?? 0} USD with ${action.slippage_percent ?? 0}% slippage.`;
    }
    return `Send a ${action.side ?? "long"} market order on ${marketLabel} using the live runtime sizing and leverage policy with ${action.slippage_percent ?? 0}% slippage${reduceOnlySuffix}.`;
  }
  if (action.type === "place_limit_order") {
    if (action.reduce_only) {
      return `Work a ${action.side ?? "long"} reduce-only limit order on ${marketLabel} for ${action.quantity ?? 0} contracts at ${action.price ?? 0} (${action.tif ?? "GTC"}).`;
    }
    return `Work a ${action.side ?? "long"} limit order on ${marketLabel} at ${action.price ?? 0} (${action.tif ?? "GTC"}) using the live runtime sizing and leverage policy${reduceOnlySuffix}.`;
  }
  if (action.type === "place_twap_order") {
    if (action.reduce_only) {
      return `Slice ${action.quantity ?? 0} contracts out of ${marketLabel} over ${action.duration_seconds ?? 0}s on the ${action.side ?? "long"} side as a reduce-only exit.`;
    }
    return `Slice into ${marketLabel} over ${action.duration_seconds ?? 0}s on the ${action.side ?? "long"} side using the live runtime sizing and leverage policy${reduceOnlySuffix}.`;
  }
  if (action.type === "close_position") {
    return `Close the ${marketLabel} position.`;
  }
  if (action.type === "set_tpsl") {
    return `Set TP ${action.take_profit_pct ?? 0}% and SL ${action.stop_loss_pct ?? 0}% on ${marketLabel}.`;
  }
  if (action.type === "update_leverage") {
    return `Update ${marketLabel} leverage to ${action.leverage ?? 0}x.`;
  }
  if (action.type === "cancel_order") {
    return `Cancel the resting order ${action.order_id || action.client_order_id || "for this market"} on ${marketLabel}.`;
  }
  if (action.type === "cancel_twap_order") {
    return `Cancel the TWAP schedule ${action.order_id || action.client_order_id || "for this market"} on ${marketLabel}.`;
  }
  if (action.all_symbols) {
    return `Cancel all resting orders across the account${action.exclude_reduce_only ? ", keeping reduce-only protection intact" : ""}.`;
  }
  return `Cancel all resting orders on ${marketLabel}${action.exclude_reduce_only ? " while keeping reduce-only protection intact" : ""}.`;
}

export function serializeGraphNode(node: BuilderFlowNode) {
  if (node.data.kind === "entry") {
    return { id: node.id, kind: node.data.kind, position: node.position };
  }
  if (node.data.kind === "condition") {
    const { id, ...condition } = node.data.condition;
    return { id: node.id, kind: node.data.kind, position: node.position, config: condition };
  }
  const { id, ...action } = node.data.action;
  return { id: node.id, kind: node.data.kind, position: node.position, config: action };
}

export function buildPrimaryRoute(nodes: BuilderFlowNode[], edges: BuilderFlowEdge[]) {
  const nodeLookup = new Map(nodes.map((node) => [node.id, node]));
  const pathNodeIds: string[] = [];
  const pathEdgeIds: string[] = [];
  const conditions: VisualCondition[] = [];
  const actions: VisualAction[] = [];
  const visited = new Set<string>([ENTRY_NODE_ID]);
  let currentId = ENTRY_NODE_ID;

  while (true) {
    const nextEdge = edges
      .filter((edge) => edge.source === currentId)
      .sort((left, right) => {
        const leftTarget = nodeLookup.get(left.target)?.position ?? { x: Number.MAX_SAFE_INTEGER, y: Number.MAX_SAFE_INTEGER };
        const rightTarget = nodeLookup.get(right.target)?.position ?? { x: Number.MAX_SAFE_INTEGER, y: Number.MAX_SAFE_INTEGER };
        return leftTarget.x - rightTarget.x || leftTarget.y - rightTarget.y || left.id.localeCompare(right.id);
      })
      .find((edge) => nodeLookup.has(edge.target) && !visited.has(edge.target));

    if (!nextEdge) {
      break;
    }

    pathEdgeIds.push(nextEdge.id);
    currentId = nextEdge.target;
    visited.add(currentId);
    pathNodeIds.push(currentId);

    const currentNode = nodeLookup.get(currentId);
    if (!currentNode) {
      break;
    }
    if (currentNode.data.kind === "condition") {
      conditions.push(currentNode.data.condition);
    }
    if (currentNode.data.kind === "action") {
      actions.push(currentNode.data.action);
    }
  }

  return { nodeIds: pathNodeIds, edgeIds: pathEdgeIds, conditions, actions };
}

export function buildRoutesFromGraph(nodes: BuilderFlowNode[], edges: BuilderFlowEdge[]): BuilderAiRoute[] {
  const nodeLookup = new Map(nodes.map((node) => [node.id, node]));
  const outgoingLookup = new Map<string, BuilderFlowEdge[]>();
  const routes: BuilderAiRoute[] = [];
  const seenRouteKeys = new Set<string>();

  edges.forEach((edge) => {
    const current = outgoingLookup.get(edge.source) ?? [];
    current.push(edge);
    outgoingLookup.set(edge.source, current);
  });

  outgoingLookup.forEach((edgeList, sourceId) => {
    const sortedEdges = [...edgeList].sort((left, right) => {
      const leftTarget = nodeLookup.get(left.target)?.position ?? { x: Number.MAX_SAFE_INTEGER, y: Number.MAX_SAFE_INTEGER };
      const rightTarget = nodeLookup.get(right.target)?.position ?? { x: Number.MAX_SAFE_INTEGER, y: Number.MAX_SAFE_INTEGER };
      return leftTarget.x - rightTarget.x || leftTarget.y - rightTarget.y || left.id.localeCompare(right.id);
    });
    outgoingLookup.set(sourceId, sortedEdges);
  });

  function visit(
    nodeId: string,
    conditions: VisualCondition[],
    actions: VisualAction[],
    trail: Set<string>,
  ) {
    if (trail.has(nodeId)) {
      return;
    }

    const nextTrail = new Set(trail);
    nextTrail.add(nodeId);
    const outgoing = outgoingLookup.get(nodeId) ?? [];

    if (outgoing.length === 0) {
      if (conditions.length === 0 || actions.length === 0) {
        return;
      }
      const route: BuilderAiRoute = {
        conditions: conditions.map((condition) => ({ ...condition })),
        actions: actions.map((action) => ({ ...action })),
      };
      const routeKey = JSON.stringify(route);
      if (!seenRouteKeys.has(routeKey)) {
        seenRouteKeys.add(routeKey);
        routes.push(route);
      }
      return;
    }

    outgoing.forEach((edge) => {
      const nextNode = nodeLookup.get(edge.target);
      if (!nextNode || nextNode.data.kind === "entry") {
        return;
      }
      if (nextNode.data.kind === "condition") {
        visit(edge.target, [...conditions, { ...nextNode.data.condition }], actions, nextTrail);
        return;
      }
      visit(edge.target, conditions, [...actions, { ...nextNode.data.action }], nextTrail);
    });
  }

  visit(ENTRY_NODE_ID, [], [], new Set<string>());
  return routes;
}

function buildMomentumBreakoutGraph(): BuilderGraphData {
  const trendCross = createCondition("ema_crosses_above");
  trendCross.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  trendCross.timeframe = "5m";
  trendCross.fast_period = 5;
  trendCross.slow_period = 13;

  const higherTimeframeTrend = createCondition("higher_timeframe_sma_above");
  higherTimeframeTrend.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  higherTimeframeTrend.timeframe = "5m";
  higherTimeframeTrend.secondary_timeframe = "1h";
  higherTimeframeTrend.period = 50;

  const liquidityGate = createCondition("volume_above");
  liquidityGate.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  liquidityGate.value = 10000000;

  const cooldown = createCondition("cooldown_elapsed");
  cooldown.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  cooldown.seconds = 45;

  const longEntry = createAction("open_long");
  longEntry.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  longEntry.size_usd = 90;
  longEntry.leverage = 4;

  const protection = createAction("set_tpsl");
  protection.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  protection.take_profit_pct = 0.8;
  protection.stop_loss_pct = 0.4;

  const nodes: BuilderFlowNode[] = [
    createEntryNode(),
    createConditionNode(trendCross, { x: 300, y: 220 }),
    createConditionNode(higherTimeframeTrend, { x: 600, y: 220 }),
    createConditionNode(liquidityGate, { x: 900, y: 220 }),
    createConditionNode(cooldown, { x: 1200, y: 220 }),
    createActionNode(longEntry, { x: 1500, y: 156 }),
    createActionNode(protection, { x: 1800, y: 156 }),
  ];

  const edges: BuilderFlowEdge[] = [
    createCanvasEdge(ENTRY_NODE_ID, trendCross.id),
    createCanvasEdge(trendCross.id, higherTimeframeTrend.id),
    createCanvasEdge(higherTimeframeTrend.id, liquidityGate.id),
    createCanvasEdge(liquidityGate.id, cooldown.id),
    createCanvasEdge(cooldown.id, longEntry.id),
    createCanvasEdge(longEntry.id, protection.id),
  ];

  return { nodes, edges };
}

function buildMeanReversionGraph(): BuilderGraphData {
  const overbought = createCondition("rsi_above");
  overbought.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  overbought.timeframe = "5m";
  overbought.period = 14;
  overbought.value = 71;

  const exhaustion = createCondition("bollinger_above_upper");
  exhaustion.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  exhaustion.timeframe = "5m";
  exhaustion.period = 20;
  exhaustion.value = 2;

  const liquidityGate = createCondition("volume_above");
  liquidityGate.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  liquidityGate.value = 10000000;

  const cooldown = createCondition("cooldown_elapsed");
  cooldown.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  cooldown.seconds = 60;

  const shortEntry = createAction("open_short");
  shortEntry.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  shortEntry.size_usd = 85;
  shortEntry.leverage = 3;

  const protection = createAction("set_tpsl");
  protection.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  protection.take_profit_pct = 0.75;
  protection.stop_loss_pct = 0.45;

  const nodes: BuilderFlowNode[] = [
    createEntryNode(),
    createConditionNode(overbought, { x: 300, y: 220 }),
    createConditionNode(exhaustion, { x: 600, y: 220 }),
    createConditionNode(liquidityGate, { x: 900, y: 220 }),
    createConditionNode(cooldown, { x: 1200, y: 220 }),
    createActionNode(shortEntry, { x: 1500, y: 156 }),
    createActionNode(protection, { x: 1800, y: 156 }),
  ];

  const edges: BuilderFlowEdge[] = [
    createCanvasEdge(ENTRY_NODE_ID, overbought.id),
    createCanvasEdge(overbought.id, exhaustion.id),
    createCanvasEdge(exhaustion.id, liquidityGate.id),
    createCanvasEdge(liquidityGate.id, cooldown.id),
    createCanvasEdge(cooldown.id, shortEntry.id),
    createCanvasEdge(shortEntry.id, protection.id),
  ];

  return { nodes, edges };
}

function buildSupportExitGraph(): BuilderGraphData {
  const higherTimeframeTrend = createCondition("higher_timeframe_sma_above");
  higherTimeframeTrend.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  higherTimeframeTrend.timeframe = "5m";
  higherTimeframeTrend.secondary_timeframe = "1h";
  higherTimeframeTrend.period = 50;

  const pullback = createCondition("rsi_below");
  pullback.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  pullback.timeframe = "5m";
  pullback.period = 14;
  pullback.value = 42;

  const reclaim = createCondition("ema_crosses_above");
  reclaim.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  reclaim.timeframe = "5m";
  reclaim.fast_period = 8;
  reclaim.slow_period = 21;

  const cooldown = createCondition("cooldown_elapsed");
  cooldown.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  cooldown.seconds = 75;

  const longEntry = createAction("open_long");
  longEntry.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  longEntry.size_usd = 95;
  longEntry.leverage = 4;

  const protection = createAction("set_tpsl");
  protection.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  protection.take_profit_pct = 1.0;
  protection.stop_loss_pct = 0.55;

  const nodes: BuilderFlowNode[] = [
    createEntryNode(),
    createConditionNode(higherTimeframeTrend, { x: 300, y: 220 }),
    createConditionNode(pullback, { x: 600, y: 220 }),
    createConditionNode(reclaim, { x: 900, y: 220 }),
    createConditionNode(cooldown, { x: 1200, y: 220 }),
    createActionNode(longEntry, { x: 1500, y: 156 }),
    createActionNode(protection, { x: 1800, y: 156 }),
  ];

  const edges: BuilderFlowEdge[] = [
    createCanvasEdge(ENTRY_NODE_ID, higherTimeframeTrend.id),
    createCanvasEdge(higherTimeframeTrend.id, pullback.id),
    createCanvasEdge(pullback.id, reclaim.id),
    createCanvasEdge(reclaim.id, cooldown.id),
    createCanvasEdge(cooldown.id, longEntry.id),
    createCanvasEdge(longEntry.id, protection.id),
  ];

  return { nodes, edges };
}

function buildTwapTrendGraph(): BuilderGraphData {
  const trendCross = createCondition("ema_crosses_below");
  trendCross.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  trendCross.timeframe = "5m";
  trendCross.fast_period = 5;
  trendCross.slow_period = 13;

  const followThrough = createCondition("higher_timeframe_sma_below");
  followThrough.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  followThrough.timeframe = "5m";
  followThrough.secondary_timeframe = "1h";
  followThrough.period = 50;

  const breakdown = createCondition("breakout_below_recent_low");
  breakdown.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  breakdown.timeframe = "5m";
  breakdown.period = 12;

  const cooldown = createCondition("cooldown_elapsed");
  cooldown.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  cooldown.seconds = 45;

  const shortEntry = createAction("open_short");
  shortEntry.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  shortEntry.size_usd = 90;
  shortEntry.leverage = 4;

  const protection = createAction("set_tpsl");
  protection.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  protection.take_profit_pct = 0.9;
  protection.stop_loss_pct = 0.45;

  const nodes: BuilderFlowNode[] = [
    createEntryNode(),
    createConditionNode(trendCross, { x: 300, y: 220 }),
    createConditionNode(followThrough, { x: 600, y: 220 }),
    createConditionNode(breakdown, { x: 900, y: 220 }),
    createConditionNode(cooldown, { x: 1200, y: 220 }),
    createActionNode(shortEntry, { x: 1500, y: 156 }),
    createActionNode(protection, { x: 1800, y: 156 }),
  ];

  const edges: BuilderFlowEdge[] = [
    createCanvasEdge(ENTRY_NODE_ID, trendCross.id),
    createCanvasEdge(trendCross.id, followThrough.id),
    createCanvasEdge(followThrough.id, breakdown.id),
    createCanvasEdge(breakdown.id, cooldown.id),
    createCanvasEdge(cooldown.id, shortEntry.id),
    createCanvasEdge(shortEntry.id, protection.id),
  ];

  return { nodes, edges };
}

function buildMakerReclaimGraph(): BuilderGraphData {
  const reclaim = createCondition("bollinger_below_lower");
  reclaim.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  reclaim.timeframe = "5m";
  reclaim.period = 20;
  reclaim.value = 2;

  const trendCross = createCondition("rsi_below");
  trendCross.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  trendCross.timeframe = "5m";
  trendCross.period = 14;
  trendCross.value = 29;

  const liquidityGate = createCondition("volume_above");
  liquidityGate.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  liquidityGate.value = 10000000;

  const cooldown = createCondition("cooldown_elapsed");
  cooldown.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  cooldown.seconds = 60;

  const longEntry = createAction("open_long");
  longEntry.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  longEntry.size_usd = 80;
  longEntry.leverage = 3;

  const protection = createAction("set_tpsl");
  protection.symbol = BOT_MARKET_UNIVERSE_SYMBOL;
  protection.take_profit_pct = 0.7;
  protection.stop_loss_pct = 0.4;

  const nodes: BuilderFlowNode[] = [
    createEntryNode(),
    createConditionNode(reclaim, { x: 300, y: 220 }),
    createConditionNode(trendCross, { x: 600, y: 220 }),
    createConditionNode(liquidityGate, { x: 900, y: 220 }),
    createConditionNode(cooldown, { x: 1200, y: 220 }),
    createActionNode(longEntry, { x: 1500, y: 156 }),
    createActionNode(protection, { x: 1800, y: 156 }),
  ];

  const edges: BuilderFlowEdge[] = [
    createCanvasEdge(ENTRY_NODE_ID, reclaim.id),
    createCanvasEdge(reclaim.id, trendCross.id),
    createCanvasEdge(trendCross.id, liquidityGate.id),
    createCanvasEdge(liquidityGate.id, cooldown.id),
    createCanvasEdge(cooldown.id, longEntry.id),
    createCanvasEdge(longEntry.id, protection.id),
  ];

  return { nodes, edges };
}

export const BUILDER_STARTER_TEMPLATES: BuilderStarterTemplate[] = [
  {
    id: "momentum-breakout-v1",
    name: "Multi-Market Trend Scalper",
    description: "Trades fast long continuation across selected markets once lower and higher timeframe trend agree.",
    marketScope: "Pacifica perpetuals / BTC, ETH, SOL",
    setupLabel: "Fast continuation",
    riskProfile: "Active",
    conditionCount: 4,
    actionCount: 2,
    buildGraph: buildMomentumBreakoutGraph,
  },
  {
    id: "mean-revert-v1",
    name: "Exhaustion Fade Short",
    description: "Sells sharp intraday extensions after upper-band stretch, overheated RSI, and liquidity confirmation line up.",
    marketScope: "Pacifica perpetuals / BTC, ETH, SOL",
    setupLabel: "Short fade",
    riskProfile: "Balanced",
    conditionCount: 4,
    actionCount: 2,
    buildGraph: buildMeanReversionGraph,
  },
  {
    id: "support-exit-v1",
    name: "Trend Pullback Reclaim",
    description: "Buys dip-and-reclaim setups inside an existing uptrend so the bot can keep cycling with the market.",
    marketScope: "Pacifica perpetuals / BTC, ETH, SOL",
    setupLabel: "Dip continuation",
    riskProfile: "Balanced",
    conditionCount: 4,
    actionCount: 2,
    buildGraph: buildSupportExitGraph,
  },
  {
    id: "twap-trend-v1",
    name: "Breakdown Momentum Short",
    description: "Presses fresh downside breaks when intraday weakness lines up with the broader trend.",
    marketScope: "Pacifica perpetuals / BTC, ETH, SOL",
    setupLabel: "Short continuation",
    riskProfile: "Active",
    conditionCount: 4,
    actionCount: 2,
    buildGraph: buildTwapTrendGraph,
  },
  {
    id: "maker-reclaim-v1",
    name: "Oversold Bounce Catcher",
    description: "Buys fast washouts after lower-band expansion and washed-out RSI create a short-term rebound setup.",
    marketScope: "Pacifica perpetuals / BTC, ETH, SOL",
    setupLabel: "Fast mean reversion",
    riskProfile: "Active",
    conditionCount: 4,
    actionCount: 2,
    buildGraph: buildMakerReclaimGraph,
  },
];

export function getBuilderStarterTemplate(id: string) {
  return BUILDER_STARTER_TEMPLATES.find((template) => template.id === id) ?? BUILDER_STARTER_TEMPLATES[0];
}

export function buildDefaultGraph() {
  return getBuilderStarterTemplate(DEFAULT_BUILDER_TEMPLATE_ID).buildGraph();
}

export function buildBlankGraph(): BuilderGraphData {
  return {
    nodes: [createEntryNode()],
    edges: [],
  };
}

export function buildGraphFromAiDraft(draft: BuilderAiDraft): BuilderGraphData {
  const entryNode = createEntryNode();
  const nodes: BuilderFlowNode[] = [entryNode];
  const edges: BuilderFlowEdge[] = [];
  const routeInputs = Array.isArray(draft.routes)
    ? draft.routes.filter((route) => route.conditions.length > 0 && route.actions.length > 0)
    : [];

  if (routeInputs.length > 0) {
    const routeGapY = 216;
    const routeCenterY = 220;
    const routeStartY = routeCenterY - ((routeInputs.length - 1) * routeGapY) / 2;
    entryNode.position = snapPosition({ x: entryNode.position.x, y: routeCenterY });

    routeInputs.forEach((route, routeIndex) => {
      const routeY = snapPosition({ x: 0, y: routeStartY + (routeIndex * routeGapY) }).y;
      let previousId = ENTRY_NODE_ID;
      const conditionBaseX = 320;
      const actionBaseX = conditionBaseX + route.conditions.length * 300;

      route.conditions.forEach((conditionInput, index) => {
        const fallbackType = CONDITION_OPTIONS.includes(conditionInput.type as (typeof CONDITION_OPTIONS)[number])
          ? (conditionInput.type as (typeof CONDITION_OPTIONS)[number])
          : "price_above";
        const baseCondition = createCondition(fallbackType);
        const condition: VisualCondition = {
          ...baseCondition,
          ...conditionInput,
          id: baseCondition.id,
          type: fallbackType,
          symbol: conditionInput.symbol?.trim() || baseCondition.symbol,
        };
        const node = createConditionNode(condition, { x: conditionBaseX + (index * 300), y: routeY });
        nodes.push(node);
        edges.push(createCanvasEdge(previousId, node.id));
        previousId = node.id;
      });

      route.actions.forEach((actionInput, index) => {
        const fallbackType = ACTION_OPTIONS.includes(actionInput.type as (typeof ACTION_OPTIONS)[number])
          ? (actionInput.type as (typeof ACTION_OPTIONS)[number])
          : "open_long";
        const baseAction = createAction(fallbackType);
        const action: VisualAction = {
          ...baseAction,
          ...actionInput,
          id: baseAction.id,
          type: fallbackType,
          symbol: actionInput.symbol?.trim() || baseAction.symbol,
        };
        const node = createActionNode(action, { x: actionBaseX + (index * 300), y: routeY });
        nodes.push(node);
        edges.push(createCanvasEdge(previousId, node.id));
        previousId = node.id;
      });
    });

    return { nodes, edges };
  }

  let previousId = ENTRY_NODE_ID;
  const conditionBaseX = 300;
  const actionBaseX = conditionBaseX + draft.conditions.length * 300;

  draft.conditions.forEach((conditionInput, index) => {
    const fallbackType = CONDITION_OPTIONS.includes(conditionInput.type as (typeof CONDITION_OPTIONS)[number])
      ? (conditionInput.type as (typeof CONDITION_OPTIONS)[number])
      : "price_above";
    const baseCondition = createCondition(fallbackType);
    const condition: VisualCondition = {
      ...baseCondition,
      ...conditionInput,
      id: baseCondition.id,
      type: fallbackType,
      symbol: conditionInput.symbol?.trim() || baseCondition.symbol,
    };
    const node = createConditionNode(condition, { x: conditionBaseX + (index * 300), y: 220 });
    nodes.push(node);
    edges.push(createCanvasEdge(previousId, node.id));
    previousId = node.id;
  });

  draft.actions.forEach((actionInput, index) => {
    const fallbackType = ACTION_OPTIONS.includes(actionInput.type as (typeof ACTION_OPTIONS)[number])
      ? (actionInput.type as (typeof ACTION_OPTIONS)[number])
      : "open_long";
    const baseAction = createAction(fallbackType);
    const action: VisualAction = {
      ...baseAction,
      ...actionInput,
      id: baseAction.id,
      type: fallbackType,
      symbol: actionInput.symbol?.trim() || baseAction.symbol,
    };
    const node = createActionNode(action, { x: actionBaseX + (index * 300), y: 156 });
    nodes.push(node);
    edges.push(createCanvasEdge(previousId, node.id));
    previousId = node.id;
  });

  return { nodes, edges };
}
