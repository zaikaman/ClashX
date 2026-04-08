export type RuntimePolicyDraft = {
  maxLeverage: number;
  maxOrderSizeUsd: number;
  allocatedCapitalUsd: number;
  maxOpenPositions: number;
  cooldownSeconds: number;
  maxDrawdownPct: number;
  allowedSymbols: string;
  sizingMode: string;
  fixedUsdAmount: number;
  riskPerTradePct: number;
};

export const DEFAULT_RUNTIME_POLICY: RuntimePolicyDraft = {
  maxLeverage: 5,
  maxOrderSizeUsd: 200,
  allocatedCapitalUsd: 200,
  maxOpenPositions: 1,
  cooldownSeconds: 45,
  maxDrawdownPct: 18,
  allowedSymbols: "BTC,ETH,SOL",
  sizingMode: "fixed_usd",
  fixedUsdAmount: 200,
  riskPerTradePct: 1,
};

function toNumber(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function runtimePolicyDraftFromPolicy(
  policy: Record<string, unknown> | null | undefined,
): RuntimePolicyDraft {
  const source = policy ?? {};
  const symbols = Array.isArray(source.allowed_symbols) ? source.allowed_symbols : [];

  return {
    maxLeverage: toNumber(source.max_leverage, DEFAULT_RUNTIME_POLICY.maxLeverage),
    maxOrderSizeUsd: toNumber(source.max_order_size_usd, DEFAULT_RUNTIME_POLICY.maxOrderSizeUsd),
    allocatedCapitalUsd: toNumber(source.allocated_capital_usd, DEFAULT_RUNTIME_POLICY.allocatedCapitalUsd),
    maxOpenPositions: toNumber(source.max_open_positions, DEFAULT_RUNTIME_POLICY.maxOpenPositions),
    cooldownSeconds: toNumber(source.cooldown_seconds, DEFAULT_RUNTIME_POLICY.cooldownSeconds),
    maxDrawdownPct: toNumber(source.max_drawdown_pct, DEFAULT_RUNTIME_POLICY.maxDrawdownPct),
    allowedSymbols: symbols.map((value) => String(value)).join(","),
    sizingMode:
      typeof source.sizing_mode === "string" && source.sizing_mode.length > 0
        ? source.sizing_mode
        : DEFAULT_RUNTIME_POLICY.sizingMode,
    fixedUsdAmount: toNumber(source.fixed_usd_amount, DEFAULT_RUNTIME_POLICY.fixedUsdAmount),
    riskPerTradePct: toNumber(source.risk_per_trade_pct, DEFAULT_RUNTIME_POLICY.riskPerTradePct),
  };
}

export function runtimePolicyDraftToPayload(draft: RuntimePolicyDraft): Record<string, unknown> {
  return {
    max_leverage: draft.maxLeverage,
    max_order_size_usd: draft.maxOrderSizeUsd,
    allocated_capital_usd: draft.allocatedCapitalUsd,
    max_open_positions: draft.maxOpenPositions,
    cooldown_seconds: draft.cooldownSeconds,
    max_drawdown_pct: draft.maxDrawdownPct,
    allowed_symbols: draft.allowedSymbols
      .split(",")
      .map((value) => value.trim().toUpperCase())
      .filter(Boolean),
    sizing_mode: draft.sizingMode,
    fixed_usd_amount: draft.fixedUsdAmount,
    risk_per_trade_pct: draft.riskPerTradePct,
  };
}
