"use client";

import type { LeaderboardRow } from "@/lib/public-bots";
import type { PortfolioDraft } from "@/lib/copy-portfolios";

type PortfolioBasketComposerProps = {
  draft: PortfolioDraft;
  candidates: LeaderboardRow[];
  editingLabel?: string | null;
  submitting?: boolean;
  onDraftChange: (draft: PortfolioDraft) => void;
  onSubmit: () => void;
  onCancelEdit?: () => void;
};

function formatScale(scaleBps: number) {
  return `${(scaleBps / 100).toFixed(0)}%`;
}

export function PortfolioBasketComposer({
  draft,
  candidates,
  editingLabel,
  submitting = false,
  onDraftChange,
  onSubmit,
  onCancelEdit,
}: PortfolioBasketComposerProps) {
  const selectedIds = new Set(draft.members.map((member) => member.source_runtime_id));
  const totalWeight = draft.members.reduce((sum, member) => sum + member.target_weight_pct, 0);

  function patchDraft(next: Partial<PortfolioDraft>) {
    onDraftChange({ ...draft, ...next });
  }

  function addCandidate(candidate: LeaderboardRow) {
    if (selectedIds.has(candidate.runtime_id)) {
      return;
    }
    patchDraft({
      members: [
        ...draft.members,
        {
          source_runtime_id: candidate.runtime_id,
          source_bot_name: candidate.bot_name,
          target_weight_pct: 25,
          max_scale_bps: 20_000,
        },
      ],
    });
  }

  function updateMember(
    runtimeId: string,
    patch: Partial<PortfolioDraft["members"][number]>,
  ) {
    patchDraft({
      members: draft.members.map((member) =>
        member.source_runtime_id === runtimeId ? { ...member, ...patch } : member,
      ),
    });
  }

  function removeMember(runtimeId: string) {
    patchDraft({
      members: draft.members.filter((member) => member.source_runtime_id !== runtimeId),
    });
  }

  return (
    <article className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <span className="label text-[#dce85d]">{editingLabel ? "Portfolio editor" : "Basket composer"}</span>
          <h2 className="font-mono text-[clamp(1.6rem,3vw,2.4rem)] font-bold uppercase tracking-tight text-neutral-50">
            {editingLabel ? editingLabel : "Build a multi-bot book"}
          </h2>
          <p className="max-w-3xl text-sm leading-7 text-neutral-400">
            Blend several source bots into one allocation plan, cap how hard each leg can scale, and define the portfolio drawdown line before capital goes live.
          </p>
        </div>
        {editingLabel && onCancelEdit ? (
          <button
            type="button"
            onClick={onCancelEdit}
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-neutral-50 hover:text-neutral-50"
          >
            Stop editing
          </button>
        ) : null}
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="grid gap-4">
          <label className="grid gap-1.5 text-sm text-neutral-400">
            Basket name
            <input
              value={draft.name}
              onChange={(event) => patchDraft({ name: event.target.value })}
              placeholder="Momentum Blend"
              className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition placeholder:text-neutral-600 focus:border-[#dce85d]"
            />
          </label>
          <label className="grid gap-1.5 text-sm text-neutral-400">
            What makes this basket useful
            <textarea
              value={draft.description}
              onChange={(event) => patchDraft({ description: event.target.value })}
              placeholder="Pair trend, mean reversion, and low-drift leaders in one follower book."
              rows={4}
              className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition placeholder:text-neutral-600 focus:border-[#dce85d]"
            />
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="grid gap-1.5 text-sm text-neutral-400">
              Target capital
              <input
                type="number"
                min={50}
                step={50}
                value={draft.target_notional_usd}
                onChange={(event) => patchDraft({ target_notional_usd: Number(event.target.value) })}
                className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
              />
            </label>
            <label className="grid gap-1.5 text-sm text-neutral-400">
              Rebalance style
              <select
                value={draft.rebalance_mode}
                onChange={(event) => patchDraft({ rebalance_mode: event.target.value })}
                className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
              >
                <option value="drift">Drift-aware</option>
                <option value="scheduled">Scheduled</option>
                <option value="manual">Manual only</option>
              </select>
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="grid gap-1.5 text-sm text-neutral-400">
              Review cadence (minutes)
              <input
                type="number"
                min={5}
                step={5}
                value={draft.rebalance_interval_minutes}
                onChange={(event) => patchDraft({ rebalance_interval_minutes: Number(event.target.value) })}
                className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#74b97f]"
              />
            </label>
            <label className="grid gap-1.5 text-sm text-neutral-400">
              Drift tripwire (%)
              <input
                type="number"
                min={0.5}
                max={100}
                step={0.5}
                value={draft.drift_threshold_pct}
                onChange={(event) => patchDraft({ drift_threshold_pct: Number(event.target.value) })}
                className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#74b97f]"
              />
            </label>
          </div>

          <div className="grid gap-4 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Risk frame</span>
              <p className="text-sm leading-6 text-neutral-400">Set the drawdown line for the whole basket and the minimum trust bar for every member that stays live.</p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="grid gap-1.5 text-sm text-neutral-400">
                Basket max drawdown
                <input
                  type="number"
                  min={5}
                  max={95}
                  value={draft.risk_policy.max_drawdown_pct}
                  onChange={(event) =>
                    patchDraft({
                      risk_policy: {
                        ...draft.risk_policy,
                        max_drawdown_pct: Number(event.target.value),
                      },
                    })
                  }
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#16181a] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
                />
              </label>
              <label className="grid gap-1.5 text-sm text-neutral-400">
                Member max drawdown
                <input
                  type="number"
                  min={5}
                  max={95}
                  value={draft.risk_policy.max_member_drawdown_pct}
                  onChange={(event) =>
                    patchDraft({
                      risk_policy: {
                        ...draft.risk_policy,
                        max_member_drawdown_pct: Number(event.target.value),
                      },
                    })
                  }
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#16181a] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
                />
              </label>
              <label className="grid gap-1.5 text-sm text-neutral-400">
                Minimum trust score
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={draft.risk_policy.min_trust_score}
                  onChange={(event) =>
                    patchDraft({
                      risk_policy: {
                        ...draft.risk_policy,
                        min_trust_score: Number(event.target.value),
                      },
                    })
                  }
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#16181a] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
                />
              </label>
              <label className="grid gap-1.5 text-sm text-neutral-400">
                Max active members
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={draft.risk_policy.max_active_members}
                  onChange={(event) =>
                    patchDraft({
                      risk_policy: {
                        ...draft.risk_policy,
                        max_active_members: Number(event.target.value),
                      },
                    })
                  }
                  className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#16181a] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#dce85d]"
                />
              </label>
            </div>
          </div>
        </div>

        <div className="grid gap-4">
          <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="grid gap-1">
                <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Selected members</span>
                <span className="text-sm text-neutral-400">Target weight currently totals {totalWeight.toFixed(1)}%.</span>
              </div>
              <label className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-neutral-400">
                <input
                  type="checkbox"
                  checked={draft.activate_on_create}
                  onChange={(event) => patchDraft({ activate_on_create: event.target.checked })}
                  className="accent-[#dce85d]"
                />
                Start live
              </label>
            </div>

            {draft.members.length === 0 ? (
              <div className="rounded-[1.25rem] border border-dashed border-[rgba(255,255,255,0.08)] px-4 py-5 text-sm leading-6 text-neutral-400">
                Pull in two or more public bots to start shaping the basket.
              </div>
            ) : (
              <div className="grid gap-3">
                {draft.members.map((member) => (
                  <article key={member.source_runtime_id} className="grid gap-3 rounded-[1.25rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="grid gap-1">
                        <span className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">{member.source_bot_name}</span>
                        <span className="text-xs uppercase tracking-[0.16em] text-neutral-500">{member.source_runtime_id.slice(0, 12)}...</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeMember(member.source_runtime_id)}
                        className="rounded-full border border-[rgba(255,255,255,0.12)] px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#ff8a9b] hover:text-[#ff8a9b]"
                      >
                        Remove
                      </button>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <label className="grid gap-1.5 text-sm text-neutral-400">
                        Weight %
                        <input
                          type="number"
                          min={1}
                          max={100}
                          step={0.5}
                          value={member.target_weight_pct}
                          onChange={(event) => updateMember(member.source_runtime_id, { target_weight_pct: Number(event.target.value) })}
                          className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#74b97f]"
                        />
                      </label>
                      <label className="grid gap-1.5 text-sm text-neutral-400">
                        Max scale cap
                        <select
                          value={member.max_scale_bps}
                          onChange={(event) => updateMember(member.source_runtime_id, { max_scale_bps: Number(event.target.value) })}
                          className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-3 text-sm text-neutral-50 outline-none transition focus:border-[#74b97f]"
                        >
                          {[5_000, 10_000, 15_000, 20_000, 25_000, 30_000].map((value) => (
                            <option key={value} value={value}>
                              {formatScale(value)}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>

          <div className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">Add candidates</span>
              <span className="text-sm text-neutral-400">Start from live public leaders. Weighting is normalized on save, so the basket always lands on a clean 100% mix.</span>
            </div>
            <div className="grid gap-3">
              {candidates.slice(0, 8).map((candidate) => (
                <article
                  key={candidate.runtime_id}
                  className="grid gap-3 rounded-[1.25rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-4 md:grid-cols-[1fr_auto] md:items-center"
                >
                  <div className="grid gap-1">
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">{candidate.bot_name}</span>
                      <span className="rounded-full bg-[rgba(220,232,93,0.12)] px-2.5 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d]">
                        Rank {candidate.rank}
                      </span>
                    </div>
                    <p className="text-sm leading-6 text-neutral-400">
                      {candidate.strategy_type} · Trust {candidate.trust.trust_score} · Drawdown {candidate.drawdown.toFixed(1)}%
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => addCandidate(candidate)}
                    disabled={selectedIds.has(candidate.runtime_id)}
                    className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {selectedIds.has(candidate.runtime_id) ? "Added" : "Add to basket"}
                  </button>
                </article>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onSubmit}
              disabled={submitting || draft.members.length === 0 || draft.name.trim().length < 2}
              className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? "Saving..." : editingLabel ? "Update basket" : "Create basket"}
            </button>
            <div className="rounded-full border border-[rgba(255,255,255,0.08)] px-4 py-3 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
              {draft.members.length} member{draft.members.length === 1 ? "" : "s"} · ${draft.target_notional_usd.toLocaleString()}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}
