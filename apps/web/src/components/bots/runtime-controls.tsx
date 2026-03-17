"use client";

import { useState } from "react";

type RuntimeResponse = {
  id: string;
  status: string;
  mode: string;
  updated_at: string;
  deployed_at?: string | null;
  stopped_at?: string | null;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function RuntimeControls({
  botId,
  walletAddress,
  getAuthHeaders,
  onRuntimeUpdate,
}: {
  botId: string;
  walletAddress: string;
  getAuthHeaders: (headersInit?: HeadersInit) => Promise<Headers>;
  onRuntimeUpdate?: (runtime: RuntimeResponse) => void;
}) {
  const [riskPolicy, setRiskPolicy] = useState('{"max_leverage":5,"max_order_size_usd":200,"allocated_capital_usd":200,"cooldown_seconds":45,"max_drawdown_pct":18}');
  const [status, setStatus] = useState<"idle" | "deploy" | "pause" | "resume" | "stop">("idle");
  const [error, setError] = useState<string | null>(null);

  async function invoke(action: "deploy" | "pause" | "resume" | "stop") {
    setStatus(action);
    setError(null);
    try {
      const endpoint = `${API_BASE_URL}/api/bots/${botId}/${action}`;
      const body =
        action === "deploy"
          ? { wallet_address: walletAddress, risk_policy_json: JSON.parse(riskPolicy) as Record<string, unknown> }
          : undefined;

      const response = await fetch(endpoint, {
        method: "POST",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: body ? JSON.stringify(body) : undefined,
      });
      const payload = (await response.json()) as RuntimeResponse | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Runtime action failed" : "Runtime action failed");
      }
      onRuntimeUpdate?.(payload as RuntimeResponse);
    } catch (runtimeError) {
      setError(runtimeError instanceof Error ? runtimeError.message : "Runtime action failed");
    } finally {
      setStatus("idle");
    }
  }

  return (
    <section className="grid gap-4 border-l-2 border-[#74b97f] bg-[#16181a] p-6">
      <div className="flex items-center justify-between">
        <span className="label text-[#74b97f]">runtime controls</span>
        <span className="text-xs text-neutral-500">wallet-bound lifecycle</span>
      </div>

      <label className="grid gap-1.5 text-sm text-neutral-400">
        Deploy risk policy JSON
        <textarea
          value={riskPolicy}
          onChange={(event) => setRiskPolicy(event.target.value)}
          rows={4}
          className="border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
        />
      </label>

      {error ? <p className="text-sm text-[#dce85d]">{error}</p> : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void invoke("deploy")}
          disabled={status !== "idle"}
          className="bg-[#dce85d] px-4 py-2.5 font-mono text-[0.62rem] font-semibold uppercase tracking-wider text-[#090a0a] transition hover:bg-[#e8f06d] disabled:opacity-60"
        >
          {status === "deploy" ? "deploying…" : "deploy"}
        </button>
        <button
          type="button"
          onClick={() => void invoke("pause")}
          disabled={status !== "idle"}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2.5 text-[0.62rem] font-semibold uppercase tracking-wider text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d] disabled:opacity-60"
        >
          pause
        </button>
        <button
          type="button"
          onClick={() => void invoke("resume")}
          disabled={status !== "idle"}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2.5 text-[0.62rem] font-semibold uppercase tracking-wider text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f] disabled:opacity-60"
        >
          resume
        </button>
        <button
          type="button"
          onClick={() => void invoke("stop")}
          disabled={status !== "idle"}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2.5 text-[0.62rem] font-semibold uppercase tracking-wider text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d] disabled:opacity-60"
        >
          stop
        </button>
      </div>
    </section>
  );
}
