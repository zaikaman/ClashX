"use client";

import { useEffect, useRef } from "react";
import {
  AreaSeries,
  createChart,
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

    visibleRuns.forEach((run, index) => {
      const isPrimarySeries = index === 0;
      const seriesType = isPrimarySeries ? AreaSeries : LineSeries;
      const equitySeries = chart.addSeries(seriesType, {
        priceScaleId: "left",
        color: EQUITY_COLORS[index % EQUITY_COLORS.length],
        lineWidth: isPrimarySeries ? 3 : 2,
        lastValueVisible: true,
        crosshairMarkerVisible: true,
        priceFormat: {
          type: "price",
          precision: 2,
          minMove: 0.01,
        },
        ...(isPrimarySeries
          ? {
              lineColor: EQUITY_COLORS[index % EQUITY_COLORS.length],
              topColor: "rgba(220,232,93,0.24)",
              bottomColor: "rgba(220,232,93,0.02)",
            }
          : {}),
      });
      equitySeries.setData(
        run.result_json.equity_curve.map((point) => ({
          time: asUtc(point.time),
          value: point.equity,
        })),
      );
    });

    chart.timeScale().fitContent();
    const resizeObserver = new ResizeObserver(() => {
      chart.timeScale().fitContent();
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
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
