"use client";

import { useEffect, useMemo, useState } from "react";

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
  const { authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();
  const sessionActive = authenticated && Boolean(walletAddress);

  const [bots, setBots] = useState<BotFleetItem[]>([]);
  const [overviewByBot, setOverviewByBot] = useState<Record<string, RuntimeOverview | null>>({});
  const [overviewErrors, setOverviewErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loadingBots, setLoadingBots] = useState(true);
  const [loadingOverviews, setLoadingOverviews] = useState(false);
  const [loadingPositions, setLoadingPositions] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionActive || !walletAddress) {
      setBots([]);
      setOverviewByBot({});
      setOverviewErrors({});
      setError(null);
      setLoadingBots(false);
      setLoadingOverviews(false);
      setLoadingPositions(false);
      setLastUpdatedAt(null);
      return;
    }

    const resolvedWallet = walletAddress;
    const controller = new AbortController();

    async function loadFleet() {
      setLoadingBots(true);
      setLoadingOverviews(true);
      setLoadingPositions(true);
      setOverviewErrors({});

      try {
        const headers = await getAuthHeaders();
        const walletQuery = encodeURIComponent(resolvedWallet);
        const fleetResponse = await fetch(
          `${API_BASE_URL}/api/bots?wallet_address=${walletQuery}&include_performance=true&performance_mode=fast`,
          {
            headers,
            signal: controller.signal,
          },
        );
        const nextBots = await unwrapResponse<BotFleetItem[]>(fleetResponse, "Could not load fleet activity");

        if (controller.signal.aborted) {
          return;
        }

        const sortedBots = [...nextBots].sort(
          (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
        );

        setBots(sortedBots);
        setError(null);
        setLoadingBots(false);
        setLastUpdatedAt(new Date().toISOString());

        const botsWithRuntime = sortedBots.filter((bot) => Boolean(bot.runtime?.id));
        const liveRuntimeBots = botsWithRuntime.filter((bot) => isLiveFleetStatus(getFleetBotStatus(bot)));

        if (botsWithRuntime.length === 0) {
          setLoadingOverviews(false);
          setLoadingPositions(false);
          setLastUpdatedAt(new Date().toISOString());
          return;
        }

        setOverviewByBot({});
        if (liveRuntimeBots.length === 0) {
          setLoadingPositions(false);
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

        const hydratePerformance = (async () => {
          try {
            const response = await fetch(
              `${API_BASE_URL}/api/bots?wallet_address=${walletQuery}&include_performance=true&performance_mode=full`,
              {
                headers,
                signal: controller.signal,
              },
            );
            const fullFleet = await unwrapResponse<BotFleetItem[]>(
              response,
              "Could not load runtime performance",
            );

            if (controller.signal.aborted) {
              return;
            }

            const fullFleetByBot = new Map(fullFleet.map((bot) => [bot.id, bot]));
            setBots((current) =>
              current.map((bot) => {
                const nextBot = fullFleetByBot.get(bot.id);
                return nextBot
                  ? {
                      ...bot,
                      runtime: nextBot.runtime ?? bot.runtime,
                      performance: nextBot.performance ?? bot.performance,
                    }
                  : bot;
              }),
            );
            setLastUpdatedAt(new Date().toISOString());
          } finally {
            if (!controller.signal.aborted) {
              setLoadingPositions(false);
            }
          }
        })();

        await Promise.allSettled([hydrateOverviews, hydratePerformance]);
      } catch (loadError) {
        if (controller.signal.aborted) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Could not load fleet activity");
        setBots([]);
        setOverviewByBot({});
        setOverviewErrors({});
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
  }, [getAuthHeaders, refreshToken, sessionActive, walletAddress]);

  useEffect(() => {
    if (!sessionActive || refreshIntervalMs <= 0) {
      return;
    }

    const interval = window.setInterval(() => {
      setRefreshToken((value) => value + 1);
    }, refreshIntervalMs);

    return () => window.clearInterval(interval);
  }, [refreshIntervalMs, sessionActive]);

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
