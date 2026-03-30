"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";

import type { BacktestRunDetail } from "@/lib/backtests";

function asUtc(value: number): UTCTimestamp {
  return Math.floor(value / 1000) as UTCTimestamp;
}

const EQUITY_COLORS = ["#dce85d", "#74b97f", "#8ec5ff", "#f59e0b"];

export function BacktestChart({
  runs,
}: {
  runs: BacktestRunDetail[];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const visibleRuns = runs.filter((run) => run.result_json.equity_curve.length > 0);
  const primaryRun = visibleRuns[0] ?? null;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !primaryRun) {
      return;
    }

    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { color: "#090a0a" },
        textColor: "#a1a1aa",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.05)" },
        horzLines: { color: "rgba(255,255,255,0.05)" },
      },
      crosshair: {
        vertLine: { color: "rgba(220,232,93,0.2)" },
        horzLine: { color: "rgba(220,232,93,0.2)" },
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.08)",
        timeVisible: true,
      },
      rightPriceScale: {
        visible: false,
      },
      leftPriceScale: {
        visible: true,
        borderColor: "rgba(255,255,255,0.08)",
      },
    });
    chartRef.current = chart;

    const seriesRefs = visibleRuns.map((run, index) => {
      const equitySeries = chart.addSeries(LineSeries, {
        priceScaleId: "left",
        color: EQUITY_COLORS[index % EQUITY_COLORS.length],
        lineWidth: index === 0 ? 3 : 2,
        lastValueVisible: true,
        crosshairMarkerVisible: true,
        priceFormat: {
          type: "price",
          precision: 2,
          minMove: 0.01,
        },
      });
      equitySeries.setData(
        run.result_json.equity_curve.map((point) => ({
          time: asUtc(point.time),
          value: point.equity,
        })),
      );
      return equitySeries;
    });

    const markerPlugin = createSeriesMarkers(seriesRefs[0]);
    markerPlugin.setMarkers(
      primaryRun.result_json.trades.flatMap((trade) => {
        const entryMarker = {
          time: asUtc(new Date(trade.entry_time).getTime()),
          position: trade.side === "long" ? "belowBar" : "aboveBar",
          color: trade.side === "long" ? "#74b97f" : "#e06c6e",
          shape: trade.side === "long" ? "arrowUp" : "arrowDown",
          text: trade.side === "long" ? "L" : "S",
        } as const;
        if (!trade.exit_time) {
          return [entryMarker];
        }
        const exitMarker = {
          time: asUtc(new Date(trade.exit_time).getTime()),
          position: trade.side === "long" ? "aboveBar" : "belowBar",
          color: "#dce85d",
          shape: "circle",
          text: trade.close_reason ? trade.close_reason.slice(0, 2).toUpperCase() : "X",
        } as const;
        return [entryMarker, exitMarker];
      }),
    );

    chart.timeScale().fitContent();
    const resizeObserver = new ResizeObserver(() => {
      chart.timeScale().fitContent();
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      markerPlugin.setMarkers([]);
      chart.remove();
      chartRef.current = null;
    };
  }, [primaryRun, visibleRuns]);

  if (!runs.length) {
    return (
      <div className="flex min-h-[26rem] items-center justify-center rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a] text-sm text-neutral-500">
        Open a run from history to load the balance curve.
      </div>
    );
  }

  if (!primaryRun) {
    return (
      <div className="flex min-h-[26rem] items-center justify-center rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a] text-sm text-neutral-500">
        This run did not produce an equity curve.
      </div>
    );
  }

  return <div ref={containerRef} className="min-h-[26rem] rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a]" />;
}
