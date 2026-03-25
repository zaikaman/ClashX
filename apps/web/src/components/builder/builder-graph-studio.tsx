"use client";

import { useSearchParams } from "next/navigation";
import {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  type Connection,
  type ReactFlowInstance,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type XYPosition,
} from "@xyflow/react";
import { Box, Sparkles, Grid3x3, Activity, Play, Search, ChevronDown, ChevronRight, Plus, Globe, Check, ArrowUp, RefreshCcw, Download, Upload } from "lucide-react";
import { clsx } from "clsx";
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from "react";

import { BuilderFlowNodeCard } from "@/components/builder/builder-flow-node";
import {
  ACTION_OPTIONS,
  actionHelper,
  actionSummary,
  actionTitle,
  BLANK_BUILDER_TEMPLATE_ID,
  BOT_MARKET_UNIVERSE_SYMBOL,
  buildGraphFromAiDraft,
  BUILDER_STARTER_TEMPLATES,
  buildBlankGraph,
  buildDefaultGraph,
  buildPrimaryRoute,
  CONDITION_OPTIONS,
  conditionHelper,
  conditionSummary,
  conditionTitle,
  createAction,
  createActionNode,
  createCondition,
  createConditionNode,
  createEntryNode,
  DEFAULT_BUILDER_TEMPLATE_ID,
  ENTRY_NODE_ID,
  getBuilderStarterTemplate,
  PALETTE_MIME,
  parseOptionalNumber,
  serializeGraphNode,
  snapPosition,
  type BuilderAiDraft,
  type BuilderFlowEdge,
  type BuilderFlowNode,
  type PaletteDragPayload,
  type VisualAction,
  type VisualCondition,
} from "@/components/builder/builder-flow-utils";
import { type PacificaOnboardingStatus } from "@/components/pacifica/onboarding-checklist";
import { useClashxAuth } from "@/lib/clashx-auth";
import {
  PacificaReadinessError,
  assertPacificaDeployReadiness,
} from "@/lib/pacifica-readiness";

type BuilderCatalogTemplate = {
  id: string;
  name: string;
  description: string;
  authoring_mode?: string;
  risk_profile?: string;
};
type BuilderMarket = { symbol: string; status: string; volume_24h?: number; max_leverage?: number };
export type BuilderNoticePayload = {
  eyebrow: string;
  title: string;
  detail: string;
};
type BuilderChatMode = "visual" | "ai";
type BuilderChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};
type BuilderAiRouteResponse = {
  reply: string;
  draft: BuilderAiDraft;
};
type BuilderBotDefinition = {
  id: string;
  name: string;
  description: string;
  wallet_address: string;
  visibility: "private" | "public" | "unlisted";
  authoring_mode: string;
  strategy_type: string;
  market_scope: string;
  rules_json: Record<string, unknown>;
};
type SavedBuilderBot = {
  id: string;
  name: string;
  description: string;
  visibility: string;
  market_scope: string;
  updated_at: string;
};
type PortableBuilderNode = {
  id: string;
  kind: "entry" | "condition" | "action";
  position: XYPosition;
  config?: Record<string, unknown>;
};
type PortableBuilderEdge = {
  id?: string;
  source: string;
  target: string;
};
type PortableBuilderDraft = {
  format: "clashx-builder-draft";
  version: 1;
  exported_at: string;
  draft: {
    name: string;
    description: string;
    visibility: "private" | "public" | "unlisted";
    selected_market_symbols: string[];
    active_template_id?: string;
    builder_mode?: BuilderChatMode;
    graph: {
      nodes: PortableBuilderNode[];
      edges: PortableBuilderEdge[];
    };
  };
};
type RuntimeControlPreset = "guarded" | "balanced" | "aggressive";
type RuntimeControlsFormState = {
  maxLeverage: number;
  maxOrderSizeUsd: number;
  allocatedCapitalUsd: number;
  cooldownSeconds: number;
  maxDrawdownPct: number;
  sizingMode: "fixed_usd" | "risk_adjusted";
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const nodeTypes = { builderNode: BuilderFlowNodeCard };
const PRIMARY_EDGE_COLOR = "#74b97f";
const SECONDARY_EDGE_COLOR = "rgba(255,255,255,0.22)";
const TIMEFRAME_OPTIONS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"] as const;
const SIDE_OPTIONS = ["long", "short"] as const;
const TIF_OPTIONS = ["GTC", "IOC", "FOK"] as const;

const SIGNAL_CATEGORIES = [
  {
    name: "Price & Trend",
    keys: ["price_above", "price_below", "price_change_pct_above", "price_change_pct_below", "sma_above", "sma_below", "vwap_above", "vwap_below", "higher_timeframe_sma_above", "higher_timeframe_sma_below", "ema_crosses_above", "ema_crosses_below", "macd_crosses_above_signal", "macd_crosses_below_signal"]
  },
  {
    name: "Momentum & Volatility",
    keys: ["rsi_above", "rsi_below", "volatility_above", "volatility_below", "bollinger_above_upper", "bollinger_below_lower", "breakout_above_recent_high", "breakout_below_recent_low", "atr_above", "atr_below"]
  },
  {
    name: "Context & Controls",
    keys: ["has_position", "position_side_is", "position_pnl_above", "position_pnl_below", "position_pnl_pct_above", "position_pnl_pct_below", "position_in_profit", "position_in_loss", "funding_rate_above", "funding_rate_below", "volume_above", "volume_below", "cooldown_elapsed"]
  }
];

const ACTION_CATEGORIES = [
  {
    name: "Execution",
    keys: ["open_long", "open_short", "place_market_order", "place_limit_order", "place_twap_order"]
  },
  {
    name: "Position & Orders",
    keys: ["close_position", "set_tpsl", "update_leverage", "cancel_order", "cancel_twap_order", "cancel_all_orders"]
  }
];
const DEFAULT_RUNTIME_CONTROLS: RuntimeControlsFormState = {
  maxLeverage: 5,
  maxOrderSizeUsd: 200,
  allocatedCapitalUsd: 200,
  cooldownSeconds: 45,
  maxDrawdownPct: 18,
  sizingMode: "fixed_usd",
};
const RUNTIME_CONTROL_PRESETS: Array<{
  id: RuntimeControlPreset;
  label: string;
  description: string;
  values: RuntimeControlsFormState;
}> = [
    {
      id: "guarded",
      label: "Guarded",
      description: "Lower leverage, slower re-entry, tighter drawdown cap.",
      values: {
        maxLeverage: 3,
        maxOrderSizeUsd: 120,
        allocatedCapitalUsd: 150,
        cooldownSeconds: 120,
        maxDrawdownPct: 10,
        sizingMode: "fixed_usd",
      },
    },
    {
      id: "balanced",
      label: "Balanced",
      description: "A steady default for most momentum and swing bots.",
      values: DEFAULT_RUNTIME_CONTROLS,
    },
    {
      id: "aggressive",
      label: "Aggressive",
      description: "Higher leverage and faster cycling for advanced setups.",
      values: {
        maxLeverage: 8,
        maxOrderSizeUsd: 350,
        allocatedCapitalUsd: 400,
        cooldownSeconds: 20,
        maxDrawdownPct: 24,
        sizingMode: "risk_adjusted",
      },
    },
  ];

function BlockCategory({
  title,
  icon: Icon,
  options,
  searchQuery,
  kind,
  onDragStart,
  defaultExpanded = false,
}: {
  title: string;
  icon: any;
  options: string[];
  searchQuery: string;
  kind: "condition" | "action";
  onDragStart: (payload: PaletteDragPayload, event: DragEvent<HTMLDivElement>) => void;
  defaultExpanded?: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const expanded = searchQuery ? options.length > 0 : isExpanded;

  if (options.length === 0) return null;

  return (
    <div className="mb-6 last:mb-0">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between py-1 hover:text-neutral-200 text-neutral-400 group transition-colors"
      >
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4" />
          <span className="text-[0.65rem] font-bold uppercase tracking-[0.12em]">{title}</span>
        </div>
        <div className="rounded-md bg-[rgba(255,255,255,0.03)] p-0.5 group-hover:bg-[rgba(255,255,255,0.08)] transition-colors">
          {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        </div>
      </button>

      {expanded && (
        <div className="mt-3 space-y-3">
          {options.map((option) => (
            <PaletteCard
              key={option}
              title={kind === "condition" ? conditionTitle(option) : actionTitle(option)}
              helper={kind === "condition" ? conditionHelper(option) : actionHelper(option)}
              accent={
                kind === "condition"
                  ? "border-[rgba(255,255,255,0.06)] border hover:border-[#dce85d]/50 bg-[#0c0d0d]"
                  : "border-[rgba(255,255,255,0.06)] border hover:border-[#74b97f]/50 bg-[#0c0d0d]"
              }
              onDragStart={(evt) => onDragStart({ kind, blockType: option }, evt)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function PaletteCard({
  title,
  helper,
  accent,
  onDragStart,
}: {
  title: string;
  helper: string;
  accent: string;
  onDragStart: (event: DragEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      className="grid cursor-grab gap-2 rounded-2xl border border-[rgba(255,255,255,0.06)] bg-[#090a0a] p-4 transition hover:border-[rgba(255,255,255,0.12)]"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-sm font-bold uppercase tracking-[0.08em] text-neutral-50">
          {title}
        </span>
        <span className={`rounded-full px-2 py-0.5 text-[0.55rem] font-semibold uppercase tracking-[0.16em] ${accent}`}>
          Drag
        </span>
      </div>
      <p className="text-sm leading-6 text-neutral-400">{helper}</p>
    </div>
  );
}

function trimSentence(value: string) {
  return value.endsWith(".") ? value.slice(0, -1) : value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function sanitizeDraftFileName(value: string) {
  const base = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return base || "clashx-bot-draft";
}

function buildCanvasFromSerializedGraph(graph: {
  nodes: PortableBuilderNode[];
  edges: PortableBuilderEdge[];
}) {
  const nextNodes: BuilderFlowNode[] = [];
  const nextEdges: BuilderFlowEdge[] = [];
  const nodeIdMap = new Map<string, string>();
  let importedEntryPosition: XYPosition | null = null;

  for (const node of graph.nodes) {
    if (node.kind === "entry") {
      nodeIdMap.set(node.id, ENTRY_NODE_ID);
      importedEntryPosition = snapPosition(node.position);
      continue;
    }

    if (!isRecord(node.config) || typeof node.config.type !== "string") {
      throw new Error("One of the imported blocks is missing its type.");
    }

    if (node.kind === "condition") {
      if (!CONDITION_OPTIONS.includes(node.config.type as (typeof CONDITION_OPTIONS)[number])) {
        throw new Error(`Unsupported condition type: ${node.config.type}`);
      }
      const baseCondition = createCondition(node.config.type as (typeof CONDITION_OPTIONS)[number]);
      const condition: VisualCondition = {
        ...baseCondition,
        ...(node.config as Partial<VisualCondition>),
        id: baseCondition.id,
        type: node.config.type,
        symbol: typeof node.config.symbol === "string" && node.config.symbol.trim() ? node.config.symbol : baseCondition.symbol,
      };
      const nextNode = createConditionNode(condition, snapPosition(node.position));
      nextNodes.push(nextNode);
      nodeIdMap.set(node.id, nextNode.id);
      continue;
    }

    if (!ACTION_OPTIONS.includes(node.config.type as (typeof ACTION_OPTIONS)[number])) {
      throw new Error(`Unsupported action type: ${node.config.type}`);
    }
    const baseAction = createAction(node.config.type as (typeof ACTION_OPTIONS)[number]);
    const action: VisualAction = {
      ...baseAction,
      ...(node.config as Partial<VisualAction>),
      id: baseAction.id,
      type: node.config.type,
      symbol: typeof node.config.symbol === "string" && node.config.symbol.trim() ? node.config.symbol : baseAction.symbol,
    };
    const nextNode = createActionNode(action, snapPosition(node.position));
    nextNodes.push(nextNode);
    nodeIdMap.set(node.id, nextNode.id);
  }

  const entryNode = createEntryNode();
  if (importedEntryPosition) {
    entryNode.position = importedEntryPosition;
  }
  nextNodes.unshift(entryNode);

  graph.edges.forEach((edge, index) => {
    const source = nodeIdMap.get(edge.source);
    const target = nodeIdMap.get(edge.target);
    if (!source || !target) {
      throw new Error("The draft has broken graph connections.");
    }
    if (source === target) {
      return;
    }
    nextEdges.push({
      id: edge.id ?? `imported-edge-${index + 1}`,
      source,
      target,
      type: "smoothstep",
    });
  });

  return {
    nodes: nextNodes,
    edges: nextEdges,
    selectedNodeId: nextNodes.find((node) => node.data.kind !== "entry")?.id ?? null,
  };
}

function normalizeMarketSymbol(symbol: string) {
  return symbol.trim().toUpperCase().replace("-PERP", "");
}

function parseMarketScopeSelection(scope: string) {
  const normalized = scope.trim();
  if (!normalized) return [];
  const lower = normalized.toLowerCase();
  if (lower.includes("all pacifica")) return [];

  const parts = normalized
    .split("/")
    .at(-1)
    ?.split(",")
    .map((part) => normalizeMarketSymbol(part))
    .filter(Boolean);

  return parts?.length ? parts : [];
}

function summarizeMarketScope(selectedSymbols: string[], availableSymbols: string[]) {
  if (availableSymbols.length > 0 && selectedSymbols.length === availableSymbols.length) {
    return "All Pacifica perpetuals";
  }
  if (selectedSymbols.length === 0) {
    return "Choose markets";
  }
  if (selectedSymbols.length <= 3) {
    return `Pacifica perpetuals / ${selectedSymbols.join(", ")}`;
  }
  return `${selectedSymbols.length} Pacifica markets`;
}

function findSelectedMarketLeverageCap(selectedSymbols: string[], markets: BuilderMarket[]) {
  const selected = new Set(selectedSymbols.map((symbol) => normalizeMarketSymbol(symbol)).filter(Boolean));
  if (selected.size === 0) return null;

  let tightestMarket: { symbol: string; maxLeverage: number } | null = null;
  for (const market of markets) {
    const symbol = normalizeMarketSymbol(market.symbol);
    const maxLeverage = Number(market.max_leverage ?? 0);
    if (!selected.has(symbol) || maxLeverage <= 0) continue;
    if (!tightestMarket || maxLeverage < tightestMarket.maxLeverage) {
      tightestMarket = { symbol, maxLeverage };
    }
  }
  return tightestMarket;
}

function buildRiskPolicyPayload(selectedSymbols: string[], runtimeControls: RuntimeControlsFormState) {
  return {
    max_leverage: runtimeControls.maxLeverage,
    max_order_size_usd: runtimeControls.maxOrderSizeUsd,
    allocated_capital_usd: runtimeControls.allocatedCapitalUsd,
    cooldown_seconds: runtimeControls.cooldownSeconds,
    max_drawdown_pct: runtimeControls.maxDrawdownPct,
    allowed_symbols: selectedSymbols,
    sizing_mode: runtimeControls.sizingMode,
  };
}

function validateRuntimeControls(
  preset: RuntimeControlPreset | null,
  runtimeControls: RuntimeControlsFormState,
  selectedSymbols: string[],
  markets: BuilderMarket[],
) {
  if (!preset) return "Choose a runtime profile before deploying.";
  if (runtimeControls.maxLeverage < 1) return "Max leverage must be at least 1.";
  const leverageCap = findSelectedMarketLeverageCap(selectedSymbols, markets);
  if (leverageCap && runtimeControls.maxLeverage > leverageCap.maxLeverage) {
    return `Max leverage must be ${leverageCap.maxLeverage} or lower for ${leverageCap.symbol}.`;
  }
  if (runtimeControls.maxOrderSizeUsd < 1) return "Max order size must be greater than 0.";
  if (runtimeControls.allocatedCapitalUsd < 1) return "Allocated capital must be greater than 0.";
  if (runtimeControls.cooldownSeconds < 0) return "Cooldown cannot be negative.";
  if (runtimeControls.maxDrawdownPct < 0) return "Max drawdown cannot be negative.";
  return null;
}

function buildPersistedGraph(nodes: BuilderFlowNode[], edges: BuilderFlowEdge[], selectedSymbols: string[]) {
  const serializedNodes = nodes.map((node) => serializeGraphNode(node));
  const universeSymbols = selectedSymbols.filter(Boolean);
  const universeNodeIds = new Set(
    serializedNodes
      .filter((node) => node.kind !== "entry" && node.config?.symbol === BOT_MARKET_UNIVERSE_SYMBOL)
      .map((node) => node.id),
  );

  if (universeNodeIds.size === 0) {
    return {
      nodes: serializedNodes,
      edges: edges.map(({ id, source, target }) => ({ id, source, target })),
    };
  }

  const expandedNodes: Array<{ id: string; kind: string; position: { x: number; y: number }; config?: Record<string, unknown> }> = [];

  for (const node of serializedNodes) {
    if (!universeNodeIds.has(node.id)) {
      expandedNodes.push(node);
      continue;
    }
    for (const symbol of universeSymbols) {
      expandedNodes.push({
        ...node,
        id: `${node.id}::${symbol}`,
        config: node.config ? { ...node.config, symbol } : undefined,
      });
    }
  }

  const expandedEdges: Array<{ id: string; source: string; target: string }> = [];
  for (const edge of edges) {
    const sourceUniverse = universeNodeIds.has(edge.source);
    const targetUniverse = universeNodeIds.has(edge.target);

    if (sourceUniverse && targetUniverse) {
      for (const symbol of universeSymbols) {
        expandedEdges.push({
          id: `${edge.id}::${symbol}`,
          source: `${edge.source}::${symbol}`,
          target: `${edge.target}::${symbol}`,
        });
      }
      continue;
    }

    if (sourceUniverse) {
      for (const symbol of universeSymbols) {
        expandedEdges.push({
          id: `${edge.id}::${symbol}`,
          source: `${edge.source}::${symbol}`,
          target: edge.target,
        });
      }
      continue;
    }

    if (targetUniverse) {
      for (const symbol of universeSymbols) {
        expandedEdges.push({
          id: `${edge.id}::${symbol}`,
          source: edge.source,
          target: `${edge.target}::${symbol}`,
        });
      }
      continue;
    }

    expandedEdges.push({ id: edge.id, source: edge.source, target: edge.target });
  }

  const expandedNodeIds = new Set(expandedNodes.map((node) => node.id));
  const filteredEdges = expandedEdges.filter((edge) => expandedNodeIds.has(edge.source) && expandedNodeIds.has(edge.target));

  return {
    nodes: expandedNodes,
    edges: filteredEdges,
  };
}

export function BuilderGraphStudio({
  onNotice,
  onboardingStatus,
  onOpenOnboardingGuide,
  onWalletAddressChange,
}: {
  onNotice?: (notice: BuilderNoticePayload) => void;
  onboardingStatus: PacificaOnboardingStatus;
  onOpenOnboardingGuide?: () => void;
  onWalletAddressChange?: (walletAddress: string) => void;
}) {
  const searchParams = useSearchParams();
  const requestedBotId = searchParams.get("botId");
  const { authenticated, login, walletAddress: authenticatedWallet, getAuthHeaders } = useClashxAuth();
  const initialTemplate = getBuilderStarterTemplate(DEFAULT_BUILDER_TEMPLATE_ID);
  const initialGraph = useMemo(() => buildDefaultGraph(), []);

  const [catalogTemplates, setCatalogTemplates] = useState<BuilderCatalogTemplate[]>([]);
  const [markets, setMarkets] = useState<BuilderMarket[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<BuilderFlowNode>(initialGraph.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<BuilderFlowEdge>(initialGraph.edges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(initialGraph.nodes.find((node) => node.data.kind !== "entry")?.id ?? null);
  const [activeTemplateId, setActiveTemplateId] = useState(initialTemplate.id);
  const [flow, setFlow] = useState<ReactFlowInstance<BuilderFlowNode, BuilderFlowEdge> | null>(null);
  const [walletAddress, setWalletAddress] = useState("");
  const [name, setName] = useState(initialTemplate.name);
  const [description, setDescription] = useState(initialTemplate.description);
  const [visibility, setVisibility] = useState<"private" | "public" | "unlisted">("private");
  const [selectedMarketSymbols, setSelectedMarketSymbols] = useState<string[]>(
    parseMarketScopeSelection(initialTemplate.marketScope).length
      ? parseMarketScopeSelection(initialTemplate.marketScope)
      : ["BTC"],
  );
  const [createdBotId, setCreatedBotId] = useState<string | null>(null);
  const [, setRuntimeStatus] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "creating" | "deploying">("idle");
  const [error, setError] = useState<string | null>(null);
  const [blockSearch, setBlockSearch] = useState("");
  const [builderMode, setBuilderMode] = useState<BuilderChatMode>("visual");
  const [chatMessages, setChatMessages] = useState<BuilderChatMessage[]>([
    {
      id: "assistant-welcome",
      role: "assistant",
      content: "Describe the bot you want and I’ll turn it into a draft with signals, actions, and market scope.",
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [chatStatus, setChatStatus] = useState<"idle" | "sending">("idle");
  const chatViewportRef = useRef<HTMLDivElement | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const [loadingBotId, setLoadingBotId] = useState<string | null>(null);
  const [loadedBotId, setLoadedBotId] = useState<string | null>(null);
  const [savedBots, setSavedBots] = useState<SavedBuilderBot[]>([]);
  const [savedBotsLoading, setSavedBotsLoading] = useState(false);
  const [savedBotsOpen, setSavedBotsOpen] = useState(false);
  const [runtimeControlsOpen, setRuntimeControlsOpen] = useState(false);
  const [runtimePreset, setRuntimePreset] = useState<RuntimeControlPreset | null>(null);
  const [runtimeControls, setRuntimeControls] = useState<RuntimeControlsFormState>({ ...DEFAULT_RUNTIME_CONTROLS });
  const [runtimeControlsError, setRuntimeControlsError] = useState<string | null>(null);

  useEffect(() => {
    if (authenticatedWallet) setWalletAddress(authenticatedWallet);
  }, [authenticatedWallet]);

  useEffect(() => {
    onWalletAddressChange?.(walletAddress.trim());
  }, [onWalletAddressChange, walletAddress]);

  useEffect(() => {
    const controller = new AbortController();

    void (async () => {
      const [templatesResponse, marketsResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/builder/templates`, { signal: controller.signal }),
        fetch(`${API_BASE_URL}/api/builder/markets`, { signal: controller.signal }),
      ]);
      if (templatesResponse.ok) setCatalogTemplates((await templatesResponse.json()) as BuilderCatalogTemplate[]);
      if (marketsResponse.ok) setMarkets((await marketsResponse.json()) as BuilderMarket[]);
    })();

    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!authenticated || !walletAddress) {
      setSavedBots([]);
      setSavedBotsOpen(false);
      return;
    }

    let cancelled = false;

    async function loadSavedBots() {
      setSavedBotsLoading(true);
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/bots?wallet_address=${encodeURIComponent(walletAddress)}&include_performance=false`,
          { cache: "no-store", headers: await getAuthHeaders() },
        );
        const payload = (await response.json()) as SavedBuilderBot[] | { detail?: string };
        if (!response.ok) {
          throw new Error("detail" in payload ? payload.detail ?? "Could not load saved bots" : "Could not load saved bots");
        }
        if (!cancelled) {
          setSavedBots(
            [...(payload as SavedBuilderBot[])].sort(
              (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
            ),
          );
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Could not load saved bots");
        }
      } finally {
        if (!cancelled) {
          setSavedBotsLoading(false);
        }
      }
    }

    void loadSavedBots();

    return () => {
      cancelled = true;
    };
  }, [authenticated, walletAddress, getAuthHeaders]);

  const loadBotIntoBuilder = useCallback(async (botId: string) => {
    if (!authenticated || !walletAddress) {
      login();
      return;
    }

    setLoadingBotId(botId);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/bots/${botId}?wallet_address=${encodeURIComponent(walletAddress)}`,
        { cache: "no-store", headers: await getAuthHeaders() },
      );
      const payload = (await response.json()) as BuilderBotDefinition | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Could not load bot draft" : "Could not load bot draft");
      }

      const bot = payload as BuilderBotDefinition;
      const graphPayload = isRecord(bot.rules_json.graph) ? bot.rules_json.graph : null;
      if (!graphPayload || !Array.isArray(graphPayload.nodes) || !Array.isArray(graphPayload.edges)) {
        throw new Error("This saved bot does not include an editable builder graph.");
      }

      const nextGraph = buildCanvasFromSerializedGraph({
        nodes: graphPayload.nodes as PortableBuilderNode[],
        edges: graphPayload.edges as PortableBuilderEdge[],
      });

      setNodes(nextGraph.nodes);
      setEdges(nextGraph.edges);
      setSelectedNodeId(nextGraph.selectedNodeId);
      setActiveTemplateId(BLANK_BUILDER_TEMPLATE_ID);
      setWalletAddress(bot.wallet_address);
      setName(bot.name);
      setDescription(bot.description);
      setVisibility(bot.visibility);
      setSelectedMarketSymbols(
        parseMarketScopeSelection(bot.market_scope).length
          ? parseMarketScopeSelection(bot.market_scope)
          : ["BTC"],
      );
      setCreatedBotId(bot.id);
      setLoadedBotId(bot.id);
      setRuntimeStatus(null);
      setError(null);
      setBlockSearch("");
      setSavedBotsOpen(false);

      requestAnimationFrame(() => {
        flow?.fitView({ padding: 0.18, duration: 280 });
      });

      onNotice?.({
        eyebrow: "Loaded",
        title: "Saved bot ready",
        detail: "You can edit this draft and save over it whenever you're ready.",
      });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Could not load bot draft");
    } finally {
      setLoadingBotId(null);
    }
  }, [authenticated, flow, getAuthHeaders, login, onNotice, setEdges, setNodes, walletAddress]);

  useEffect(() => {
    if (!authenticated || !walletAddress || !requestedBotId || requestedBotId === loadedBotId || requestedBotId === loadingBotId) {
      return;
    }
    void loadBotIntoBuilder(requestedBotId);
  }, [authenticated, walletAddress, requestedBotId, loadedBotId, loadingBotId, loadBotIntoBuilder]);

  useEffect(() => {
    if (selectedNodeId && nodes.some((node) => node.id === selectedNodeId && node.data.kind !== "entry")) return;
    setSelectedNodeId(nodes.find((node) => node.data.kind !== "entry")?.id ?? null);
  }, [nodes, selectedNodeId]);

  useEffect(() => {
    const viewport = chatViewportRef.current;
    if (!viewport) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, [chatMessages]);

  const route = useMemo(() => buildPrimaryRoute(nodes, edges), [nodes, edges]);
  const primaryNodeIds = useMemo(() => new Set(route.nodeIds), [route.nodeIds]);
  const primaryEdgeIds = useMemo(() => new Set(route.edgeIds), [route.edgeIds]);
  const routeNodeIndex = useMemo(() => new Map(route.nodeIds.map((id, index) => [id, index])), [route.nodeIds]);
  const firstActionId = route.actions[0]?.id ?? null;
  const lastActionId = route.actions[route.actions.length - 1]?.id ?? null;
  const selectedNode = selectedNodeId ? nodes.find((node) => node.id === selectedNodeId) ?? null : null;
  const selectedCondition = selectedNode?.data.kind === "condition" ? selectedNode.data.condition : null;
  const selectedAction = selectedNode?.data.kind === "action" ? selectedNode.data.action : null;
  const outgoingCounts = useMemo(() => {
    const counts = new Map<string, number>();
    edges.forEach((edge) => counts.set(edge.source, (counts.get(edge.source) ?? 0) + 1));
    return counts;
  }, [edges]);
  const starterTemplates = useMemo(
    () =>
      BUILDER_STARTER_TEMPLATES.map((template) => {
        const catalogTemplate = catalogTemplates.find(
          (candidate) => candidate.id === template.id && (candidate.authoring_mode ?? "visual") === "visual",
        );
        return {
          ...template,
          name: catalogTemplate?.name ?? template.name,
          description: catalogTemplate?.description ?? template.description,
          riskProfile: catalogTemplate?.risk_profile
            ? catalogTemplate.risk_profile.charAt(0).toUpperCase() + catalogTemplate.risk_profile.slice(1)
            : template.riskProfile,
        };
      }),
    [catalogTemplates],
  );

  const flowNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          active: node.id === selectedNodeId,
          primary: node.data.kind === "entry" ? true : primaryNodeIds.has(node.id),
          branchCount: outgoingCounts.get(node.id) ?? 0,
          stageLabel: node.data.kind === "entry"
            ? "Start"
            : !primaryNodeIds.has(node.id)
              ? "Branch"
              : node.data.kind === "condition"
                ? "Signal"
                : "Action",
        },
      })),
    [nodes, selectedNodeId, primaryNodeIds, outgoingCounts],
  );

  const flowEdges = useMemo(
    () =>
      edges.map((edge) => {
        const primary = primaryEdgeIds.has(edge.id);
        return {
          ...edge,
          type: "smoothstep",
          animated: primary,
          markerEnd: { type: MarkerType.ArrowClosed, color: primary ? PRIMARY_EDGE_COLOR : SECONDARY_EDGE_COLOR },
          style: { stroke: primary ? PRIMARY_EDGE_COLOR : SECONDARY_EDGE_COLOR, strokeWidth: primary ? 2.5 : 1.7 },
        };
      }),
    [edges, primaryEdgeIds],
  );

  const marketOptions = useMemo(
    () =>
      Array.from(
        new Set(
          [
            ...markets.map((market) => market.symbol.trim()),
            ...markets.map((market) => normalizeMarketSymbol(market.symbol)),
            ...selectedMarketSymbols,
            ...nodes.flatMap((node) =>
              node.data.kind === "condition"
                ? [normalizeMarketSymbol(node.data.condition.symbol)]
                : node.data.kind === "action"
                  ? [normalizeMarketSymbol(node.data.action.symbol)]
                  : [],
            ),
            "BTC",
            "ETH",
            "SOL",
          ].filter((value) => Boolean(value) && value !== BOT_MARKET_UNIVERSE_SYMBOL),
        ),
      ),
    [markets, nodes, selectedMarketSymbols],
  );

  const activeMarkets = useMemo(
    () =>
      [...markets]
        .filter((market) => market.status === "active")
        .map((market) => ({ ...market, symbol: normalizeMarketSymbol(market.symbol) }))
        .sort((left, right) => Number(right.volume_24h ?? 0) - Number(left.volume_24h ?? 0)),
    [markets],
  );

  const availableMarketSymbols = useMemo(
    () => Array.from(new Set(activeMarkets.map((market) => market.symbol.trim()).filter(Boolean))),
    [activeMarkets],
  );

  const marketScope = useMemo(
    () => summarizeMarketScope(selectedMarketSymbols, availableMarketSymbols),
    [selectedMarketSymbols, availableMarketSymbols],
  );

  const hasUniverseNodes = useMemo(
    () =>
      nodes.some((node) =>
        node.data.kind === "condition"
          ? node.data.condition.symbol === BOT_MARKET_UNIVERSE_SYMBOL
          : node.data.kind === "action"
            ? node.data.action.symbol === BOT_MARKET_UNIVERSE_SYMBOL
            : false,
      ),
    [nodes],
  );

  const blockMarketOptions = useMemo(
    () => [BOT_MARKET_UNIVERSE_SYMBOL, ...marketOptions],
    [marketOptions],
  );

  const rulesJson = useMemo(() => {
    const persistedGraph = buildPersistedGraph(nodes, edges, selectedMarketSymbols);
    const persistedConditions = persistedGraph.nodes
      .filter((node) => node.kind === "condition" && node.config)
      .map((node) => node.config as Record<string, unknown>);
    const persistedActions = persistedGraph.nodes
      .filter((node) => node.kind === "action" && node.config)
      .map((node) => node.config as Record<string, unknown>);

    return {
      conditions: persistedConditions,
      actions: persistedActions,
      graph: {
        version: 1,
        entry: ENTRY_NODE_ID,
        nodes: persistedGraph.nodes,
        edges: persistedGraph.edges,
      },
    };
  }, [nodes, edges, selectedMarketSymbols]);
  const readyCount = [
    Boolean(name.trim() && description.trim()),
    Boolean(walletAddress.trim()),
    route.conditions.length > 0,
    route.actions.length > 0,
  ].filter(Boolean).length;
  const activeTemplate = starterTemplates.find((template) => template.id === activeTemplateId) ?? null;
  const activeTemplateLabel = activeTemplateId === BLANK_BUILDER_TEMPLATE_ID ? "New draft" : (activeTemplate?.name ?? "Custom");
  const branchSourceCount = Array.from(outgoingCounts.values()).filter((count) => count > 1).length;
  const triggerReadout = route.conditions[0]
    ? trimSentence(conditionSummary(route.conditions[0]))
    : "Add the first trigger condition";
  const executionReadout = route.actions[0]
    ? trimSentence(actionSummary(route.actions[0]))
    : "Add a first action";
  const strategyReadout = `${triggerReadout}. ${executionReadout}.`;

  const filteredConditions = CONDITION_OPTIONS.filter((option) =>
    conditionTitle(option).toLowerCase().includes(blockSearch.toLowerCase()) ||
    conditionHelper(option).toLowerCase().includes(blockSearch.toLowerCase())
  );

  const filteredActions = ACTION_OPTIONS.filter((option) =>
    actionTitle(option).toLowerCase().includes(blockSearch.toLowerCase()) ||
    actionHelper(option).toLowerCase().includes(blockSearch.toLowerCase())
  );

  function getBuilderBlocker(actionLabel: "save" | "deploy") {
    if (!walletAddress.trim()) return "Connect a wallet before saving this bot.";
    if (!name.trim()) return `Add a strategy name before you ${actionLabel}.`;
    if (!description.trim()) return `Add a short description before you ${actionLabel}.`;
    if (hasUniverseNodes && selectedMarketSymbols.length === 0) {
      return `Choose at least one market before you ${actionLabel}.`;
    }
    if (route.conditions.length === 0) return `Add at least one trigger condition before you ${actionLabel}.`;
    if (route.actions.length === 0) return `Add at least one action before you ${actionLabel}.`;
    if (actionLabel === "deploy" && onboardingStatus.blocker) return onboardingStatus.blocker;
    return null;
  }

  function applyTemplate(templateId: string) {
    const template = starterTemplates.find((candidate) => candidate.id === templateId) ?? getBuilderStarterTemplate(templateId);
    const nextGraph = template.buildGraph();

    setNodes(nextGraph.nodes);
    setEdges(nextGraph.edges);
    setSelectedNodeId(nextGraph.nodes.find((node) => node.data.kind !== "entry")?.id ?? null);
    setActiveTemplateId(template.id);
    setName(template.name);
    setDescription(template.description);
    setSelectedMarketSymbols(
      parseMarketScopeSelection(template.marketScope).length
        ? parseMarketScopeSelection(template.marketScope)
        : ["BTC"],
    );
    setCreatedBotId(null);
    setLoadedBotId(null);
    setRuntimeStatus(null);
    setError(null);

    requestAnimationFrame(() => {
      flow?.fitView({ padding: 0.18, duration: 280 });
    });
  }

  function createNewBotDraft() {
    const nextGraph = buildBlankGraph();

    setNodes(nextGraph.nodes);
    setEdges(nextGraph.edges);
    setSelectedNodeId(null);
    setActiveTemplateId(BLANK_BUILDER_TEMPLATE_ID);
    setName("");
    setDescription("");
    setSelectedMarketSymbols(["BTC", "ETH", "SOL"]);
    setCreatedBotId(null);
    setLoadedBotId(null);
    setRuntimeStatus(null);
    setError(null);
    setBlockSearch("");

    requestAnimationFrame(() => {
      flow?.fitView({ padding: 0.24, duration: 280 });
    });
  }

  function buildCurrentAiDraftContext(): BuilderAiDraft {
    return {
      name: name.trim(),
      description: description.trim(),
      marketSelection: hasUniverseNodes && selectedMarketSymbols.length === availableMarketSymbols.length ? "all" : "selected",
      markets: selectedMarketSymbols,
      conditions: route.conditions.map((condition) => ({ ...condition })),
      actions: route.actions.map((action) => ({ ...action })),
    };
  }

  function applyAiDraft(draft: BuilderAiDraft) {
    const nextGraph = buildGraphFromAiDraft(draft);
    const nextSelectedMarkets = draft.marketSelection === "all"
      ? (availableMarketSymbols.length > 0 ? availableMarketSymbols : draft.markets)
      : draft.markets;

    setNodes(nextGraph.nodes);
    setEdges(nextGraph.edges);
    setSelectedNodeId(nextGraph.nodes.find((node) => node.data.kind !== "entry")?.id ?? null);
    setActiveTemplateId(BLANK_BUILDER_TEMPLATE_ID);
    setName(draft.name);
    setDescription(draft.description);
    setSelectedMarketSymbols(nextSelectedMarkets.length > 0 ? nextSelectedMarkets : ["BTC"]);
    setCreatedBotId(null);
    setLoadedBotId(null);
    setRuntimeStatus(null);
    setBuilderMode("ai");
    setError(null);

    requestAnimationFrame(() => {
      flow?.fitView({ padding: 0.18, duration: 280 });
    });
  }

  async function sendAiMessage(seed?: string) {
    const message = (seed ?? chatInput).trim();
    if (!message || chatStatus === "sending") return;

    const nextUserMessage: BuilderChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: message,
    };
    const nextConversation = [...chatMessages, nextUserMessage];

    setChatMessages(nextConversation);
    setChatInput("");
    setChatStatus("sending");
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/builder/ai-chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextConversation.map(({ role, content }) => ({ role, content })),
          availableMarkets: availableMarketSymbols,
          currentDraft: buildCurrentAiDraftContext(),
        }),
      });
      const payload = (await response.json()) as BuilderAiRouteResponse & { detail?: string };
      if (!response.ok || !payload.draft) {
        throw new Error(payload.detail ?? "AI draft failed");
      }

      applyAiDraft(payload.draft);
      setChatMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: payload.reply,
        },
      ]);
      onNotice?.({
        eyebrow: "AI Draft",
        title: "Builder updated",
        detail: "The canvas has been rebuilt from your latest prompt.",
      });
    } catch (chatError) {
      setError(chatError instanceof Error ? chatError.message : "AI draft failed");
    } finally {
      setChatStatus("idle");
    }
  }

  function addNode(kind: "condition" | "action", blockType: string, position: XYPosition) {
    const nextPosition = snapPosition(position);
    if (kind === "condition") {
      const node = createConditionNode(createCondition(blockType as (typeof CONDITION_OPTIONS)[number]), nextPosition);
      setNodes((current) => [...current, node]);
      setSelectedNodeId(node.id);
    } else {
      const node = createActionNode(createAction(blockType as (typeof ACTION_OPTIONS)[number]), nextPosition);
      setNodes((current) => [...current, node]);
      setSelectedNodeId(node.id);
    }
    setError(null);
  }

  function updateConditionNode(id: string, patch: Partial<VisualCondition>) {
    setNodes((current) => current.map((node) => node.id === id && node.data.kind === "condition" ? { ...node, data: { ...node.data, condition: { ...node.data.condition, ...patch } } } : node));
  }

  function updateActionNode(id: string, patch: Partial<VisualAction>) {
    setNodes((current) => current.map((node) => node.id === id && node.data.kind === "action" ? { ...node, data: { ...node.data, action: { ...node.data.action, ...patch } } } : node));
  }

  function applyUniverseToAllBlocks() {
    setNodes((current) =>
      current.map((node) => {
        if (node.data.kind === "condition") {
          return {
            ...node,
            data: {
              ...node.data,
              condition: { ...node.data.condition, symbol: BOT_MARKET_UNIVERSE_SYMBOL },
            },
          };
        }
        if (node.data.kind === "action" && node.data.action.type !== "cancel_all_orders") {
          return {
            ...node,
            data: {
              ...node.data,
              action: { ...node.data.action, symbol: BOT_MARKET_UNIVERSE_SYMBOL },
            },
          };
        }
        return node;
      }),
    );
    setError(null);
  }

  function toggleSelectedMarket(symbol: string) {
    setSelectedMarketSymbols((current) =>
      current.includes(symbol) ? current.filter((item) => item !== symbol) : [...current, symbol],
    );
  }

  function changeConditionType(id: string, type: (typeof CONDITION_OPTIONS)[number]) {
    setNodes((current) => current.map((node) => {
      if (node.id !== id || node.data.kind !== "condition") return node;
      const next = createCondition(type);
      return { ...node, data: { ...node.data, condition: { ...next, id, symbol: node.data.condition.symbol || next.symbol } } };
    }));
  }

  function changeActionType(id: string, type: (typeof ACTION_OPTIONS)[number]) {
    setNodes((current) => current.map((node) => {
      if (node.id !== id || node.data.kind !== "action") return node;
      const next = createAction(type);
      return { ...node, data: { ...node.data, action: { ...next, id, symbol: node.data.action.symbol || next.symbol } } };
    }));
  }

  function removeNode(id: string) {
    setNodes((current) => current.filter((node) => node.id !== id));
    setEdges((current) => current.filter((edge) => edge.source !== id && edge.target !== id));
    if (selectedNodeId === id) setSelectedNodeId(null);
  }

  function handlePaletteDragStart(payload: PaletteDragPayload, event: DragEvent<HTMLDivElement>) {
    event.dataTransfer.setData(PALETTE_MIME, JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "move";
  }

  function handlePaneDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }

  function onPaneDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (!flow) return;
    const raw = event.dataTransfer.getData(PALETTE_MIME);
    if (!raw) return;
    const payload = JSON.parse(raw) as PaletteDragPayload;
    addNode(payload.kind, payload.blockType, flow.screenToFlowPosition({ x: event.clientX, y: event.clientY }));
  }

  function handleConnect(connection: Connection) {
    if (!connection.source || !connection.target || connection.source === connection.target) return;
    const targetNode = nodes.find((node) => node.id === connection.target);
    if (!targetNode || targetNode.data.kind === "entry") return;
    if (edges.some((edge) => edge.target === connection.target)) {
      setError("Each block can only receive one incoming connection right now. Branch outward instead of merging.");
      return;
    }
    if (edges.some((edge) => edge.source === connection.source && edge.target === connection.target)) return;
    setEdges((current) => addEdge({ ...connection, type: "smoothstep" }, current));
    setError(null);
  }

  async function persistBotDraft() {
    const method = createdBotId ? "PATCH" : "POST";
    const endpoint = createdBotId ? `${API_BASE_URL}/api/bots/${createdBotId}` : `${API_BASE_URL}/api/bots`;
    const response = await fetch(endpoint, {
      method,
      headers: await getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        wallet_address: walletAddress.trim(),
        name: name.trim(),
        description: description.trim(),
        visibility,
        market_scope: marketScope,
        strategy_type: "rules",
        authoring_mode: "visual",
        rules_version: 1,
        rules_json: rulesJson,
      }),
    });
    const payload = (await response.json()) as { id?: string; detail?: string };
    if (!response.ok || !payload.id) throw new Error(payload.detail ?? "Bot save failed");
    setCreatedBotId(payload.id);
    return payload.id;
  }

  async function createBot() {
    if (!authenticated) return void login();
    const blocker = getBuilderBlocker("save");
    if (blocker) return void setError(blocker);
    setStatus("creating");
    setError(null);
    const updatingExisting = Boolean(createdBotId);
    try {
      const savedBotId = await persistBotDraft();
      setLoadedBotId(savedBotId);
      setSavedBots((current) => {
        const nextItem: SavedBuilderBot = {
          id: savedBotId,
          name: name.trim(),
          description: description.trim(),
          visibility,
          market_scope: marketScope,
          updated_at: new Date().toISOString(),
        };
        return [nextItem, ...current.filter((bot) => bot.id !== savedBotId)].sort(
          (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
        );
      });
      setRuntimeStatus(null);
      onNotice?.({
        eyebrow: updatingExisting ? "Updated" : "Saved",
        title: updatingExisting ? "Draft updated" : "Draft saved",
        detail: updatingExisting
          ? "Your latest edits have been written back to this bot."
          : "Your changes are ready whenever you want to deploy.",
      });
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Bot save failed");
    } finally {
      setStatus("idle");
    }
  }

  function buildPortableDraft(): PortableBuilderDraft {
    return {
      format: "clashx-builder-draft",
      version: 1,
      exported_at: new Date().toISOString(),
      draft: {
        name: name.trim() || "Untitled bot",
        description: description.trim(),
        visibility,
        selected_market_symbols: selectedMarketSymbols,
        active_template_id: activeTemplateId,
        builder_mode: builderMode,
        graph: {
          nodes: nodes.map((node) => serializeGraphNode(node) as PortableBuilderNode),
          edges: edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target })),
        },
      },
    };
  }

  function parsePortableDraft(payload: unknown): PortableBuilderDraft {
    if (!isRecord(payload) || payload.format !== "clashx-builder-draft" || payload.version !== 1) {
      throw new Error("This file is not a supported ClashX bot draft.");
    }

    const { draft } = payload;
    if (!isRecord(draft)) {
      throw new Error("The draft payload is missing its configuration.");
    }

    const visibilityValue = draft.visibility;
    if (visibilityValue !== "private" && visibilityValue !== "public" && visibilityValue !== "unlisted") {
      throw new Error("The draft visibility is invalid.");
    }

    const graph = draft.graph;
    if (!isRecord(graph) || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
      throw new Error("The draft graph is incomplete.");
    }

    for (const node of graph.nodes) {
      if (!isRecord(node) || typeof node.id !== "string" || typeof node.kind !== "string" || !isRecord(node.position)) {
        throw new Error("The draft contains an invalid node.");
      }
      if (typeof node.position.x !== "number" || typeof node.position.y !== "number") {
        throw new Error("One of the imported nodes has an invalid position.");
      }
      if (node.kind !== "entry" && node.kind !== "condition" && node.kind !== "action") {
        throw new Error("The draft contains an unknown node type.");
      }
    }

    for (const edge of graph.edges) {
      if (!isRecord(edge) || typeof edge.source !== "string" || typeof edge.target !== "string") {
        throw new Error("The draft contains an invalid edge.");
      }
    }

    const selectedSymbols = Array.isArray(draft.selected_market_symbols)
      ? draft.selected_market_symbols.filter((value): value is string => typeof value === "string")
      : [];

    return {
      format: "clashx-builder-draft",
      version: 1,
      exported_at: typeof payload.exported_at === "string" ? payload.exported_at : new Date().toISOString(),
      draft: {
        name: typeof draft.name === "string" ? draft.name : "",
        description: typeof draft.description === "string" ? draft.description : "",
        visibility: visibilityValue,
        selected_market_symbols: selectedSymbols,
        active_template_id: typeof draft.active_template_id === "string" ? draft.active_template_id : undefined,
        builder_mode: draft.builder_mode === "ai" ? "ai" : "visual",
        graph: {
          nodes: graph.nodes as PortableBuilderNode[],
          edges: graph.edges as PortableBuilderEdge[],
        },
      },
    };
  }

  function applyImportedDraft(payload: PortableBuilderDraft) {
    const nextGraph = buildCanvasFromSerializedGraph(payload.draft.graph);

    setNodes(nextGraph.nodes);
    setEdges(nextGraph.edges);
    setSelectedNodeId(nextGraph.selectedNodeId);
    setActiveTemplateId(payload.draft.active_template_id ?? BLANK_BUILDER_TEMPLATE_ID);
    setName(payload.draft.name);
    setDescription(payload.draft.description);
    setVisibility(payload.draft.visibility);
    setSelectedMarketSymbols(payload.draft.selected_market_symbols.length > 0 ? payload.draft.selected_market_symbols.map(normalizeMarketSymbol) : ["BTC"]);
    setBuilderMode(payload.draft.builder_mode ?? "visual");
    setCreatedBotId(null);
    setLoadedBotId(null);
    setRuntimeStatus(null);
    setError(null);
    setBlockSearch("");

    requestAnimationFrame(() => {
      flow?.fitView({ padding: 0.18, duration: 280 });
    });
  }

  function exportDraft() {
    try {
      const payload = buildPortableDraft();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${sanitizeDraftFileName(payload.draft.name)}.json`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
      onNotice?.({
        eyebrow: "Exported",
        title: "Draft downloaded",
        detail: "You can import this JSON on any Builder Studio session.",
      });
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Could not export this draft");
    }
  }

  async function importDraft(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    try {
      const raw = await file.text();
      const payload = parsePortableDraft(JSON.parse(raw));
      applyImportedDraft(payload);
      onNotice?.({
        eyebrow: "Imported",
        title: "Draft loaded",
        detail: "The builder has been updated from your JSON file.",
      });
    } catch (importError) {
      setError(importError instanceof Error ? importError.message : "Could not import this draft");
    }
  }

  function openDeployModal() {
    if (!authenticated) return void login();
    const blocker = getBuilderBlocker("deploy");
    if (blocker) {
      if (blocker === onboardingStatus.blocker) {
        setError(null);
        onOpenOnboardingGuide?.();
        return;
      }
      return void setError(blocker);
    }
    setError(null);
    setRuntimeControlsError(null);
    setRuntimeControlsOpen(true);
  }

  function closeRuntimeControlsModal() {
    if (status === "deploying") return;
    setRuntimeControlsOpen(false);
    setRuntimeControlsError(null);
  }

  function selectRuntimePreset(presetId: RuntimeControlPreset) {
    const preset = RUNTIME_CONTROL_PRESETS.find((candidate) => candidate.id === presetId);
    if (!preset) return;
    setRuntimePreset(preset.id);
    setRuntimeControls({ ...preset.values });
    setRuntimeControlsError(null);
  }

  function updateRuntimeControl<K extends keyof RuntimeControlsFormState>(key: K, value: RuntimeControlsFormState[K]) {
    setRuntimeControls((current) => ({ ...current, [key]: value }));
    setRuntimeControlsError(null);
  }

  async function deployBot() {
    const runtimeBlocker = validateRuntimeControls(
      runtimePreset,
      runtimeControls,
      selectedMarketSymbols,
      activeMarkets,
    );
    if (runtimeBlocker) {
      setRuntimeControlsError(runtimeBlocker);
      return;
    }

    setStatus("deploying");
    setError(null);
    setRuntimeControlsError(null);
    try {
      const botId = await persistBotDraft();
      await assertPacificaDeployReadiness(walletAddress.trim(), getAuthHeaders);
      const response = await fetch(`${API_BASE_URL}/api/bots/${botId}/deploy`, {
        method: "POST",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          wallet_address: walletAddress.trim(),
          risk_policy_json: buildRiskPolicyPayload(selectedMarketSymbols, runtimeControls),
        }),
      });
      const payload = (await response.json()) as { status?: string; detail?: string };
      if (!response.ok) throw new Error(payload.detail ?? "Deploy failed");
      setRuntimeStatus(payload.status ?? "active");
      setRuntimeControlsOpen(false);
      onNotice?.({
        eyebrow: "Deployed",
        title: "Bot is live",
        detail: "It will start trading as soon as the strategy conditions are met.",
      });
    } catch (deployError) {
      if (deployError instanceof PacificaReadinessError) {
        setRuntimeControlsOpen(false);
        onOpenOnboardingGuide?.();
      }
      setError(deployError instanceof Error ? deployError.message : "Deploy failed");
    } finally {
      setStatus("idle");
    }
  }

  return (
    <div className="relative flex-1 flex flex-col bg-app overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-[rgba(255,255,255,0.06)] bg-secondary">
        <div className="px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-bold text-neutral-50 flex items-center gap-3">
              <Box className="w-6 h-6 text-[#dce85d]" />
              Bot Builder
            </h1>
            <div className="h-6 w-px bg-[rgba(255,255,255,0.06)]"></div>

            {/* Builder Mode Toggle */}
            <div className="flex items-center gap-2 bg-neutral-900 border border-[rgba(255,255,255,0.06)] rounded-md p-1">
              <button
                type="button"
                onClick={() => setBuilderMode("visual")}
                className={clsx(
                  "flex items-center gap-2 px-3 py-1.5 text-sm rounded transition-all",
                  builderMode === "visual"
                    ? "bg-[#dce85d] text-[#090a0a] font-semibold"
                    : "text-neutral-400 hover:text-neutral-300",
                )}
              >
                <Grid3x3 className="w-4 h-4" />
                <span>Visual</span>
              </button>
              <button
                type="button"
                onClick={() => setBuilderMode("ai")}
                className={clsx(
                  "flex items-center gap-2 px-3 py-1.5 text-sm rounded transition-all",
                  builderMode === "ai"
                    ? "bg-[#dce85d] text-[#090a0a] font-semibold"
                    : "text-neutral-400 hover:text-neutral-300",
                )}
              >
                <Sparkles className="w-4 h-4" />
                <span>AI Chat</span>
              </button>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-1 justify-end max-w-4xl">
            <input
              ref={importInputRef}
              type="file"
              accept="application/json,.json"
              onChange={importDraft}
              className="hidden"
            />
            <div className="flex items-center gap-3 flex-1">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter Strategy Name..."
                className="bg-neutral-900 border border-[rgba(255,255,255,0.06)] rounded-md px-3 py-1.5 text-sm text-neutral-50 w-full focus:outline-none focus:border-[#dce85d] transition-colors"
              />
              <button
                type="button"
                onClick={createNewBotDraft}
                className="flex h-9 items-center gap-2 rounded-md border border-[rgba(255,255,255,0.08)] bg-neutral-900 px-3 text-sm font-semibold text-neutral-200 transition-all hover:border-[rgba(220,232,93,0.34)] hover:text-white"
              >
                <Plus className="w-4 h-4" />
                New
              </button>
              <button
                type="button"
                onClick={() => setSavedBotsOpen((current) => !current)}
                className={clsx(
                  "flex h-9 items-center gap-2 rounded-md border px-3 text-sm font-semibold transition-all",
                  savedBotsOpen
                    ? "border-[rgba(220,232,93,0.34)] bg-[rgba(220,232,93,0.08)] text-[#dce85d]"
                    : "border-[rgba(255,255,255,0.08)] bg-neutral-900 text-neutral-200 hover:border-[rgba(220,232,93,0.34)] hover:text-white",
                )}
              >
                <RefreshCcw className="w-4 h-4" />
                Load
              </button>
              <button
                type="button"
                onClick={createBot}
                disabled={status === "creating"}
                className={clsx(
                  "flex h-9 items-center gap-2 rounded-md border px-3 text-sm font-semibold transition-all",
                  status === "creating"
                    ? "border-[rgba(255,255,255,0.08)] bg-neutral-900 text-neutral-500"
                    : "border-[rgba(255,255,255,0.08)] bg-neutral-900 text-neutral-200 hover:border-[rgba(220,232,93,0.34)] hover:text-white",
                )}
              >
                {status === "creating" ? "Saving..." : "Save"}
              </button>
              <button
                type="button"
                onClick={exportDraft}
                className="flex h-9 items-center gap-2 rounded-md border border-[rgba(255,255,255,0.08)] bg-neutral-900 px-3 text-sm font-semibold text-neutral-200 transition-all hover:border-[rgba(116,185,127,0.34)] hover:text-white"
              >
                <Download className="w-4 h-4" />
                Export
              </button>
              <button
                type="button"
                onClick={() => importInputRef.current?.click()}
                className="flex h-9 items-center gap-2 rounded-md border border-[rgba(255,255,255,0.08)] bg-neutral-900 px-3 text-sm font-semibold text-neutral-200 transition-all hover:border-[rgba(220,232,93,0.34)] hover:text-white"
              >
                <Upload className="w-4 h-4" />
                Import
              </button>
            </div>
            <button
              onClick={openDeployModal}
              disabled={status === "deploying"}
              className={clsx(
                "flex items-center gap-2 h-9 px-4 rounded-md text-sm font-semibold transition-all whitespace-nowrap",
                status === "deploying"
                  ? "bg-neutral-800 text-neutral-500"
                  : "bg-[#dce85d] text-[#090a0a] hover:bg-[#e8f06d]"
              )}
            >
              <Play className="w-4 h-4" />
              {status === "deploying" ? "Deploying..." : "Deploy Bot"}
            </button>
            <button
              type="button"
              onClick={onOpenOnboardingGuide}
              className="flex h-9 items-center rounded-md border border-[rgba(255,255,255,0.08)] bg-neutral-900 px-3 text-sm font-semibold text-neutral-200 transition-all hover:border-[rgba(220,232,93,0.34)] hover:text-white whitespace-nowrap"
            >
              Pacifica setup
            </button>
          </div>
        </div>
      </div>

      {savedBotsOpen ? (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-[rgba(3,4,4,0.72)] px-4 py-8 backdrop-blur-sm">
          <div
            className="absolute inset-0"
            onClick={() => setSavedBotsOpen(false)}
            aria-hidden="true"
          />
          <div className="relative z-10 w-full max-w-2xl overflow-hidden rounded-[2rem] border border-[rgba(220,232,93,0.22)] bg-[linear-gradient(180deg,rgba(18,20,18,0.98),rgba(9,10,10,0.99))] shadow-[0_28px_80px_rgba(0,0,0,0.5)]">
            <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.06)] px-6 py-5">
              <div>
                <div className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">Saved drafts</div>
                <div className="mt-1 text-sm text-neutral-400">Pick a bot to reopen in the builder and keep editing.</div>
              </div>
              <button
                type="button"
                onClick={() => setSavedBotsOpen(false)}
                className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1 text-[0.58rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-white hover:text-white"
              >
                Close
              </button>
            </div>
            <div className="max-h-[min(70vh,38rem)] space-y-3 overflow-y-auto p-6">
              {savedBotsLoading ? (
                <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-neutral-800/70 px-4 py-4 text-sm text-neutral-400">
                  Loading your saved bots...
                </div>
              ) : savedBots.length === 0 ? (
                <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-neutral-800/70 px-4 py-4 text-sm leading-6 text-neutral-400">
                  Save a draft once and it will appear here for quick loading.
                </div>
              ) : (
                savedBots.slice(0, 10).map((bot) => {
                  const isCurrent = bot.id === createdBotId;
                  const isLoading = bot.id === loadingBotId;
                  return (
                    <div
                      key={bot.id}
                      className={clsx(
                        "rounded-[1.35rem] border px-4 py-4 transition-colors",
                        isCurrent
                          ? "border-[rgba(220,232,93,0.24)] bg-[rgba(220,232,93,0.06)]"
                          : "border-[rgba(255,255,255,0.06)] bg-neutral-800/70",
                      )}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="truncate text-base font-semibold text-neutral-50">{bot.name}</div>
                          <div className="mt-1 text-[0.65rem] uppercase tracking-[0.14em] text-neutral-500">
                            {bot.visibility} / {bot.market_scope}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => void loadBotIntoBuilder(bot.id)}
                          disabled={isCurrent || isLoading}
                          className={clsx(
                            "rounded-full border px-3 py-1.5 text-[0.58rem] font-semibold uppercase tracking-[0.16em] transition",
                            isCurrent
                              ? "border-[rgba(220,232,93,0.18)] text-[#dce85d]/70"
                              : "border-[rgba(255,255,255,0.12)] text-neutral-300 hover:border-[#dce85d] hover:text-[#dce85d]",
                          )}
                        >
                          {isLoading ? "Loading" : isCurrent ? "Open" : "Load"}
                        </button>
                      </div>
                      <div className="mt-2 line-clamp-2 text-sm leading-6 text-neutral-400">
                        {bot.description || "No description yet."}
                      </div>
                      <div className="mt-3 text-[0.7rem] text-neutral-500">
                        Updated {new Date(bot.updated_at).toLocaleString()}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      ) : null}

      {runtimeControlsOpen ? (
        <div className="absolute inset-0 z-40 flex items-center justify-center bg-[rgba(3,4,4,0.76)] px-4 py-8 backdrop-blur-sm">
          <div
            className="absolute inset-0"
            onClick={closeRuntimeControlsModal}
            aria-hidden="true"
          />
          <div className="relative z-10 flex w-full max-w-4xl flex-col overflow-hidden max-h-full rounded-[2rem] border border-[rgba(220,232,93,0.24)] bg-[linear-gradient(180deg,rgba(18,20,18,0.98),rgba(9,10,10,0.99))] shadow-[0_28px_90px_rgba(0,0,0,0.56)]">
            <div className="grid shrink-0 gap-6 border-b border-[rgba(255,255,255,0.06)] px-6 py-6 lg:grid-cols-[1.15fr_0.85fr]">
              <div>
                <div className="text-[0.62rem] font-semibold uppercase tracking-[0.2em] text-[#dce85d]">Runtime controls</div>
                <h2 className="mt-2 text-2xl font-semibold text-neutral-50">Choose how this bot behaves once it goes live.</h2>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-neutral-400">
                  Pick a runtime profile, then fine-tune the guardrails. Deployment stays locked until you make that choice.
                </p>
              </div>
              <div className="rounded-[1.5rem] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] p-5">
                <div className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">Launch summary</div>
                <div className="mt-3 text-lg font-semibold text-neutral-50">{name.trim() || "Untitled bot"}</div>
                <div className="mt-2 line-clamp-2 text-sm leading-6 text-neutral-400" title={selectedMarketSymbols.join(", ")}>
                  {selectedMarketSymbols.length > 0 ? selectedMarketSymbols.join(", ") : "No markets selected"}
                </div>
                <div className="mt-4 grid gap-2 text-xs text-neutral-500">
                  <div className="flex items-center justify-between gap-4">
                    <span>Capital at work</span>
                    <span className="text-neutral-300">${runtimeControls.allocatedCapitalUsd}</span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span>Max leverage</span>
                    <span className="text-neutral-300">{runtimeControls.maxLeverage}x</span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span>Cooldown</span>
                    <span className="text-neutral-300">{runtimeControls.cooldownSeconds}s</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="custom-scrollbar grid min-h-0 gap-6 overflow-y-auto px-6 py-6 lg:grid-cols-[1.15fr_0.85fr]">
              <div className="flex flex-col gap-6">
                <div>
                  <div className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">Pick a profile</div>
                  <div className="mt-3 grid gap-3 md:grid-cols-3">
                  {RUNTIME_CONTROL_PRESETS.map((preset) => {
                    const selected = runtimePreset === preset.id;
                    return (
                      <button
                        key={preset.id}
                        type="button"
                        onClick={() => selectRuntimePreset(preset.id)}
                        className={clsx(
                          "rounded-[1.35rem] border p-4 text-left transition-all",
                          selected
                            ? "border-[rgba(220,232,93,0.42)] bg-[rgba(220,232,93,0.08)]"
                            : "border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] hover:border-[rgba(220,232,93,0.22)]",
                        )}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-sm font-semibold text-neutral-50">{preset.label}</span>
                          {selected ? (
                            <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#dce85d] text-[#090a0a]">
                              <Check className="h-3.5 w-3.5" />
                            </div>
                          ) : null}
                        </div>
                        <p className="mt-2 text-sm leading-6 text-neutral-400">{preset.description}</p>
                      </button>
                    );
                  })}
                </div>

                <div className="mt-6 grid gap-3 sm:grid-cols-2">
                  <label className="grid gap-1.5 text-sm text-neutral-400">
                    Max leverage
                    <input
                      type="number"
                      min={1}
                      value={runtimeControls.maxLeverage}
                      onChange={(event) => updateRuntimeControl("maxLeverage", Number(event.target.value))}
                      className="w-full rounded-xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
                    />
                  </label>
                  <label className="grid gap-1.5 text-sm text-neutral-400">
                    Max order size USD
                    <input
                      type="number"
                      min={1}
                      value={runtimeControls.maxOrderSizeUsd}
                      onChange={(event) => updateRuntimeControl("maxOrderSizeUsd", Number(event.target.value))}
                      className="w-full rounded-xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
                    />
                  </label>
                  <label className="grid gap-1.5 text-sm text-neutral-400">
                    Allocated capital USD
                    <input
                      type="number"
                      min={1}
                      value={runtimeControls.allocatedCapitalUsd}
                      onChange={(event) => updateRuntimeControl("allocatedCapitalUsd", Number(event.target.value))}
                      className="w-full rounded-xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
                    />
                  </label>
                  <label className="grid gap-1.5 text-sm text-neutral-400">
                    Cooldown seconds
                    <input
                      type="number"
                      min={0}
                      value={runtimeControls.cooldownSeconds}
                      onChange={(event) => updateRuntimeControl("cooldownSeconds", Number(event.target.value))}
                      className="w-full rounded-xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
                    />
                  </label>
                  <label className="grid gap-1.5 text-sm text-neutral-400">
                    Max drawdown %
                    <input
                      type="number"
                      min={0}
                      step="0.1"
                      value={runtimeControls.maxDrawdownPct}
                      onChange={(event) => updateRuntimeControl("maxDrawdownPct", Number(event.target.value))}
                      className="w-full rounded-xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
                    />
                  </label>
                  <label className="grid gap-1.5 text-sm text-neutral-400">
                    Sizing mode
                    <select
                      value={runtimeControls.sizingMode}
                      onChange={(event) => updateRuntimeControl("sizingMode", event.target.value as RuntimeControlsFormState["sizingMode"])}
                      className="w-full rounded-xl border border-[rgba(255,255,255,0.08)] bg-[#090a0a] px-3 py-2.5 text-neutral-50 outline-none transition focus:border-[#dce85d]"
                    >
                      <option value="fixed_usd">fixed usd</option>
                      <option value="risk_adjusted">risk adjusted</option>
                    </select>
                  </label>
                </div>
              </div>
            </div>

            <div className="flex h-[32rem] lg:h-full max-h-[32rem] flex-col rounded-[1.5rem] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] p-5">
                <div className="mb-4 shrink-0 text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">Risk policy preview</div>
                <div className="min-h-0 flex-1 overflow-hidden rounded-[1.15rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a]">
                  <pre className="custom-scrollbar h-full w-full overflow-auto p-4 text-xs leading-6 text-neutral-300">
                    {JSON.stringify(buildRiskPolicyPayload(selectedMarketSymbols, runtimeControls), null, 2)}
                  </pre>
                </div>
                {runtimeControlsError ? (
                  <p className="mt-4 shrink-0 text-sm text-[#dce85d]">{runtimeControlsError}</p>
                ) : (
                  <p className="mt-4 shrink-0 text-sm leading-6 text-neutral-500">
                    These controls are sent with the deploy request and become the bot&apos;s live runtime guardrails.
                  </p>
                )}
              </div>
            </div>

            <div className="flex shrink-0 items-center justify-between gap-3 border-t border-[rgba(255,255,255,0.06)] px-6 py-5">
              <button
                type="button"
                onClick={closeRuntimeControlsModal}
                disabled={status === "deploying"}
                className="flex h-10 items-center rounded-full border border-[rgba(255,255,255,0.1)] px-4 text-sm font-semibold text-neutral-300 transition hover:border-[rgba(255,255,255,0.18)] hover:text-white disabled:opacity-60"
              >
                Back to builder
              </button>
              <button
                type="button"
                onClick={() => void deployBot()}
                disabled={status === "deploying"}
                className={clsx(
                  "flex h-10 items-center gap-2 rounded-full px-5 text-sm font-semibold transition-all",
                  status === "deploying"
                    ? "bg-neutral-800 text-neutral-500"
                    : "bg-[#dce85d] text-[#090a0a] hover:bg-[#e8f06d]",
                )}
              >
                <Play className="h-4 w-4" />
                {status === "deploying" ? "Deploying..." : "Deploy with runtime controls"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Main Workspace */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        <div className="w-72 flex-shrink-0 border-r border-[rgba(255,255,255,0.06)] bg-secondary flex flex-col">
          {builderMode === "visual" ? (
            <>
              <div className="p-4 border-b border-[rgba(255,255,255,0.06)] bg-transparent">
                <h2 className="text-sm font-semibold text-neutral-50 mb-1">Block Palette</h2>
                <div className="relative mt-3">
                  <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                  <input
                    type="text"
                    placeholder="Search blocks..."
                    value={blockSearch}
                    onChange={(e) => setBlockSearch(e.target.value)}
                    className="w-full bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md pl-9 pr-3 py-1.5 text-xs text-neutral-50 focus:outline-none focus:border-[rgba(255,255,255,0.12)] transition-colors"
                  />
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                {SIGNAL_CATEGORIES.some((c) => c.keys.some((k) => filteredConditions.includes(k as any))) && (
                  <div className="mb-8">
                    <div className="flex items-center gap-2 mb-4 pb-2 border-b border-[rgba(255,255,255,0.06)] text-neutral-300">
                      <Activity className="w-4 h-4 text-[#dce85d]" />
                      <span className="text-sm font-bold tracking-wide">Signals</span>
                    </div>
                    {SIGNAL_CATEGORIES.map((category, idx) => (
                      <BlockCategory
                        key={category.name}
                        title={category.name}
                        icon={Activity}
                        options={category.keys.filter((k) => filteredConditions.includes(k as any))}
                        searchQuery={blockSearch}
                        kind="condition"
                        onDragStart={handlePaletteDragStart}
                        defaultExpanded={idx === 0}
                      />
                    ))}
                  </div>
                )}

                {ACTION_CATEGORIES.some((c) => c.keys.some((k) => filteredActions.includes(k as any))) && (
                  <div className="mb-4">
                    <div className="flex items-center gap-2 mb-4 pb-2 border-b border-[rgba(255,255,255,0.06)] text-neutral-300">
                      <Box className="w-4 h-4 text-[#74b97f]" />
                      <span className="text-sm font-bold tracking-wide">Actions</span>
                    </div>
                    {ACTION_CATEGORIES.map((category, idx) => (
                      <BlockCategory
                        key={category.name}
                        title={category.name}
                        icon={Box}
                        options={category.keys.filter((k) => filteredActions.includes(k as any))}
                        searchQuery={blockSearch}
                        kind="action"
                        onDragStart={handlePaletteDragStart}
                        defaultExpanded={idx === 0}
                      />
                    ))}
                  </div>
                )}

                {filteredConditions.length === 0 && filteredActions.length === 0 && (
                  <div className="text-center py-8 text-xs text-neutral-500">
                    No blocks found matching &quot;{blockSearch}&quot;
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <div className="border-b border-[rgba(255,255,255,0.06)] bg-transparent px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]/80">Builder AI</div>
                    <h2 className="mt-1 text-sm font-semibold text-neutral-50">Describe the bot in plain language</h2>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setChatMessages([
                        {
                          id: "assistant-welcome-reset",
                          role: "assistant",
                          content: "Describe the bot you want and I’ll turn it into a draft with signals, actions, and market scope.",
                        },
                      ]);
                      setChatInput("");
                      setError(null);
                    }}
                    className="flex h-8 items-center gap-1.5 rounded-md border border-[rgba(255,255,255,0.08)] bg-neutral-800 px-2.5 text-[0.7rem] font-semibold text-neutral-300 transition hover:border-[rgba(255,255,255,0.14)] hover:text-white"
                  >
                    <RefreshCcw className="h-3.5 w-3.5" />
                    Reset
                  </button>
                </div>
                <p className="mt-2 text-xs leading-5 text-neutral-400">
                  Ask for entries, exits, leverage, cooldowns, or multi-market scans. Each reply can refine the draft on the canvas.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {[
                    "Build a BTC momentum long bot that waits for an EMA cross, RSI strength, then opens long with TP and SL.",
                    "Make this trade all active markets, but only after volatility expands and cooldown is clear.",
                    "Turn the current draft into a mean reversion short on ETH with tighter risk.",
                  ].map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => void sendAiMessage(prompt)}
                      className="rounded-full border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] px-3 py-1.5 text-left text-[0.68rem] leading-4 text-neutral-300 transition hover:border-[rgba(220,232,93,0.24)] hover:text-white"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>

              <div ref={chatViewportRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4 custom-scrollbar">
                {chatMessages.map((message) => (
                  <div
                    key={message.id}
                    className={clsx(
                      "rounded-2xl px-3 py-3 text-sm leading-6",
                      message.role === "assistant"
                        ? "border border-[rgba(220,232,93,0.16)] bg-[rgba(220,232,93,0.06)] text-neutral-100"
                        : "border border-[rgba(255,255,255,0.06)] bg-neutral-900 text-neutral-200",
                    )}
                  >
                    <div className="mb-1 text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">
                      {message.role === "assistant" ? "ClashX AI" : "You"}
                    </div>
                    <p className="whitespace-pre-wrap">{message.content}</p>
                  </div>
                ))}
                {chatStatus === "sending" ? (
                  <div className="rounded-2xl border border-[rgba(220,232,93,0.16)] bg-[rgba(220,232,93,0.04)] px-3 py-3 text-sm text-neutral-300">
                    Rebuilding the draft...
                  </div>
                ) : null}
              </div>

              <div className="border-t border-[rgba(255,255,255,0.06)] bg-transparent p-4">
                <div className="rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0d0f10] p-2">
                  <textarea
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        void sendAiMessage();
                      }
                    }}
                    placeholder="Create a SOL trend bot that scales in with TWAP after MACD confirmation..."
                    className="min-h-28 w-full resize-none bg-transparent px-2 py-2 text-sm leading-6 text-neutral-50 placeholder:text-neutral-500 focus:outline-none"
                  />
                  <div className="flex items-center justify-between gap-3 border-t border-[rgba(255,255,255,0.06)] px-2 pt-2">
                    <div className="text-[0.68rem] leading-4 text-neutral-500">
                      Press Enter to send. Shift+Enter adds a new line.
                    </div>
                    <button
                      type="button"
                      onClick={() => void sendAiMessage()}
                      disabled={chatStatus === "sending" || !chatInput.trim()}
                      className={clsx(
                        "flex h-9 items-center gap-2 rounded-full px-3 text-sm font-semibold transition-all",
                        chatStatus === "sending" || !chatInput.trim()
                          ? "bg-neutral-800 text-neutral-500"
                          : "bg-[#dce85d] text-[#090a0a] hover:bg-[#e8f06d]",
                      )}
                    >
                      <ArrowUp className="h-4 w-4" />
                      Send
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Center - Canvas */}
        <div
          className="flex-1 relative bg-[#090a0a]"
          onDragOver={handlePaneDragOver}
          onDrop={onPaneDrop}
        >
          <div className="absolute inset-x-4 top-4 z-10 flex flex-wrap items-start justify-between gap-3">
            <div className="max-w-xl rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(15,16,17,0.9)] px-4 py-3 shadow-[0_18px_40px_rgba(0,0,0,0.28)] backdrop-blur-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[0.58rem] font-semibold uppercase tracking-[0.18em] text-neutral-500">Strategy</span>
                <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-2 py-0.5 text-[0.55rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
                  {activeTemplateLabel}
                </span>
                <span className="rounded-full border border-[rgba(255,255,255,0.08)] px-2 py-0.5 text-[0.55rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">
                  {marketScope}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-neutral-300">{strategyReadout}</p>
            </div>

            <div className="rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(15,16,17,0.9)] px-3 py-3 shadow-[0_18px_40px_rgba(0,0,0,0.28)] backdrop-blur-sm">
              <div className="grid gap-2 text-xs text-neutral-300">
                <div className="flex items-center justify-between gap-4">
                  <span>Signals</span>
                  <span className="font-semibold text-neutral-50">{nodes.filter((node) => node.data.kind === "condition").length}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>Actions</span>
                  <span className="font-semibold text-neutral-50">{nodes.filter((node) => node.data.kind === "action").length}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>Branches</span>
                  <span className="font-semibold text-neutral-50">{branchSourceCount}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>Ready</span>
                  <span className="font-semibold text-[#dce85d]">{readyCount}/4</span>
                </div>
              </div>
            </div>
          </div>

          {error ? (
            <div className="absolute left-4 top-28 z-10 rounded-lg border border-[#e06c6e]/30 bg-[#e06c6e]/10 px-3 py-2">
              <span className="text-xs font-medium text-[#f0a5a6]">{error}</span>
            </div>
          ) : null}

          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={handleConnect}
            onInit={setFlow}
            onNodeClick={(_, node) => {
              if (node.data.kind !== "entry") setSelectedNodeId(node.id);
            }}
            nodeTypes={nodeTypes}
            fitView
            proOptions={{ hideAttribution: true }}
            className="[&_.react-flow__pane]:bg-transparent"
          >
            <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="rgba(255,255,255,0.08)" />
            <Controls className="!bg-secondary !border-[rgba(255,255,255,0.08)] !shadow-xl !flex !flex-col !gap-1 !p-1 [&_button]:!bg-transparent [&_button]:!border-none [&_button]:!rounded-md hover:[&_button]:!bg-white/10 [&_button_svg]:!fill-neutral-400" />
            <MiniMap
              className="!bg-secondary !border-[rgba(255,255,255,0.06)] rounded-lg overflow-hidden"
              nodeColor={(node) => {
                return node.data?.kind === 'condition' ? '#dce85d' : '#74b97f';
              }}
              maskColor="rgba(9, 10, 10, 0.7)"
            />
          </ReactFlow>
        </div>

        {/* Right Sidebar - Settings */}
        <div className="w-80 flex-shrink-0 border-l border-[rgba(255,255,255,0.06)] bg-secondary overflow-y-auto overflow-x-hidden custom-scrollbar flex flex-col">
          <div className="border-b border-[rgba(255,255,255,0.06)]">
            <div className="p-4 bg-transparent">
              <h2 className="text-sm font-semibold text-neutral-50 mb-4">Quick Start Templates</h2>
              <div className="space-y-2">
                {starterTemplates.map((template) => {
                  const isActive = template.id === activeTemplateId;

                  return (
                    <button
                      key={template.id}
                      type="button"
                      aria-pressed={isActive}
                      onClick={() => applyTemplate(template.id)}
                      className={clsx(
                        "w-full rounded-md border px-3 py-2 text-left text-sm transition-colors",
                        isActive
                          ? "border-[#dce85d]/50 bg-neutral-800 text-neutral-50"
                          : "border-[rgba(255,255,255,0.06)] bg-neutral-800 text-neutral-300 hover:border-[rgba(255,255,255,0.12)] hover:text-neutral-50",
                      )}
                    >
                      {template.name}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Settings Section */}
          <div className="border-b border-[rgba(255,255,255,0.06)]">
            <div className="p-4 bg-transparent">
              <h2 className="text-sm font-semibold text-neutral-50 mb-4">Bot Configuration</h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1.5">Description</label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Describe your strategy in plain language..."
                    rows={4}
                    className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] resize-none transition-colors"
                  />
                </div>

                <div>
                  <div className="mb-1.5 flex items-center justify-between gap-3">
                    <label className="block text-xs font-medium text-neutral-400">Market Universe</label>
                    <span className="text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-[#dce85d]">
                      {selectedMarketSymbols.length || "No"} selected
                    </span>
                  </div>
                  <div className="rounded-2xl border border-[rgba(255,255,255,0.06)] bg-neutral-800/80 p-3">
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-2xl border border-[rgba(220,232,93,0.18)] bg-[rgba(220,232,93,0.08)] text-[#dce85d]">
                        <Globe className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-semibold text-neutral-50">{marketScope}</div>
                        <p className="mt-1 text-xs leading-5 text-neutral-400">
                          The bot scans these markets. Any block set to <span className="text-neutral-200">Bot market universe</span> expands across the full list when you save or deploy.
                        </p>
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedMarketSymbols(availableMarketSymbols)}
                        className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1.5 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-neutral-200 transition hover:border-[#dce85d]/40 hover:text-white"
                      >
                        All markets
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelectedMarketSymbols(["BTC", "ETH", "SOL"])}
                        className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1.5 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-neutral-200 transition hover:border-[#dce85d]/40 hover:text-white"
                      >
                        Majors
                      </button>
                      <button
                        type="button"
                        onClick={applyUniverseToAllBlocks}
                        className="rounded-full border border-[#dce85d]/30 bg-[#dce85d]/10 px-3 py-1.5 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#dce85d] transition hover:bg-[#dce85d]/16"
                      >
                        Use for every block
                      </button>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      {activeMarkets.slice(0, 18).map((market) => {
                        const selected = selectedMarketSymbols.includes(market.symbol);
                        return (
                          <button
                            key={market.symbol}
                            type="button"
                            onClick={() => toggleSelectedMarket(market.symbol)}
                            className={clsx(
                              "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition",
                              selected
                                ? "border-[#dce85d]/45 bg-[#dce85d]/12 text-neutral-50"
                                : "border-[rgba(255,255,255,0.08)] text-neutral-400 hover:border-[rgba(255,255,255,0.16)] hover:text-neutral-200",
                            )}
                          >
                            {selected ? <Check className="h-3.5 w-3.5 text-[#dce85d]" /> : null}
                            {market.symbol}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="border-b border-[rgba(255,255,255,0.06)]">
            <div className="p-4 bg-transparent">
              <h2 className="text-sm font-semibold text-neutral-50 mb-4">Selected Block</h2>

              {!selectedNode ? (
                <div className="rounded-md border border-[rgba(255,255,255,0.06)] bg-neutral-800 px-3 py-3 text-xs leading-5 text-neutral-400">
                  Click a node on the canvas to edit its trigger or action settings.
                </div>
              ) : null}

              {selectedCondition ? (
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-neutral-400 mb-1.5">Signal Type</label>
                    <select
                      value={selectedCondition.type}
                      onChange={(e) => changeConditionType(selectedCondition.id, e.target.value as (typeof CONDITION_OPTIONS)[number])}
                      className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                    >
                      {CONDITION_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {conditionTitle(option)}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-neutral-400 mb-1.5">Market</label>
                    <select
                      value={selectedCondition.symbol}
                      onChange={(e) => updateConditionNode(selectedCondition.id, { symbol: e.target.value })}
                      className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                    >
                      {blockMarketOptions.map((symbol) => (
                        <option key={symbol} value={symbol}>
                          {symbol === BOT_MARKET_UNIVERSE_SYMBOL ? "Bot market universe" : symbol}
                        </option>
                      ))}
                    </select>
                  </div>

                  {selectedCondition.type === "position_side_is" ? (
                    <div>
                      <label className="block text-xs font-medium text-neutral-400 mb-1.5">Required Side</label>
                      <select
                        value={selectedCondition.side ?? "long"}
                        onChange={(e) => updateConditionNode(selectedCondition.id, { side: e.target.value as "long" | "short" })}
                        className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                      >
                        <option value="long">Long</option>
                        <option value="short">Short</option>
                      </select>
                    </div>
                  ) : null}

                  {selectedCondition.type === "cooldown_elapsed" ? (
                    <div>
                      <label className="block text-xs font-medium text-neutral-400 mb-1.5">Cooldown Seconds</label>
                      <input
                        value={selectedCondition.seconds ?? ""}
                        onChange={(e) => updateConditionNode(selectedCondition.id, { seconds: parseOptionalNumber(e.target.value) })}
                        placeholder="60"
                        className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                      />
                    </div>
                  ) : null}

                  {selectedCondition.type === "price_above" || selectedCondition.type === "price_below" ? (
                    <div>
                      <label className="block text-xs font-medium text-neutral-400 mb-1.5">Price Level</label>
                      <input
                        value={selectedCondition.value ?? ""}
                        onChange={(e) => updateConditionNode(selectedCondition.id, { value: parseOptionalNumber(e.target.value) })}
                        placeholder="100000"
                        className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                      />
                    </div>
                  ) : null}

                  {selectedCondition.type === "funding_rate_above" || selectedCondition.type === "funding_rate_below" ? (
                    <div>
                      <label className="block text-xs font-medium text-neutral-400 mb-1.5">Funding Threshold</label>
                      <input
                        value={selectedCondition.value ?? ""}
                        onChange={(e) => updateConditionNode(selectedCondition.id, { value: parseOptionalNumber(e.target.value) })}
                        placeholder={selectedCondition.type === "funding_rate_above" ? "0.01" : "-0.01"}
                        className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                      />
                    </div>
                  ) : null}

                  {selectedCondition.type === "volume_above" || selectedCondition.type === "volume_below" ? (
                    <div>
                      <label className="block text-xs font-medium text-neutral-400 mb-1.5">24h Volume Threshold</label>
                      <input
                        value={selectedCondition.value ?? ""}
                        onChange={(e) => updateConditionNode(selectedCondition.id, { value: parseOptionalNumber(e.target.value) })}
                        placeholder={selectedCondition.type === "volume_above" ? "100000000" : "25000000"}
                        className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                      />
                    </div>
                  ) : null}

                  {selectedCondition.type === "price_change_pct_above" || selectedCondition.type === "price_change_pct_below" ? (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Timeframe</label>
                          <select
                            value={selectedCondition.timeframe ?? "15m"}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { timeframe: e.target.value })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {TIMEFRAME_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Lookback Bars</label>
                          <input
                            value={selectedCondition.period ?? ""}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { period: parseOptionalNumber(e.target.value) })}
                            placeholder="5"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Change Threshold %</label>
                        <input
                          value={selectedCondition.value ?? ""}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { value: parseOptionalNumber(e.target.value) })}
                          placeholder={selectedCondition.type === "price_change_pct_above" ? "1.2" : "-1.2"}
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                    </>
                  ) : null}

                  {selectedCondition.type === "rsi_above" || selectedCondition.type === "rsi_below" ? (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Timeframe</label>
                          <select
                            value={selectedCondition.timeframe ?? "15m"}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { timeframe: e.target.value })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {TIMEFRAME_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">RSI Period</label>
                          <input
                            value={selectedCondition.period ?? ""}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { period: parseOptionalNumber(e.target.value) })}
                            placeholder="14"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Threshold</label>
                        <input
                          value={selectedCondition.value ?? ""}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { value: parseOptionalNumber(e.target.value) })}
                          placeholder={selectedCondition.type === "rsi_above" ? "70" : "30"}
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                    </>
                  ) : null}

                  {selectedCondition.type === "sma_above" || selectedCondition.type === "sma_below" ? (
                    <>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Timeframe</label>
                        <select
                          value={selectedCondition.timeframe ?? "15m"}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { timeframe: e.target.value })}
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        >
                          {TIMEFRAME_OPTIONS.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">SMA Period</label>
                        <input
                          value={selectedCondition.period ?? ""}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { period: parseOptionalNumber(e.target.value) })}
                          placeholder="20"
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                    </>
                  ) : null}

                  {selectedCondition.type === "volatility_above" || selectedCondition.type === "volatility_below" ? (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Timeframe</label>
                          <select
                            value={selectedCondition.timeframe ?? "15m"}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { timeframe: e.target.value })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {TIMEFRAME_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Lookback Bars</label>
                          <input
                            value={selectedCondition.period ?? ""}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { period: parseOptionalNumber(e.target.value) })}
                            placeholder="20"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Volatility Threshold %</label>
                        <input
                          value={selectedCondition.value ?? ""}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { value: parseOptionalNumber(e.target.value) })}
                          placeholder={selectedCondition.type === "volatility_above" ? "1.5" : "0.7"}
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                    </>
                  ) : null}

                  {selectedCondition.type === "bollinger_above_upper" || selectedCondition.type === "bollinger_below_lower" ? (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Timeframe</label>
                          <select
                            value={selectedCondition.timeframe ?? "15m"}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { timeframe: e.target.value })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {TIMEFRAME_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Band Period</label>
                          <input
                            value={selectedCondition.period ?? ""}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { period: parseOptionalNumber(e.target.value) })}
                            placeholder="20"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Deviation Multiplier</label>
                        <input
                          value={selectedCondition.value ?? ""}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { value: parseOptionalNumber(e.target.value) })}
                          placeholder="2"
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                    </>
                  ) : null}

                  {selectedCondition.type === "breakout_above_recent_high" || selectedCondition.type === "breakout_below_recent_low" ? (
                    <>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Timeframe</label>
                        <select
                          value={selectedCondition.timeframe ?? "15m"}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { timeframe: e.target.value })}
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        >
                          {TIMEFRAME_OPTIONS.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Lookback Bars</label>
                        <input
                          value={selectedCondition.period ?? ""}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { period: parseOptionalNumber(e.target.value) })}
                          placeholder="20"
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                    </>
                  ) : null}

                  {selectedCondition.type === "atr_above" || selectedCondition.type === "atr_below" ? (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Timeframe</label>
                          <select
                            value={selectedCondition.timeframe ?? "15m"}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { timeframe: e.target.value })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {TIMEFRAME_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">ATR Period</label>
                          <input
                            value={selectedCondition.period ?? ""}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { period: parseOptionalNumber(e.target.value) })}
                            placeholder="14"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">ATR Threshold %</label>
                        <input
                          value={selectedCondition.value ?? ""}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { value: parseOptionalNumber(e.target.value) })}
                          placeholder={selectedCondition.type === "atr_above" ? "1.1" : "0.6"}
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                    </>
                  ) : null}

                  {selectedCondition.type === "vwap_above" || selectedCondition.type === "vwap_below" ? (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Timeframe</label>
                          <select
                            value={selectedCondition.timeframe ?? "15m"}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { timeframe: e.target.value })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {TIMEFRAME_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">VWAP Bars</label>
                          <input
                            value={selectedCondition.period ?? ""}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { period: parseOptionalNumber(e.target.value) })}
                            placeholder="24"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                    </>
                  ) : null}

                  {selectedCondition.type === "higher_timeframe_sma_above" || selectedCondition.type === "higher_timeframe_sma_below" ? (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Setup Timeframe</label>
                          <select
                            value={selectedCondition.timeframe ?? "15m"}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { timeframe: e.target.value })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {TIMEFRAME_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Confirm Timeframe</label>
                          <select
                            value={selectedCondition.secondary_timeframe ?? "1h"}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { secondary_timeframe: e.target.value })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {TIMEFRAME_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Higher Timeframe SMA</label>
                        <input
                          value={selectedCondition.period ?? ""}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { period: parseOptionalNumber(e.target.value) })}
                          placeholder="20"
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                    </>
                  ) : null}

                  {selectedCondition.type === "ema_crosses_above" || selectedCondition.type === "ema_crosses_below" ? (
                    <>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Timeframe</label>
                        <select
                          value={selectedCondition.timeframe ?? "15m"}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { timeframe: e.target.value })}
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        >
                          {TIMEFRAME_OPTIONS.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Fast EMA</label>
                          <input
                            value={selectedCondition.fast_period ?? ""}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { fast_period: parseOptionalNumber(e.target.value) })}
                            placeholder="9"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Slow EMA</label>
                          <input
                            value={selectedCondition.slow_period ?? ""}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { slow_period: parseOptionalNumber(e.target.value) })}
                            placeholder="21"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                    </>
                  ) : null}

                  {selectedCondition.type === "macd_crosses_above_signal" || selectedCondition.type === "macd_crosses_below_signal" ? (
                    <>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Timeframe</label>
                        <select
                          value={selectedCondition.timeframe ?? "1h"}
                          onChange={(e) => updateConditionNode(selectedCondition.id, { timeframe: e.target.value })}
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        >
                          {TIMEFRAME_OPTIONS.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Fast</label>
                          <input
                            value={selectedCondition.fast_period ?? ""}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { fast_period: parseOptionalNumber(e.target.value) })}
                            placeholder="12"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Slow</label>
                          <input
                            value={selectedCondition.slow_period ?? ""}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { slow_period: parseOptionalNumber(e.target.value) })}
                            placeholder="26"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Signal</label>
                          <input
                            value={selectedCondition.signal_period ?? ""}
                            onChange={(e) => updateConditionNode(selectedCondition.id, { signal_period: parseOptionalNumber(e.target.value) })}
                            placeholder="9"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                    </>
                  ) : null}

                  {selectedCondition.type === "position_pnl_above" || selectedCondition.type === "position_pnl_below" ? (
                    <div>
                      <label className="block text-xs font-medium text-neutral-400 mb-1.5">PnL Threshold USD</label>
                      <input
                        value={selectedCondition.value ?? ""}
                        onChange={(e) => updateConditionNode(selectedCondition.id, { value: parseOptionalNumber(e.target.value) })}
                        placeholder={selectedCondition.type === "position_pnl_above" ? "75" : "-75"}
                        className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                      />
                    </div>
                  ) : null}

                  {selectedCondition.type === "position_pnl_pct_above" || selectedCondition.type === "position_pnl_pct_below" ? (
                    <div>
                      <label className="block text-xs font-medium text-neutral-400 mb-1.5">PnL Threshold %</label>
                      <input
                        value={selectedCondition.value ?? ""}
                        onChange={(e) => updateConditionNode(selectedCondition.id, { value: parseOptionalNumber(e.target.value) })}
                        placeholder={selectedCondition.type === "position_pnl_pct_above" ? "8" : "-5"}
                        className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                      />
                    </div>
                  ) : null}

                  <div className="rounded-md border border-[rgba(255,255,255,0.06)] bg-neutral-800 px-3 py-3 text-xs leading-5 text-neutral-400">
                    {conditionSummary(selectedCondition)}
                  </div>
                </div>
              ) : null}

              {selectedAction ? (
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-neutral-400 mb-1.5">Action Type</label>
                    <select
                      value={selectedAction.type}
                      onChange={(e) => changeActionType(selectedAction.id, e.target.value as (typeof ACTION_OPTIONS)[number])}
                      className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                    >
                      {ACTION_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {actionTitle(option)}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-neutral-400 mb-1.5">Market</label>
                    <select
                      value={selectedAction.symbol}
                      onChange={(e) => updateActionNode(selectedAction.id, { symbol: e.target.value })}
                      className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                    >
                      {blockMarketOptions.map((symbol) => (
                        <option key={symbol} value={symbol}>
                          {symbol === BOT_MARKET_UNIVERSE_SYMBOL ? "Bot market universe" : symbol}
                        </option>
                      ))}
                    </select>
                  </div>

                  {selectedAction.type === "open_long" || selectedAction.type === "open_short" ? (
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Size USD</label>
                        <input
                          value={selectedAction.size_usd ?? ""}
                          onChange={(e) => updateActionNode(selectedAction.id, { size_usd: parseOptionalNumber(e.target.value) })}
                          placeholder="150"
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Leverage</label>
                        <input
                          value={selectedAction.leverage ?? ""}
                          onChange={(e) => updateActionNode(selectedAction.id, { leverage: parseOptionalNumber(e.target.value) })}
                          placeholder="3"
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                    </div>
                  ) : null}

                  {selectedAction.type === "place_market_order" ? (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Side</label>
                          <select
                            value={selectedAction.side ?? "long"}
                            onChange={(e) => updateActionNode(selectedAction.id, { side: e.target.value as "long" | "short" })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {SIDE_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Leverage</label>
                          <input
                            value={selectedAction.leverage ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { leverage: parseOptionalNumber(e.target.value) })}
                            placeholder="3"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Size USD</label>
                          <input
                            value={selectedAction.size_usd ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { size_usd: parseOptionalNumber(e.target.value) })}
                            placeholder="180"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Slippage %</label>
                          <input
                            value={selectedAction.slippage_percent ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { slippage_percent: parseOptionalNumber(e.target.value) })}
                            placeholder="0.25"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <label className="flex items-center justify-between rounded-md border border-[rgba(255,255,255,0.06)] bg-neutral-800 px-3 py-2 text-xs text-neutral-300">
                        <span>Reduce-Only Exit</span>
                        <input
                          type="checkbox"
                          checked={Boolean(selectedAction.reduce_only)}
                          onChange={(e) => updateActionNode(selectedAction.id, { reduce_only: e.target.checked })}
                          className="h-4 w-4 rounded border-[rgba(255,255,255,0.18)] bg-transparent"
                        />
                      </label>
                    </>
                  ) : null}

                  {selectedAction.type === "place_limit_order" ? (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Side</label>
                          <select
                            value={selectedAction.side ?? "long"}
                            onChange={(e) => updateActionNode(selectedAction.id, { side: e.target.value as "long" | "short" })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {SIDE_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Leverage</label>
                          <input
                            value={selectedAction.leverage ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { leverage: parseOptionalNumber(e.target.value) })}
                            placeholder="3"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Quantity</label>
                          <input
                            value={selectedAction.quantity ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { quantity: parseOptionalNumber(e.target.value) })}
                            placeholder="0.01"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Limit Price</label>
                          <input
                            value={selectedAction.price ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { price: parseOptionalNumber(e.target.value) })}
                            placeholder="99500"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Time in Force</label>
                          <select
                            value={selectedAction.tif ?? "GTC"}
                            onChange={(e) => updateActionNode(selectedAction.id, { tif: e.target.value })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {TIF_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Client Order ID</label>
                          <input
                            value={selectedAction.client_order_id ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { client_order_id: e.target.value })}
                            placeholder="maker-entry-001"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <label className="flex items-center justify-between rounded-md border border-[rgba(255,255,255,0.06)] bg-neutral-800 px-3 py-2 text-xs text-neutral-300">
                        <span>Reduce-Only Exit</span>
                        <input
                          type="checkbox"
                          checked={Boolean(selectedAction.reduce_only)}
                          onChange={(e) => updateActionNode(selectedAction.id, { reduce_only: e.target.checked })}
                          className="h-4 w-4 rounded border-[rgba(255,255,255,0.18)] bg-transparent"
                        />
                      </label>
                    </>
                  ) : null}

                  {selectedAction.type === "place_twap_order" ? (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Side</label>
                          <select
                            value={selectedAction.side ?? "long"}
                            onChange={(e) => updateActionNode(selectedAction.id, { side: e.target.value as "long" | "short" })}
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          >
                            {SIDE_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Leverage</label>
                          <input
                            value={selectedAction.leverage ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { leverage: parseOptionalNumber(e.target.value) })}
                            placeholder="2"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Quantity</label>
                          <input
                            value={selectedAction.quantity ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { quantity: parseOptionalNumber(e.target.value) })}
                            placeholder="0.03"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Duration Seconds</label>
                          <input
                            value={selectedAction.duration_seconds ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { duration_seconds: parseOptionalNumber(e.target.value) })}
                            placeholder="1800"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Slippage %</label>
                          <input
                            value={selectedAction.slippage_percent ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { slippage_percent: parseOptionalNumber(e.target.value) })}
                            placeholder="0.35"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-neutral-400 mb-1.5">Client Order ID</label>
                          <input
                            value={selectedAction.client_order_id ?? ""}
                            onChange={(e) => updateActionNode(selectedAction.id, { client_order_id: e.target.value })}
                            placeholder="twap-entry-001"
                            className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                          />
                        </div>
                      </div>
                      <label className="flex items-center justify-between rounded-md border border-[rgba(255,255,255,0.06)] bg-neutral-800 px-3 py-2 text-xs text-neutral-300">
                        <span>Reduce-Only Exit</span>
                        <input
                          type="checkbox"
                          checked={Boolean(selectedAction.reduce_only)}
                          onChange={(e) => updateActionNode(selectedAction.id, { reduce_only: e.target.checked })}
                          className="h-4 w-4 rounded border-[rgba(255,255,255,0.18)] bg-transparent"
                        />
                      </label>
                    </>
                  ) : null}

                  {selectedAction.type === "set_tpsl" ? (
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Take Profit %</label>
                        <input
                          value={selectedAction.take_profit_pct ?? ""}
                          onChange={(e) => updateActionNode(selectedAction.id, { take_profit_pct: parseOptionalNumber(e.target.value) })}
                          placeholder="1.8"
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Stop Loss %</label>
                        <input
                          value={selectedAction.stop_loss_pct ?? ""}
                          onChange={(e) => updateActionNode(selectedAction.id, { stop_loss_pct: parseOptionalNumber(e.target.value) })}
                          placeholder="0.9"
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                    </div>
                  ) : null}

                  {selectedAction.type === "update_leverage" ? (
                    <div>
                      <label className="block text-xs font-medium text-neutral-400 mb-1.5">Target Leverage</label>
                      <input
                        value={selectedAction.leverage ?? ""}
                        onChange={(e) => updateActionNode(selectedAction.id, { leverage: parseOptionalNumber(e.target.value) })}
                        placeholder="3"
                        className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                      />
                    </div>
                  ) : null}

                  {selectedAction.type === "cancel_order" || selectedAction.type === "cancel_twap_order" ? (
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Order ID</label>
                        <input
                          value={selectedAction.order_id ?? ""}
                          onChange={(e) => updateActionNode(selectedAction.id, { order_id: e.target.value })}
                          placeholder="order-001"
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-neutral-400 mb-1.5">Client Order ID</label>
                        <input
                          value={selectedAction.client_order_id ?? ""}
                          onChange={(e) => updateActionNode(selectedAction.id, { client_order_id: e.target.value })}
                          placeholder="maker-entry-001"
                          className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                        />
                      </div>
                    </div>
                  ) : null}

                  {selectedAction.type === "cancel_all_orders" ? (
                    <div className="space-y-3">
                      <label className="flex items-center justify-between rounded-md border border-[rgba(255,255,255,0.06)] bg-neutral-800 px-3 py-2 text-xs text-neutral-300">
                        <span>Cancel Across All Symbols</span>
                        <input
                          type="checkbox"
                          checked={Boolean(selectedAction.all_symbols)}
                          onChange={(e) => updateActionNode(selectedAction.id, { all_symbols: e.target.checked })}
                          className="h-4 w-4 rounded border-[rgba(255,255,255,0.18)] bg-transparent"
                        />
                      </label>
                      <label className="flex items-center justify-between rounded-md border border-[rgba(255,255,255,0.06)] bg-neutral-800 px-3 py-2 text-xs text-neutral-300">
                        <span>Keep Reduce-Only Orders</span>
                        <input
                          type="checkbox"
                          checked={Boolean(selectedAction.exclude_reduce_only)}
                          onChange={(e) => updateActionNode(selectedAction.id, { exclude_reduce_only: e.target.checked })}
                          className="h-4 w-4 rounded border-[rgba(255,255,255,0.18)] bg-transparent"
                        />
                      </label>
                    </div>
                  ) : null}

                  <div className="rounded-md border border-[rgba(255,255,255,0.06)] bg-neutral-800 px-3 py-3 text-xs leading-5 text-neutral-400">
                    {actionSummary(selectedAction)}
                  </div>
                </div>
              ) : null}

              {selectedNode ? (
                <div className="mt-4 pt-4 border-t border-[rgba(255,255,255,0.06)]">
                  <button
                    type="button"
                    onClick={() => removeNode(selectedNode.id)}
                    className="w-full rounded-md border border-[rgba(224,108,110,0.24)] bg-[#2a1718] px-3 py-2 text-sm font-medium text-[#f0a5a6] transition hover:border-[rgba(224,108,110,0.42)] hover:bg-[#311a1b]"
                  >
                    Remove block
                  </button>
                </div>
              ) : null}
            </div>
          </div>

          <div className="border-b border-[rgba(255,255,255,0.06)]">
            <div className="p-4 bg-transparent">
              <h2 className="text-sm font-semibold text-neutral-50 mb-4">Execution Guardrails</h2>

              <div className="grid gap-4">
                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1.5">Owner Wallet</label>
                  <input
                    value={walletAddress}
                    onChange={(e) => setWalletAddress(e.target.value)}
                    readOnly={Boolean(authenticatedWallet)}
                    placeholder="Connect wallet..."
                    className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none text-neutral-400 transition-colors"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-400 mb-1.5">Visibility</label>
                  <select
                    value={visibility}
                    onChange={(e) => setVisibility(e.target.value as "private" | "public" | "unlisted")}
                    className="w-full px-3 py-2 bg-neutral-800 border border-[rgba(255,255,255,0.06)] rounded-md text-neutral-50 text-xs focus:outline-none focus:border-[#dce85d] transition-colors"
                  >
                    <option value="private">Private</option>
                    <option value="public">Public (Leaderboard)</option>
                    <option value="unlisted">Unlisted (Link only)</option>
                  </select>
                </div>

                <div className="mt-2 bg-app border border-[rgba(255,255,255,0.06)] rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-neutral-300">Readiness Score</span>
                    <span className="text-xs font-bold text-[#dce85d]">{readyCount}/4</span>
                  </div>
                  <div className="w-full bg-neutral-800 rounded-full h-1.5">
                    <div className="bg-[#dce85d] h-1.5 rounded-full" style={{ width: `${(readyCount / 4) * 100}%` }}></div>
                  </div>
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-[rgba(255,255,255,0.06)]">
                {onboardingStatus.blocker ? (
                  <button
                    type="button"
                    onClick={onOpenOnboardingGuide}
                    className="mb-3 w-full rounded-lg border border-[rgba(220,232,93,0.24)] bg-[rgba(220,232,93,0.08)] px-3 py-2 text-left text-xs leading-5 text-[#dce85d] transition hover:bg-[rgba(220,232,93,0.12)]"
                  >
                    {onboardingStatus.blocker}
                  </button>
                ) : null}
                <button
                  onClick={createBot}
                  disabled={status === "creating"}
                  className={clsx(
                    "w-full flex justify-center items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all",
                    status === "creating" ? "bg-neutral-800 text-neutral-500" : "bg-white/5 text-white hover:bg-white/10"
                  )}
                >
                  {status === "creating" ? "Saving..." : createdBotId ? "Update Draft" : "Save Sandbox Draft"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
