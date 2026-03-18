"use client";

import { useEffect, useState } from "react";

type RiskStateResponse = {
  runtime_id: string;
  risk_policy_json: Record<string, unknown>;
  runtime_state: Record<string, unknown>;
  updated_at: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function AdvancedSettingsPanel({
  botId,
  walletAddress,
  getAuthHeaders,
  onSaved,
}: {
  botId: string;
  walletAddress: string;
  getAuthHeaders: (headersInit?: HeadersInit) => Promise<Headers>;
  onSaved?: () => void;
}) {
  const [maxLeverage, setMaxLeverage] = useState(5);
  const [maxOrderSizeUsd, setMaxOrderSizeUsd] = useState(200);
  const [allocatedCapitalUsd, setAllocatedCapitalUsd] = useState(200);
  const [maxOpenPositions, setMaxOpenPositions] = useState(1);
  const [cooldownSeconds, setCooldownSeconds] = useState(45);
  const [maxDrawdownPct, setMaxDrawdownPct] = useState(18);
  const [allowedSymbols, setAllowedSymbols] = useState("BTC,ETH,SOL");
  const [sizingMode, setSizingMode] = useState("fixed_usd");
  const [status, setStatus] = useState<"idle" | "loading" | "saving">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadRiskState() {
      setStatus("loading");
      setError(null);
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/bots/${botId}/risk-state?wallet_address=${encodeURIComponent(walletAddress)}`,
          { cache: "no-store", headers: await getAuthHeaders() },
        );
        const payload = (await response.json()) as RiskStateResponse | { detail?: string };
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Could not load risk state" : "Could not load risk state");
        }
        const policy = (payload as RiskStateResponse).risk_policy_json;
        setMaxLeverage(Number(policy.max_leverage ?? 5));
        setMaxOrderSizeUsd(Number(policy.max_order_size_usd ?? 200));
        setAllocatedCapitalUsd(Number(policy.allocated_capital_usd ?? 200));
        setMaxOpenPositions(Number(policy.max_open_positions ?? 1));
        setCooldownSeconds(Number(policy.cooldown_seconds ?? 45));
        setMaxDrawdownPct(Number(policy.max_drawdown_pct ?? 18));
        const symbols = Array.isArray(policy.allowed_symbols) ? policy.allowed_symbols : [];
        setAllowedSymbols(symbols.map((value) => String(value)).join(","));
        setSizingMode(String(policy.sizing_mode ?? "fixed_usd"));
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load risk state");
      } finally {
        setStatus("idle");
      }
    }

    void loadRiskState();
  }, [botId, walletAddress, getAuthHeaders]);

  async function saveSettings() {
    setStatus("saving");
    setError(null);
    try {
      const nextPolicy = {
        max_leverage: maxLeverage,
        max_order_size_usd: maxOrderSizeUsd,
        allocated_capital_usd: allocatedCapitalUsd,
        max_open_positions: maxOpenPositions,
        cooldown_seconds: cooldownSeconds,
        max_drawdown_pct: maxDrawdownPct,
        allowed_symbols: allowedSymbols
          .split(",")
          .map((value) => value.trim().toUpperCase())
          .filter(Boolean),
        sizing_mode: sizingMode,
      };
      const response = await fetch(`${API_BASE_URL}/api/bots/${botId}/risk-state`, {
        method: "PATCH",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ wallet_address: walletAddress, risk_policy_json: nextPolicy }),
      });
      const payload = (await response.json()) as RiskStateResponse | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Could not save settings" : "Could not save settings");
      }
      onSaved?.();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not save settings");
    } finally {
      setStatus("idle");
    }
  }

  return (
    <section className="grid gap-4 border-l-2 border-[rgba(255,255,255,0.12)] bg-[#16181a] p-6">
      <div className="flex items-center justify-between">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">advanced execution settings</span>
        <span className="text-xs text-neutral-500">live runtime policy</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1.5 text-sm text-neutral-400">
          Max leverage
          <input type="number" min={1} value={maxLeverage} onChange={(event) => setMaxLeverage(Number(event.target.value))} className="w-full border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d] rounded-md" />
        </label>
        <label className="grid gap-1.5 text-sm text-neutral-400">
          Max order size USD
          <input type="number" min={1} value={maxOrderSizeUsd} onChange={(event) => setMaxOrderSizeUsd(Number(event.target.value))} className="w-full border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d] rounded-md" />
        </label>
        <label className="grid gap-1.5 text-sm text-neutral-400">
          Allocated capital USD
          <input type="number" min={1} value={allocatedCapitalUsd} onChange={(event) => setAllocatedCapitalUsd(Number(event.target.value))} className="w-full border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d] rounded-md" />
        </label>
        <label className="grid gap-1.5 text-sm text-neutral-400">
          Max open positions
          <input type="number" min={1} value={maxOpenPositions} onChange={(event) => setMaxOpenPositions(Number(event.target.value))} className="w-full border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d] rounded-md" />
        </label>
        <label className="grid gap-1.5 text-sm text-neutral-400">
          Cooldown seconds
          <input type="number" min={0} value={cooldownSeconds} onChange={(event) => setCooldownSeconds(Number(event.target.value))} className="w-full border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d] rounded-md" />
        </label>
        <label className="grid gap-1.5 text-sm text-neutral-400">
          Max drawdown % of allocation
          <input type="number" min={0} step="0.1" value={maxDrawdownPct} onChange={(event) => setMaxDrawdownPct(Number(event.target.value))} className="w-full border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d] rounded-md" />
        </label>
      </div>
      <p className="text-xs leading-6 text-neutral-500">
        Drawdown now uses realized plus unrealized bot PnL against this runtime allocation. If a bot with ${allocatedCapitalUsd || 0} allocated reaches a {maxDrawdownPct}% loss budget, it is stopped automatically. Open positions are capped at {maxOpenPositions} so the runtime cannot keep stacking fresh entries indefinitely.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1.5 text-sm text-neutral-400">
          Market scope symbols
          <input value={allowedSymbols} onChange={(event) => setAllowedSymbols(event.target.value)} placeholder="BTC,ETH,SOL" className="w-full border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d] rounded-md" />
        </label>
        <label className="grid gap-1.5 text-sm text-neutral-400">
          Sizing mode
          <select
            value={sizingMode}
            onChange={(event) => setSizingMode(event.target.value)}
            className="w-full border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d] rounded-md"
          >
            <option value="fixed_usd">fixed usd</option>
            <option value="risk_adjusted">risk adjusted</option>
          </select>
        </label>
      </div>

      {error ? <p className="text-sm text-[#dce85d]">{error}</p> : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void saveSettings()}
          disabled={status !== "idle"}
          className="inline-flex items-center justify-center rounded-full bg-[#dce85d] px-5 py-2.5 font-mono text-[0.62rem] font-semibold uppercase tracking-wider text-[#090a0a] transition hover:bg-[#e8f06d] disabled:opacity-60"
        >
          {status === "saving" ? <><span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full spinner-reverse mr-2 align-middle"></span>saving...</> : "save settings"}
        </button>
      </div>
    </section>
  );
}
