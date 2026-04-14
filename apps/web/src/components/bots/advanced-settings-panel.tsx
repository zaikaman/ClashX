"use client";

import { type RuntimePolicyDraft } from "@/components/bots/runtime-policy";

const FIELD_LABEL_CLASS = "grid gap-2 text-sm text-neutral-400";
const INPUT_CLASS =
  "w-full rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d] disabled:cursor-not-allowed disabled:opacity-60";
const SECTION_CARD_CLASS =
  "grid gap-4 rounded-[1.4rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] p-4";

export function AdvancedSettingsPanel({
  policy,
  status,
  error,
  isDeployed,
  onPolicyChange,
  onSave,
}: {
  policy: RuntimePolicyDraft;
  status: "idle" | "loading" | "saving";
  error: string | null;
  isDeployed: boolean;
  onPolicyChange: (policy: RuntimePolicyDraft) => void;
  onSave: () => void | Promise<void>;
}) {
  const inputsDisabled = status !== "idle";

  function updatePolicy(patch: Partial<RuntimePolicyDraft>) {
    onPolicyChange({ ...policy, ...patch });
  }

  return (
    <article className="grid gap-5 rounded-[1.75rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
            Advanced settings
          </span>
          <h3 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">
            Runtime policy
          </h3>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            {isDeployed
              ? "Edit the live runtime policy here. The deploy controls above use this same policy source."
              : "Set the deployment policy once here. The deploy controls above use this same draft."}
          </p>
        </div>
        <span className="text-xs text-neutral-500">
          {isDeployed ? "live runtime policy" : "deploy-time runtime policy"}
        </span>
      </div>

      {status === "loading" ? (
        <div className="rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-400">
          Loading the current runtime policy.
        </div>
      ) : null}

      <div className={SECTION_CARD_CLASS}>
        <div className="grid gap-1">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
            Risk profile
          </span>
          <p className="text-sm leading-7 text-neutral-400">
            Set the capital, leverage cap, and drawdown boundaries this runtime should respect.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className={FIELD_LABEL_CLASS}>
            Leverage cap
            <input
              type="number"
              min={1}
              value={policy.maxLeverage}
              onChange={(event) => updatePolicy({ maxLeverage: Number(event.target.value) })}
              className={INPUT_CLASS}
              disabled={inputsDisabled}
            />
          </label>
          <label className={FIELD_LABEL_CLASS}>
            Max order size USD
            <input
              type="number"
              min={1}
              value={policy.maxOrderSizeUsd}
              onChange={(event) => updatePolicy({ maxOrderSizeUsd: Number(event.target.value) })}
              className={INPUT_CLASS}
              disabled={inputsDisabled}
            />
          </label>
          <label className={FIELD_LABEL_CLASS}>
            Allocated capital USD
            <input
              type="number"
              min={1}
              value={policy.allocatedCapitalUsd}
              onChange={(event) => updatePolicy({ allocatedCapitalUsd: Number(event.target.value) })}
              className={INPUT_CLASS}
              disabled={inputsDisabled}
            />
          </label>
          <label className={FIELD_LABEL_CLASS}>
            Max open positions
            <input
              type="number"
              min={1}
              value={policy.maxOpenPositions}
              onChange={(event) => updatePolicy({ maxOpenPositions: Number(event.target.value) })}
              className={INPUT_CLASS}
              disabled={inputsDisabled}
            />
          </label>
          <label className={FIELD_LABEL_CLASS}>
            Cooldown seconds
            <input
              type="number"
              min={0}
              value={policy.cooldownSeconds}
              onChange={(event) => updatePolicy({ cooldownSeconds: Number(event.target.value) })}
              className={INPUT_CLASS}
              disabled={inputsDisabled}
            />
          </label>
          <label className={FIELD_LABEL_CLASS}>
            Max drawdown % of allocation
            <input
              type="number"
              min={0}
              step="0.1"
              value={policy.maxDrawdownPct}
              onChange={(event) => updatePolicy({ maxDrawdownPct: Number(event.target.value) })}
              className={INPUT_CLASS}
              disabled={inputsDisabled}
            />
          </label>
        </div>
      </div>

      <div className={SECTION_CARD_CLASS}>
        <div className="grid gap-1">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
            Execution scope
          </span>
          <p className="text-sm leading-7 text-neutral-400">
            Market scope is managed in Builder. This panel only controls runtime risk and sizing.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className={FIELD_LABEL_CLASS}>
            Market scope symbols (Builder only)
            <input
              value={policy.allowedSymbols}
              readOnly
              placeholder="BTC,ETH,SOL"
              className={INPUT_CLASS}
              aria-readonly="true"
            />
          </label>
          <label className={FIELD_LABEL_CLASS}>
            Sizing mode
            <select
              value={policy.sizingMode}
              onChange={(event) => updatePolicy({ sizingMode: event.target.value })}
              className={INPUT_CLASS}
              disabled={inputsDisabled}
            >
              <option value="fixed_usd">fixed usd</option>
              <option value="risk_adjusted">risk adjusted</option>
            </select>
          </label>
          {policy.sizingMode === "fixed_usd" ? (
            <label className={FIELD_LABEL_CLASS}>
              USD per trade
              <input
                type="number"
                min={1}
                value={policy.fixedUsdAmount}
                onChange={(event) => updatePolicy({ fixedUsdAmount: Number(event.target.value) })}
                className={INPUT_CLASS}
                disabled={inputsDisabled}
              />
            </label>
          ) : (
            <label className={FIELD_LABEL_CLASS}>
              Risk % per trade
              <input
                type="number"
                min={0.1}
                step="0.1"
                value={policy.riskPerTradePct}
                onChange={(event) => updatePolicy({ riskPerTradePct: Number(event.target.value) })}
                className={INPUT_CLASS}
                disabled={inputsDisabled}
              />
            </label>
          )}
        </div>

        <p className="text-xs leading-6 text-neutral-500">
          Market scope cannot be edited here. Use the Builder page to change which symbols this bot may trade.
        </p>
        <p className="text-xs leading-6 text-neutral-500">
          Drawdown uses realized plus unrealized PnL against this runtime allocation. If a bot with $
          {policy.allocatedCapitalUsd || 0} allocated reaches a {policy.maxDrawdownPct}% loss budget, it is stopped
          automatically. Open positions are capped at {policy.maxOpenPositions} so the runtime cannot keep stacking
          fresh entries indefinitely.
        </p>
        <p className="text-xs leading-6 text-neutral-500">
          {policy.sizingMode === "fixed_usd"
            ? `Each fresh entry uses ${policy.fixedUsdAmount || 0} USD before leverage.`
            : `Each fresh entry risks ${policy.riskPerTradePct || 0}% of the allocated capital, using the builder stop loss on the matching TP / SL block.`}
        </p>
      </div>

      {error ? <p className="text-sm text-[#dce85d]">{error}</p> : null}

      {isDeployed ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void onSave()}
            disabled={status !== "idle"}
            className="inline-flex items-center justify-center rounded-full bg-[#dce85d] px-5 py-2.5 font-mono text-[0.62rem] font-semibold uppercase tracking-wider text-[#090a0a] transition hover:bg-[#e8f06d] disabled:opacity-60"
          >
            {status === "saving" ? "saving..." : "save live policy"}
          </button>
        </div>
      ) : (
        <div className="rounded-[1.2rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-3 text-sm leading-6 text-neutral-400">
          This draft is not persisted yet because the bot is not deployed. When you deploy from the controls above, the runtime starts with these exact settings.
        </div>
      )}
    </article>
  );
}
