"use client";

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
import { Box, Sparkles, Grid3x3, Activity, Play, Search, ChevronDown, ChevronRight, Plus, Globe, Check } from "lucide-react";
import { clsx } from "clsx";
import { useEffect, useMemo, useState, type DragEvent } from "react";

import { BuilderFlowNodeCard } from "@/components/builder/builder-flow-node";
import {
  ACTION_OPTIONS,
  actionHelper,
  actionSummary,
  actionTitle,
  BLANK_BUILDER_TEMPLATE_ID,
  BOT_MARKET_UNIVERSE_SYMBOL,
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
  DEFAULT_BUILDER_TEMPLATE_ID,
  ENTRY_NODE_ID,
  getBuilderStarterTemplate,
  PALETTE_MIME,
  parseOptionalNumber,
  serializeGraphNode,
  snapPosition,
  type BuilderFlowEdge,
  type BuilderFlowNode,
  type PaletteDragPayload,
  type VisualAction,
  type VisualCondition,
} from "@/components/builder/builder-flow-utils";
import { type PacificaOnboardingStatus } from "@/components/pacifica/onboarding-checklist";
import { useClashxAuth } from "@/lib/clashx-auth";

type BuilderCatalogTemplate = {
  id: string;
  name: string;
  description: string;
  authoring_mode?: string;
  risk_profile?: string;
};
type BuilderMarket = { symbol: string; status: string; volume_24h?: number };
export type BuilderNoticePayload = {
  eyebrow: string;
  title: string;
  detail: string;
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
}: {
  onNotice?: (notice: BuilderNoticePayload) => void;
  onboardingStatus: PacificaOnboardingStatus;
  onOpenOnboardingGuide?: () => void;
}) {
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

  useEffect(() => {
    if (authenticatedWallet) setWalletAddress(authenticatedWallet);
  }, [authenticatedWallet]);

  useEffect(() => {
    void (async () => {
      const [templatesResponse, marketsResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/builder/templates`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/api/builder/markets`, { cache: "no-store" }),
      ]);
      if (templatesResponse.ok) setCatalogTemplates((await templatesResponse.json()) as BuilderCatalogTemplate[]);
      if (marketsResponse.ok) setMarkets((await marketsResponse.json()) as BuilderMarket[]);
    })();
  }, []);

  useEffect(() => {
    if (selectedNodeId && nodes.some((node) => node.id === selectedNodeId && node.data.kind !== "entry")) return;
    setSelectedNodeId(nodes.find((node) => node.data.kind !== "entry")?.id ?? null);
  }, [nodes, selectedNodeId]);

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
    setRuntimeStatus(null);
    setError(null);
    setBlockSearch("");

    requestAnimationFrame(() => {
      flow?.fitView({ padding: 0.24, duration: 280 });
    });
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
    try {
      await persistBotDraft();
      setRuntimeStatus(null);
      onNotice?.({
        eyebrow: "Saved",
        title: "Draft saved",
        detail: "Your changes are ready whenever you want to deploy.",
      });
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Bot save failed");
    } finally {
      setStatus("idle");
    }
  }

  async function deployBot() {
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
    setStatus("deploying");
    setError(null);
    try {
      const botId = await persistBotDraft();
      const response = await fetch(`${API_BASE_URL}/api/bots/${botId}/deploy`, {
        method: "POST",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ wallet_address: walletAddress.trim(), risk_policy_json: { max_leverage: 5, max_order_size_usd: 200, cooldown_seconds: 45, max_drawdown_pct: 18 } }),
      });
      const payload = (await response.json()) as { status?: string; detail?: string };
      if (!response.ok) throw new Error(payload.detail ?? "Deploy failed");
      setRuntimeStatus(payload.status ?? "active");
      onNotice?.({
        eyebrow: "Deployed",
        title: "Bot is live",
        detail: "It will start trading as soon as the strategy conditions are met.",
      });
    } catch (deployError) {
      setError(deployError instanceof Error ? deployError.message : "Deploy failed");
    } finally {
      setStatus("idle");
    }
  }

  return (
    <div className="flex-1 flex flex-col bg-app overflow-hidden">
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
              <button className="flex items-center gap-2 px-3 py-1.5 text-sm rounded transition-all bg-[#dce85d] text-[#090a0a] font-semibold">
                <Grid3x3 className="w-4 h-4" />
                <span>Visual</span>
              </button>
              <button className="flex items-center gap-2 px-3 py-1.5 text-sm rounded transition-all text-neutral-400 hover:text-neutral-300">
                <Sparkles className="w-4 h-4" />
                <span>AI Chat</span>
              </button>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-1 justify-end max-w-2xl">
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
             </div>
             <button
               onClick={deployBot}
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
               className="flex h-9 items-center rounded-md border border-[rgba(255,255,255,0.08)] bg-neutral-900 px-3 text-sm font-semibold text-neutral-200 transition-all hover:border-[rgba(220,232,93,0.34)] hover:text-white"
             >
               Pacifica setup
             </button>
          </div>
        </div>
      </div>

      {/* Main Workspace */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Block Palette */}
        <div className="w-72 flex-shrink-0 border-r border-[rgba(255,255,255,0.06)] bg-[#16181a] flex flex-col">
          <div className="p-4 border-b border-[rgba(255,255,255,0.06)] bg-neutral-900">
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
            {SIGNAL_CATEGORIES.some(c => c.keys.some(k => filteredConditions.includes(k as any))) && (
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
                    options={category.keys.filter(k => filteredConditions.includes(k as any))}
                    searchQuery={blockSearch}
                    kind="condition"
                    onDragStart={handlePaletteDragStart}
                    defaultExpanded={idx === 0}
                  />
                ))}
              </div>
            )}
            
            {ACTION_CATEGORIES.some(c => c.keys.some(k => filteredActions.includes(k as any))) && (
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
                    options={category.keys.filter(k => filteredActions.includes(k as any))}
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
            <Controls className="!bg-[#16181a] !border-[rgba(255,255,255,0.08)] !shadow-xl !flex !flex-col !gap-1 !p-1 [&_button]:!bg-transparent [&_button]:!border-none [&_button]:!rounded-md hover:[&_button]:!bg-white/10 [&_button_svg]:!fill-neutral-400" />
            <MiniMap 
               className="!bg-[#16181a] !border-[rgba(255,255,255,0.06)] rounded-lg overflow-hidden" 
               nodeColor={(node) => {
                  return node.data?.kind === 'condition' ? '#dce85d' : '#74b97f';
               }}
               maskColor="rgba(9, 10, 10, 0.7)"
            />
          </ReactFlow>
        </div>

        {/* Right Sidebar - Settings */}
        <div className="w-80 flex-shrink-0 border-l border-[rgba(255,255,255,0.06)] bg-[#16181a] overflow-y-auto overflow-x-hidden custom-scrollbar flex flex-col">
          <div className="border-b border-[rgba(255,255,255,0.06)]">
            <div className="p-4 bg-neutral-900">
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
            <div className="p-4 bg-neutral-900">
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
            <div className="p-4 bg-neutral-900">
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
            <div className="p-4 bg-neutral-900">
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
                   {status === "creating" ? "Testing..." : "Save Sandbox Draft"}
                 </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
