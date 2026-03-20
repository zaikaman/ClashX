"use client";

import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
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

const EQUITY_COLORS = ["#dce85d", "#74b97f", "#8ec5ff"];

export function BacktestChart({
  run,
  compareRuns,
}: {
  run: BacktestRunDetail | null;
  compareRuns: BacktestRunDetail[];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !run) {
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
        borderColor: "rgba(255,255,255,0.08)",
      },
      leftPriceScale: {
        visible: true,
        borderColor: "rgba(255,255,255,0.08)",
      },
    });
    chartRef.current = chart;

    const result = run.result_json;
    const primarySymbol = result.price_series.primary_symbol;
    const priceData = primarySymbol ? result.price_series.series_by_symbol[primarySymbol] ?? [] : [];
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#74b97f",
      downColor: "#e06c6e",
      wickUpColor: "#74b97f",
      wickDownColor: "#e06c6e",
      borderVisible: false,
      priceScaleId: "right",
    });
    candlestickSeries.setData(
      priceData.map((candle) => ({
        time: asUtc(candle.time),
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      })),
    );

    const markerPlugin = createSeriesMarkers(candlestickSeries);
    markerPlugin.setMarkers(
      result.trades.flatMap((trade) => {
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

    const visibleCompareRuns = compareRuns.length > 0 ? compareRuns : [run];
    const equitySeriesRefs = [];
    visibleCompareRuns.forEach((compareRun, index) => {
      const equitySeries = chart.addSeries(LineSeries, {
        priceScaleId: "left",
        color: EQUITY_COLORS[index % EQUITY_COLORS.length],
        lineWidth: compareRun.id === run.id ? 3 : 2,
        lastValueVisible: true,
        crosshairMarkerVisible: true,
      });
      equitySeries.setData(
        compareRun.result_json.equity_curve.map((point) => ({
          time: asUtc(point.time),
          value: point.equity,
        })),
      );
      equitySeriesRefs.push(equitySeries);
    });

    chart.timeScale().fitContent();
    const resizeObserver = new ResizeObserver(() => {
      chart.timeScale().fitContent();
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      equitySeriesRefs.length = 0;
      markerPlugin.setMarkers([]);
      chart.remove();
      chartRef.current = null;
    };
  }, [compareRuns, run]);

  if (!run) {
    return (
      <div className="flex min-h-[26rem] items-center justify-center rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a] text-sm text-neutral-500">
        Run a backtest or open one from history to load the chart.
      </div>
    );
  }

  return <div ref={containerRef} className="min-h-[26rem] rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#090a0a]" />;
}
