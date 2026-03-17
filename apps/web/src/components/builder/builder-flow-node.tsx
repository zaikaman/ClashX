"use client";

import { Handle, type NodeProps, Position, useReactFlow } from "@xyflow/react";
import { X } from "lucide-react";

import {
  actionSummary,
  actionTitle,
  conditionSummary,
  conditionTitle,
  type BuilderFlowNode,
  type BuilderNodeData,
} from "@/components/builder/builder-flow-utils";

function nodeTitle(data: BuilderNodeData) {
  if (data.kind === "entry") {
    return "Draft start";
  }
  if (data.kind === "condition") {
    return conditionTitle(data.condition.type);
  }
  return actionTitle(data.action.type);
}

function nodeSummary(data: BuilderNodeData) {
  if (data.kind === "entry") {
    return "Connect this anchor into the first node on the route you want the runtime to follow.";
  }
  if (data.kind === "condition") {
    return conditionSummary(data.condition);
  }
  return actionSummary(data.action);
}

export function BuilderFlowNodeCard({ data, id }: NodeProps<BuilderFlowNode>) {
  const { setNodes, setEdges } = useReactFlow();
  const isEntry = data.kind === "entry";
  const isCondition = data.kind === "condition";

  const kicker = data.stageLabel ?? (isEntry ? "Start" : isCondition ? "Signal node" : "Action node");
  const badgeTone = isEntry
    ? "bg-[color:color-mix(in_oklch,var(--mint)_22%,transparent)] text-[#74b97f]"
    : isCondition
      ? "bg-[color:color-mix(in_oklch,var(--accent)_18%,transparent)] text-[#dce85d]"
      : "bg-[color:color-mix(in_oklch,var(--mint)_20%,transparent)] text-[#74b97f]";
  const handleTone = isEntry
    ? "!bg-[#74b97f]"
    : isCondition
      ? "!bg-[#dce85d]"
      : "!bg-[#74b97f]";

  function handleRemove(e: React.MouseEvent) {
    e.stopPropagation();
    setNodes((nds) => nds.filter((n) => n.id !== id));
    setEdges((eds) => eds.filter((edge) => edge.source !== id && edge.target !== id));
  }

  return (
    <div
      className={`relative min-w-[16.25rem] max-w-[17.5rem] rounded-2xl border px-4 py-4 shadow-[0_18px_42px_rgba(0,0,0,0.18)] transition group ${data.active
        ? "border-[#dce85d] bg-[#dce85d]/10"
        : data.primary
          ? "border-[color:color-mix(in_oklch,var(--mint)_46%,var(--line))] bg-[color:color-mix(in_oklch,var(--bg-raised)_78%,var(--mint)_22%)]"
          : "border-[rgba(255,255,255,0.06)] bg-[#16181a]"
        }`}
    >
      {!isEntry ? (
        <button
          onClick={handleRemove}
          className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-[#16181a] border border-[rgba(255,255,255,0.1)] text-neutral-400 hover:text-neutral-50 hover:bg-[#e06c6e] hover:border-[#e06c6e] transition-all flex items-center justify-center z-10"
        >
          <X className="w-3 h-3" />
        </button>
      ) : null}

      {!isEntry ? (
        <Handle
          type="target"
          position={Position.Left}
          className="!h-3 !w-3 !border-2 !border-[#090a0a] !bg-[rgba(255,255,255,0.12)]"
        />
      ) : null}

      <div className="grid gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="grid gap-1">
            <span className="text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
              {kicker}
            </span>
            <div className="font-mono text-sm font-bold uppercase tracking-[0.08em] text-neutral-50">
              {nodeTitle(data)}
            </div>
          </div>
          <span className={`rounded-full px-2 py-1 text-[0.55rem] font-semibold uppercase tracking-[0.16em] ${badgeTone}`}>
            {isEntry ? "Anchor" : data.primary ? "Primary" : "Branch"}
          </span>
        </div>

        <p className="text-sm leading-6 text-neutral-400">{nodeSummary(data)}</p>

        <div className="flex flex-wrap gap-2">
          {data.branchCount > 1 ? (
            <span className="rounded-full border border-[rgba(255,255,255,0.06)] px-2 py-1 text-[0.55rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
              {data.branchCount} branches
            </span>
          ) : null}
          <span className="rounded-full border border-[rgba(255,255,255,0.06)] px-2 py-1 text-[0.55rem] font-semibold uppercase tracking-[0.16em] text-neutral-500">
            {isEntry ? "Connect the route" : "Drag to reposition"}
          </span>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className={`!h-3 !w-3 !border-2 !border-[#090a0a] ${handleTone}`}
      />
    </div>
  );
}
