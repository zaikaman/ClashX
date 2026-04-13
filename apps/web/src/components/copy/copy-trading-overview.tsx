"use client";

import Link from "next/link";

import type {
  CopyTradingActivity,
  CopyTradingDashboard,
  CopyTradingDiscoverRow,
  CopyTradingFollow,
  CopyTradingPosition,
} from "@/lib/copy-dashboard";

function formatUsd(value: number) {
  return `$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function formatSignedUsd(value: number) {
  return `${value >= 0 ? "+" : "-"}${formatUsd(value).slice(1)}`;
}

function formatScale(scaleBps: number) {
  return `${(scaleBps / 100).toFixed(0)}%`;
}

function toneForPnl(value: number) {
  return value >= 0 ? "text-[#74b97f]" : "text-[#ff8a9b]";
}

type CopyTradingOverviewProps = {
  dashboard: CopyTradingDashboard;
  refreshing: boolean;
  scaleDrafts: Record<string, number>;
  savingRelationshipId: string | null;
  onRefresh: () => void;
  onScaleChange: (relationshipId: string, value: number) => void;
  onSaveScale: (relationshipId: string, scaleBps: number) => void;
  onResumeFollow: (relationshipId: string, scaleBps: number) => void;
  onStopFollow: (relationshipId: string) => void;
};

export function CopyTradingOverview({
  dashboard,
  refreshing,
  scaleDrafts,
  savingRelationshipId,
  onRefresh,
  onScaleChange,
  onSaveScale,
  onResumeFollow,
  onStopFollow,
}: CopyTradingOverviewProps) {
  return (
    <div className="grid gap-6 md:gap-8">
      <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.14),transparent_28%),radial-gradient(circle_at_bottom_right,rgba(116,185,127,0.14),transparent_24%),linear-gradient(140deg,#16181a,#0d0f10)] p-6 md:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="grid gap-2">
            <span className="text-[0.64rem] font-semibold uppercase tracking-[0.2em] text-[#dce85d]">Copy trading</span>
            <h1 className="font-mono text-[clamp(2.2rem,5vw,4rem)] font-extrabold uppercase leading-[0.92] tracking-[-0.05em] text-neutral-50">
              See your copy trading at a glance
            </h1>
            <p className="max-w-3xl text-sm leading-7 text-neutral-400 md:text-base">
              Keep an eye on copied exposure, live PnL, trader health, and execution issues without digging through extra tools.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onRefresh}
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-3 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
            >
              {refreshing ? "Refreshing..." : "Refresh"}
            </button>
            <Link
              href="/marketplace"
              className="rounded-full bg-[#dce85d] px-5 py-3 text-[0.64rem] font-semibold uppercase tracking-[0.16em] text-[#090a0a] transition hover:bg-[#e8f06d]"
            >
              Find bots
            </Link>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          <MetricCard label="Active follows" value={`${dashboard.summary.active_follows}`} detail="Bots currently being copied" />
          <MetricCard label="Open copied trades" value={`${dashboard.summary.open_positions}`} detail="Positions copied from bots" />
          <MetricCard label="Copied notional" value={formatUsd(dashboard.summary.copied_open_notional_usd)} detail="Current copied exposure" />
          <MetricCard
            label="Copied unrealized"
            value={formatSignedUsd(dashboard.summary.copied_unrealized_pnl_usd)}
            detail="Live PnL across open copied trades"
            tone={toneForPnl(dashboard.summary.copied_unrealized_pnl_usd)}
          />
          <MetricCard
            label="Realized 24h"
            value={formatSignedUsd(dashboard.summary.copied_realized_pnl_usd_24h)}
            detail="Realized PnL over the last 24 hours"
            tone={toneForPnl(dashboard.summary.copied_realized_pnl_usd_24h)}
          />
          <MetricCard
            label="Readiness"
            value={dashboard.readiness.can_copy ? "Ready" : "Blocked"}
            detail={dashboard.readiness.authorization_status}
            tone={dashboard.readiness.can_copy ? "text-[#74b97f]" : "text-[#dce85d]"}
          />
        </div>
      </section>

      {!dashboard.readiness.can_copy ? (
        <section className="grid gap-4 rounded-[1.75rem] border border-[#dce85d]/30 bg-[#dce85d]/10 p-5 md:p-6">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-[#eef4b0]">Setup required</span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">Copy trading needs attention</h2>
          </div>
          <div className="grid gap-2 text-sm leading-6 text-[#f5f1c7]">
            {dashboard.readiness.blockers.map((blocker) => (
              <p key={blocker}>{blocker}</p>
            ))}
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/dashboard"
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-200 transition hover:border-neutral-50 hover:text-neutral-50"
            >
              Open operations
            </Link>
          </div>
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr] xl:items-start">
        <MyCopyPortfolio follows={dashboard.follows} />
        <OpenCopyPositions positions={dashboard.positions} follows={dashboard.follows} />
      </section>

      <section className="grid gap-5 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid gap-1">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">Active follows</span>
            <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">Bots you are copying</h2>
          </div>
          <Link
            href="/marketplace"
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
          >
            Browse marketplace
          </Link>
        </div>
        {dashboard.follows.length === 0 ? (
          <article className="rounded-[1.5rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-5 py-6 text-sm leading-7 text-neutral-400">
            You are not copying any bots yet. Pick a bot below or head to the marketplace to get started.
          </article>
        ) : (
          <div className="grid gap-4">
            {dashboard.follows.map((follow) => (
              <FollowCard
                key={follow.id}
                follow={follow}
                scaleDraft={scaleDrafts[follow.id] ?? follow.scale_bps}
                saving={savingRelationshipId === follow.id}
                onScaleChange={onScaleChange}
                onSaveScale={onSaveScale}
                onResumeFollow={onResumeFollow}
                onStopFollow={onStopFollow}
              />
            ))}
          </div>
        )}
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr] xl:items-start">
        <RecentCopyActivity activity={dashboard.activity} />
        <DiscoverTraders rows={dashboard.discover} />
      </section>
    </div>
  );
}

function MetricCard({
  label,
  value,
  detail,
  tone = "text-neutral-50",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: string;
}) {
  return (
    <article className="grid gap-1 rounded-[1.35rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] px-4 py-4">
      <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</span>
      <span className={`font-mono text-[clamp(1.3rem,2vw,1.8rem)] font-bold uppercase tracking-tight ${tone}`}>{value}</span>
      <p className="text-xs leading-5 text-neutral-500">{detail}</p>
    </article>
  );
}

function MyCopyPortfolio({ follows }: { follows: CopyTradingFollow[] }) {
  const activeFollows = follows.filter((item) => item.status === "active");
  const totalExposure = activeFollows.reduce((sum, item) => sum + item.copied_open_notional_usd, 0);

  return (
    <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
      <div className="grid gap-1">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#74b97f]">My copy portfolio</span>
        <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">Allocation by bot</h2>
      </div>
      {activeFollows.length === 0 ? (
        <p className="rounded-[1.5rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-5 text-sm leading-6 text-neutral-400">
          Once you start copying bots, this is where your allocation, exposure, and account health will show up.
        </p>
      ) : (
        <div className="grid gap-3">
          {activeFollows
            .sort((left, right) => right.copied_open_notional_usd - left.copied_open_notional_usd)
            .map((follow) => {
              const share = totalExposure > 0 ? (follow.copied_open_notional_usd / totalExposure) * 100 : 0;
              return (
                <article key={follow.id} className="grid gap-3 rounded-[1.5rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="grid gap-1">
                      <span className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">{follow.source_bot_name}</span>
                      <span className="text-sm text-neutral-400">
                        {follow.creator_display_name || "Unknown creator"} · Trust {follow.source_trust_score} · Drawdown {follow.source_drawdown_pct.toFixed(1)}%
                      </span>
                    </div>
                    <span className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[#16181a] px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
                      {share.toFixed(0)}% of copied exposure
                    </span>
                  </div>
                  <div className="grid gap-2">
                    <div className="h-2 overflow-hidden rounded-full bg-[#16181a]">
                      <div className="h-full rounded-full bg-[linear-gradient(90deg,#dce85d,#74b97f)]" style={{ width: `${Math.max(share, 4)}%` }} />
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-neutral-500">
                      <span>{formatUsd(follow.copied_open_notional_usd)} open</span>
                      <span className={toneForPnl(follow.copied_unrealized_pnl_usd)}>{formatSignedUsd(follow.copied_unrealized_pnl_usd)}</span>
                    </div>
                  </div>
                </article>
              );
            })}
        </div>
      )}
    </article>
  );
}

function OpenCopyPositions({
  positions,
  follows,
}: {
  positions: CopyTradingPosition[];
  follows: CopyTradingFollow[];
}) {
  const followById = new Map(follows.map((item) => [item.id, item]));

  return (
    <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
      <div className="grid gap-1">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">Open copy positions</span>
        <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">Open positions right now</h2>
      </div>
      {positions.length === 0 ? (
        <p className="rounded-[1.5rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-5 text-sm leading-6 text-neutral-400">
          No copied positions are open right now.
        </p>
      ) : (
        <div className="grid gap-3">
          {positions.map((position) => {
            const follow = followById.get(position.relationship_id);
            return (
              <article
                key={`${position.relationship_id}-${position.symbol}-${position.side}`}
                className="grid gap-3 rounded-[1.35rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4 md:grid-cols-[0.9fr_0.8fr_0.9fr_0.8fr_0.8fr_0.9fr] md:items-center"
              >
                <div className="grid gap-1">
                  <span className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">{position.symbol}</span>
                  <span className="text-xs uppercase tracking-[0.16em] text-neutral-500">{position.side}</span>
                </div>
                <div className="grid gap-1 text-sm text-neutral-400">
                  <span>{follow?.source_bot_name || "Copied strategy"}</span>
                  <span className="text-xs text-neutral-500">{follow?.creator_display_name || "Unknown creator"}</span>
                </div>
                <DataStack label="Quantity" value={position.quantity.toFixed(4)} />
                <DataStack label="Entry / Mark" value={`${position.entry_price.toFixed(2)} / ${position.mark_price.toFixed(2)}`} />
                <DataStack label="Notional" value={formatUsd(position.notional_usd)} />
                <DataStack label="Unrealized" value={formatSignedUsd(position.unrealized_pnl_usd)} tone={toneForPnl(position.unrealized_pnl_usd)} />
              </article>
            );
          })}
        </div>
      )}
    </article>
  );
}

function DataStack({ label, value, tone = "text-neutral-50" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="grid gap-1">
      <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</span>
      <span className={`text-sm ${tone}`}>{value}</span>
    </div>
  );
}

function FollowCard({
  follow,
  scaleDraft,
  saving,
  onScaleChange,
  onSaveScale,
  onResumeFollow,
  onStopFollow,
}: {
  follow: CopyTradingFollow;
  scaleDraft: number;
  saving: boolean;
  onScaleChange: (relationshipId: string, value: number) => void;
  onSaveScale: (relationshipId: string, scaleBps: number) => void;
  onResumeFollow: (relationshipId: string, scaleBps: number) => void;
  onStopFollow: (relationshipId: string) => void;
}) {
  const scaleChanged = scaleDraft !== follow.scale_bps;
  const statusTone =
    follow.status === "active"
      ? "border-[#74b97f]/20 bg-[#74b97f]/10 text-[#74b97f]"
      : "border-[rgba(255,255,255,0.08)] bg-[#121416] text-neutral-400";

  return (
    <article className="grid gap-5 rounded-[1.8rem] border border-[rgba(255,255,255,0.06)] bg-[linear-gradient(180deg,#101214,#0b0d0e)] p-5 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[clamp(1.4rem,2vw,2rem)] font-bold uppercase tracking-tight text-neutral-50">
              {follow.source_bot_name}
            </span>
            <span className={`rounded-full border px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] ${statusTone}`}>
              {follow.status}
            </span>
            {follow.source_rank ? (
              <span className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[#121416] px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300">
                Rank #{follow.source_rank}
              </span>
            ) : null}
          </div>
          <p className="text-sm leading-6 text-neutral-400">
            {follow.creator_display_name || "Unknown creator"} · Trust {follow.source_trust_score} · Drawdown {follow.source_drawdown_pct.toFixed(1)}% · Last sync{" "}
            {follow.last_execution_at ? new Date(follow.last_execution_at).toLocaleString() : "Waiting for first trade"}
          </p>
        </div>

        <div className="grid min-w-[12rem] gap-1 rounded-[1.35rem] border border-[rgba(255,255,255,0.06)] bg-[#141618] px-4 py-3 text-right">
          <span className="text-[0.6rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Open copied exposure</span>
          <span className="text-lg text-neutral-300">{formatUsd(follow.copied_open_notional_usd)}</span>
          <span className={`font-mono text-2xl font-bold tracking-tight ${toneForPnl(follow.copied_unrealized_pnl_usd)}`}>
            {formatSignedUsd(follow.copied_unrealized_pnl_usd)}
          </span>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(20rem,0.9fr)]">
        <section className="grid gap-4 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#17191b] p-4 md:p-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="grid gap-1">
              <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Copy size</span>
              <span className="font-mono text-4xl font-bold uppercase tracking-tight text-neutral-50">{formatScale(scaleDraft)}</span>
            </div>
            <span className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[#101214] px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
              {follow.copied_position_count} open positions
            </span>
          </div>
          <input
            type="range"
            min={500}
            max={30000}
            step={500}
            value={scaleDraft}
            onChange={(event) => onScaleChange(follow.id, Number(event.target.value))}
            className="accent-[#dce85d]"
          />
          <div className="flex items-center justify-between text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
            <span>Min 5%</span>
            <span>Max 300%</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <MetricStack label="Trader health" value={follow.source_health || "Unknown"} />
            <MetricStack label="Sync status" value={follow.source_drift_status || "Unknown"} />
            <MetricStack label="Latest symbol" value={follow.last_execution_symbol || "None yet"} />
          </div>
        </section>

        <section className="grid gap-3 rounded-[1.6rem] border border-[rgba(255,255,255,0.06)] bg-[#121416] p-4 md:p-5">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">Actions</span>
          <div className="grid gap-2">
            <button
              type="button"
              onClick={() => onSaveScale(follow.id, scaleDraft)}
              disabled={saving || !scaleChanged}
              className="inline-flex h-12 items-center justify-center rounded-[1rem] bg-[#8c9440] px-4 text-[0.62rem] font-semibold uppercase tracking-[0.14em] text-[#090a0a] transition hover:bg-[#a3ad4b] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving && scaleChanged ? "Saving..." : scaleChanged ? "Save size" : "Size saved"}
            </button>
            {follow.status === "active" ? (
              <button
                type="button"
                onClick={() => onStopFollow(follow.id)}
                disabled={saving}
                className="inline-flex h-12 items-center justify-center rounded-[1rem] border border-[rgba(255,255,255,0.1)] bg-[#0f1113] px-4 text-[0.62rem] font-semibold uppercase tracking-[0.14em] text-neutral-300 transition hover:border-[#ff8a9b] hover:text-[#ff8a9b] disabled:opacity-50"
              >
                {saving ? "Pausing..." : "Pause copying"}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onResumeFollow(follow.id, scaleDraft)}
                disabled={saving}
                className="inline-flex h-12 items-center justify-center rounded-[1rem] border border-[rgba(255,255,255,0.1)] bg-[#0f1113] px-4 text-[0.62rem] font-semibold uppercase tracking-[0.14em] text-neutral-300 transition hover:border-[#74b97f] hover:text-[#74b97f] disabled:opacity-50"
              >
                {saving ? "Resuming..." : "Resume copying"}
              </button>
            )}
            <Link
              href={`/marketplace/${follow.source_runtime_id}`}
              className="inline-flex h-12 items-center justify-center rounded-[1rem] border border-[rgba(255,255,255,0.1)] bg-[#0f1113] px-4 text-[0.62rem] font-semibold uppercase tracking-[0.14em] text-neutral-300 transition hover:border-neutral-50 hover:text-neutral-50"
            >
              View profile
            </Link>
          </div>
        </section>
      </div>
    </article>
  );
}

function MetricStack({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 rounded-[1.1rem] border border-[rgba(255,255,255,0.05)] bg-[#101214] px-3 py-3">
      <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">{label}</span>
      <span className="text-sm font-medium text-neutral-100">{value}</span>
    </div>
  );
}

function RecentCopyActivity({ activity }: { activity: CopyTradingActivity[] }) {
  return (
    <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
      <div className="grid gap-1">
        <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-400">Recent copy activity</span>
        <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">Recent execution activity</h2>
      </div>
      {activity.length === 0 ? (
        <p className="rounded-[1.5rem] border border-dashed border-[rgba(255,255,255,0.08)] bg-[#0d0f10] px-4 py-5 text-sm leading-6 text-neutral-400">
          No copy activity yet.
        </p>
      ) : (
        <div className="grid gap-3">
          {activity.map((item) => (
            <article key={item.id ?? `${item.symbol}-${item.created_at}`} className="grid gap-2 rounded-[1.35rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4 md:grid-cols-[0.9fr_0.9fr_0.8fr_1.1fr] md:items-center">
              <div className="grid gap-1">
                <span className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">{item.symbol || "Activity"}</span>
                <span className="text-xs uppercase tracking-[0.16em] text-neutral-500">{(item.action_type || "copy_event").replaceAll("_", " ")}</span>
              </div>
              <div className="text-sm text-neutral-400">
                {item.side || "n/a"} · {item.copied_quantity > 0 ? item.copied_quantity.toFixed(4) : "0.0000"}
              </div>
              <div className={`text-sm font-semibold ${item.status === "mirrored" ? "text-[#74b97f]" : item.status === "error" ? "text-[#ff8a9b]" : "text-neutral-300"}`}>
                {item.status || "pending"}
              </div>
              <div className="text-xs leading-5 text-neutral-500">
                {item.error_reason || (item.created_at ? new Date(item.created_at).toLocaleString() : "Awaiting timestamp")}
              </div>
            </article>
          ))}
        </div>
      )}
    </article>
  );
}

function DiscoverTraders({ rows }: { rows: CopyTradingDiscoverRow[] }) {
  return (
    <article className="grid gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-5 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="grid gap-1">
          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">Discover bots</span>
          <h2 className="font-mono text-2xl font-bold uppercase tracking-tight text-neutral-50">Bots worth watching</h2>
        </div>
        <Link
          href="/marketplace"
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
        >
          Open marketplace
        </Link>
      </div>
      <div className="grid gap-3">
        {rows.map((row) => (
          <Link
            key={row.runtime_id || row.bot_definition_id || row.bot_name}
            href={row.runtime_id ? `/marketplace/${row.runtime_id}` : "/marketplace"}
            className="grid gap-3 rounded-[1.35rem] border border-[rgba(255,255,255,0.06)] bg-[#0d0f10] p-4 transition hover:border-[#dce85d]/30 hover:bg-[#121416]"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="grid gap-1">
                <span className="font-mono text-lg font-bold uppercase tracking-tight text-neutral-50">{row.bot_name || "Unknown trader"}</span>
                <span className="text-sm text-neutral-400">{row.creator_display_name || "Unknown creator"} · {row.strategy_type || "Strategy"}</span>
              </div>
              {row.rank ? (
                <span className="font-mono text-xl font-bold text-[#dce85d]">#{row.rank}</span>
              ) : null}
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <DataStack label="Trust" value={`${row.trust_score}`} />
              <DataStack label="Drawdown" value={`${row.drawdown.toFixed(1)}%`} />
              <DataStack label="Route" value="Open profile" tone="text-[#74b97f]" />
            </div>
          </Link>
        ))}
      </div>
    </article>
  );
}
