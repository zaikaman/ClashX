"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useClashxAuth } from "@/lib/clashx-auth";
import type { BotPerformance, BotPosition } from "@/lib/bot-performance";
import type { RuntimeOverview } from "@/lib/runtime-overview";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type RuntimeSummary = {
  id: string;
  status: string;
  mode: string;
  updated_at: string;
  deployed_at?: string | null;
  stopped_at?: string | null;
};

export type BotFleetItem = {
  id: string;
  name: string;
  description: string;
  wallet_address: string;
  visibility: string;
  authoring_mode: string;
  strategy_type: string;
  market_scope: string;
  updated_at: string;
  runtime?: RuntimeSummary | null;
  performance?: BotPerformance | null;
};

export type FleetStatus = "active" | "paused" | "stopped" | "draft";

export function getFleetBotStatus(bot: BotFleetItem): FleetStatus {
  if (!bot.runtime) {
    return "draft";
  }

  if (bot.runtime.status === "active" || bot.runtime.status === "paused" || bot.runtime.status === "stopped") {
    return bot.runtime.status;
  }

  return "draft";
}

export function isLiveFleetStatus(status: FleetStatus) {
  return status === "active" || status === "paused";
}

export function getBotOpenPositions(bot: BotFleetItem): BotPosition[] {
  return bot.performance?.positions ?? [];
}

export function getBotOpenPositionCount(bot: BotFleetItem) {
  return getBotOpenPositions(bot).length;
}

function mergePerformanceSnapshot(
  previous: BotPerformance | null | undefined,
  next: BotPerformance | null | undefined,
  options?: { preservePositions?: boolean },
): BotPerformance | null | undefined {
  if (next == null) {
    return next;
  }

  if (previous == null) {
    return next;
  }

  const shouldPreservePositions =
    options?.preservePositions === true &&
    previous.positions.length > 0 &&
    next.positions.length === 0;

  return {
    ...previous,
    ...next,
    positions: shouldPreservePositions ? previous.positions : next.positions,
  };
}

function mergeFleetSnapshot(
  currentBots: BotFleetItem[],
  incomingBots: BotFleetItem[],
  options?: { preservePositions?: boolean },
) {
  const currentByBotId = new Map(currentBots.map((bot) => [bot.id, bot]));

  return [...incomingBots]
    .map((bot) => {
      const current = currentByBotId.get(bot.id);
      if (!current) {
        return bot;
      }

      return {
        ...current,
        ...bot,
        runtime: bot.runtime ?? null,
        performance: mergePerformanceSnapshot(current.performance, bot.performance, options),
      };
    })
    .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime());
}

async function unwrapResponse<T>(response: Response, fallback: string): Promise<T> {
  const payload = (await response.json()) as unknown;
  if (!response.ok) {
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = payload.detail;
      throw new Error(typeof detail === "string" && detail.length > 0 ? detail : fallback);
    }
    throw new Error(fallback);
  }
  return payload as T;
}

export function useFleetObservability({ refreshIntervalMs = 15000 }: { refreshIntervalMs?: number } = {}) {
  const { ready, authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();
  const sessionActive = ready && authenticated && Boolean(walletAddress);

  const [bots, setBots] = useState<BotFleetItem[]>([]);
  const [overviewByBot, setOverviewByBot] = useState<Record<string, RuntimeOverview | null>>({});
  const [overviewErrors, setOverviewErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loadingBots, setLoadingBots] = useState(true);
  const [loadingOverviews, setLoadingOverviews] = useState(false);
  const [loadingPositions, setLoadingPositions] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [hasLoadedBots, setHasLoadedBots] = useState(false);
  const [hasLoadedOverviews, setHasLoadedOverviews] = useState(false);
  const [hasLoadedPositions, setHasLoadedPositions] = useState(false);
  const [hasLoadedFullPerformance, setHasLoadedFullPerformance] = useState(false);
  const botsRef = useRef<BotFleetItem[]>([]);
  const hasLoadedBotsRef = useRef(false);
  const hasLoadedOverviewsRef = useRef(false);
  const hasLoadedPositionsRef = useRef(false);
  const hasLoadedFullPerformanceRef = useRef(false);
  const sessionWalletRef = useRef<string | null>(null);
  const fullPerformanceInFlightRef = useRef(false);
  const fullPerformanceRequestKeyRef = useRef<string | null>(null);

  useEffect(() => {
    botsRef.current = bots;
    hasLoadedBotsRef.current = hasLoadedBots;
    hasLoadedOverviewsRef.current = hasLoadedOverviews;
    hasLoadedPositionsRef.current = hasLoadedPositions;
    hasLoadedFullPerformanceRef.current = hasLoadedFullPerformance;
    sessionWalletRef.current = sessionActive && walletAddress ? walletAddress : null;
  }, [
    bots,
    hasLoadedBots,
    hasLoadedFullPerformance,
    hasLoadedOverviews,
    hasLoadedPositions,
    sessionActive,
    walletAddress,
  ]);

  useEffect(() => {
    if (!ready) {
      return;
    }

    if (!sessionActive || !walletAddress) {
      setBots([]);
      setOverviewByBot({});
      setOverviewErrors({});
      setError(null);
      setLoadingBots(false);
      setLoadingOverviews(false);
      setLoadingPositions(false);
      setLastUpdatedAt(null);
      setHasLoadedBots(false);
      setHasLoadedOverviews(false);
      setHasLoadedPositions(false);
      setHasLoadedFullPerformance(false);
      sessionWalletRef.current = null;
      fullPerformanceInFlightRef.current = false;
      fullPerformanceRequestKeyRef.current = null;
      return;
    }

    const resolvedWallet = walletAddress;
    const controller = new AbortController();

    async function loadFleet() {
      const hasCachedBots = hasLoadedBotsRef.current;
      const hasCachedOverviews = hasLoadedOverviewsRef.current;
      const hasCachedPositions = hasLoadedPositionsRef.current;
      const hasCachedFullPerformance = hasLoadedFullPerformanceRef.current;
      const performanceMode = "full";

      setLoadingBots(!hasCachedBots);
      setLoadingOverviews(!hasCachedOverviews);
      setLoadingPositions(!hasCachedPositions);

      try {
        const headers = await getAuthHeaders();
        const walletQuery = encodeURIComponent(resolvedWallet);
        const fleetResponse = await fetch(
          `${API_BASE_URL}/api/bots?wallet_address=${walletQuery}&include_performance=true&performance_mode=${performanceMode}`,
          {
            headers,
            signal: controller.signal,
          },
        );
        const nextBots = await unwrapResponse<BotFleetItem[]>(fleetResponse, "Could not load fleet activity");

        if (controller.signal.aborted) {
          return;
        }

        const mergedBots = mergeFleetSnapshot(botsRef.current, nextBots, {
          preservePositions: hasCachedPositions,
        });

        setBots(mergedBots);
        setError(null);
        setLoadingBots(false);
        setLoadingPositions(false);
        setHasLoadedBots(true);
        setHasLoadedPositions(true);
        if (performanceMode === "full") {
          setHasLoadedFullPerformance(true);
        }
        setLastUpdatedAt(new Date().toISOString());

        const botsWithRuntime = mergedBots.filter((bot) => Boolean(bot.runtime?.id));
        const liveRuntimeBots = botsWithRuntime.filter((bot) => isLiveFleetStatus(getFleetBotStatus(bot)));

        if (botsWithRuntime.length === 0) {
          setLoadingOverviews(false);
          setLoadingPositions(false);
          setHasLoadedOverviews(true);
          setHasLoadedPositions(true);
          setHasLoadedFullPerformance(true);
          setLastUpdatedAt(new Date().toISOString());
          return;
        }

        if (liveRuntimeBots.length === 0) {
          setLoadingPositions(false);
          setHasLoadedPositions(true);
          setHasLoadedFullPerformance(true);
        }
        const hydrateOverviews = (async () => {
          try {
            const response = await fetch(
              `${API_BASE_URL}/api/bots/runtime-overviews?wallet_address=${walletQuery}`,
              {
                headers,
                signal: controller.signal,
              },
            );
            const overviewPayload = await unwrapResponse<Record<string, RuntimeOverview>>(
              response,
              "Could not load runtime observability",
            );

            if (controller.signal.aborted) {
              return;
            }

            setOverviewByBot(overviewPayload);
            setOverviewErrors({});
            setHasLoadedOverviews(true);
            setLastUpdatedAt(new Date().toISOString());
          } catch (loadError) {
            if (controller.signal.aborted) {
              return;
            }

            const message =
              loadError instanceof Error ? loadError.message : "Could not load runtime observability";
            setOverviewErrors(
              Object.fromEntries(
                botsWithRuntime.map((bot) => [bot.id, message]),
              ),
            );
          } finally {
            if (!controller.signal.aborted) {
              setLoadingOverviews(false);
            }
          }
        })();

        const shouldHydratePerformance =
          performanceMode !== "full" &&
          liveRuntimeBots.length > 0 &&
          !hasCachedFullPerformance &&
          !fullPerformanceInFlightRef.current;

        if (shouldHydratePerformance) {
          const requestKey = `${resolvedWallet}:${Date.now()}`;
          fullPerformanceInFlightRef.current = true;
          fullPerformanceRequestKeyRef.current = requestKey;

          void (async () => {
            try {
              const response = await fetch(
                `${API_BASE_URL}/api/bots?wallet_address=${walletQuery}&include_performance=true&performance_mode=full`,
                {
                  headers,
                },
              );
              const fullFleet = await unwrapResponse<BotFleetItem[]>(
                response,
                "Could not load runtime performance",
              );

              if (
                sessionWalletRef.current !== resolvedWallet ||
                fullPerformanceRequestKeyRef.current !== requestKey
              ) {
                return;
              }

              setBots((current) => mergeFleetSnapshot(current, fullFleet));
              setHasLoadedFullPerformance(true);
              setLastUpdatedAt(new Date().toISOString());
            } finally {
              if (fullPerformanceRequestKeyRef.current === requestKey) {
                fullPerformanceInFlightRef.current = false;
              }
            }
          })();
        }

        await Promise.allSettled([hydrateOverviews]);
      } catch (loadError) {
        if (controller.signal.aborted) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Could not load fleet activity");
        if (!hasCachedBots) {
          setBots([]);
          setOverviewByBot({});
          setOverviewErrors({});
          setHasLoadedBots(false);
          setHasLoadedOverviews(false);
          setHasLoadedPositions(false);
          setHasLoadedFullPerformance(false);
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoadingBots(false);
          setLoadingOverviews(false);
          setLoadingPositions(false);
        }
      }
    }

    void loadFleet();
    return () => controller.abort();
  }, [getAuthHeaders, ready, refreshToken, sessionActive, walletAddress]);

  useEffect(() => {
    if (!ready || !sessionActive || refreshIntervalMs <= 0) {
      return;
    }

    const interval = window.setInterval(() => {
      setRefreshToken((value) => value + 1);
    }, refreshIntervalMs);

    return () => window.clearInterval(interval);
  }, [ready, refreshIntervalMs, sessionActive]);

  const liveBots = useMemo(
    () => bots.filter((bot) => isLiveFleetStatus(getFleetBotStatus(bot))),
    [bots],
  );

  const openPositions = useMemo(
    () =>
      bots.flatMap((bot) =>
        getBotOpenPositions(bot).map((position) => ({
          botId: bot.id,
          botName: bot.name,
          botStatus: getFleetBotStatus(bot),
          position,
        })),
      ),
    [bots],
  );

  return {
    ready,
    authenticated,
    login,
    walletAddress,
    sessionActive,
    bots,
    liveBots,
    openPositions,
    overviewByBot,
    overviewErrors,
    error,
    loading: loadingBots,
    loadingBots,
    loadingOverviews,
    loadingPositions,
    lastUpdatedAt,
    refresh: () => setRefreshToken((value) => value + 1),
  };
}
