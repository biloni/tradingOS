"use client";

import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import type { PriceBar } from "@/lib/api/symbols";

/**
 * lightweight-charts v5 (verified against the real API, not v4-era training
 * data): series are created via chart.addSeries(CandlestickSeries, options)
 * with a tree-shaken series-type import, and the chart instance is created
 * once and torn down with chart.remove() in the effect cleanup — React 19
 * Strict Mode double-invokes effects in dev, so skipping cleanup would
 * visibly leak/duplicate the chart on first load.
 *
 * Resize: `autoSize: true` was tried first (the newer v5 convenience flag)
 * but was observed live, in this app's flex/sidebar layout, to resize the
 * canvas's CSS size correctly while leaving its underlying pixel buffer
 * stuck at the browser's default 300x150 — a blurry, wrongly-scaled chart.
 * A manual ResizeObserver calling `chart.applyOptions({width, height})`
 * (the pattern the library's own official React tutorial demonstrates) is
 * what's used here instead, and was verified to size the canvas correctly.
 */
export function CandlestickChart({ bars }: { bars: PriceBar[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart: IChartApi = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: { background: { color: "transparent" }, textColor: "#71717a" },
      grid: {
        vertLines: { color: "rgba(113, 113, 122, 0.1)" },
        horzLines: { color: "rgba(113, 113, 122, 0.1)" },
      },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });
    seriesRef.current = series;

    const resizeObserver = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      chart.applyOptions({ width, height });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current) return;
    const data: CandlestickData<Time>[] = bars.map((bar) => ({
      time: bar.as_of as Time,
      open: Number(bar.open),
      high: Number(bar.high),
      low: Number(bar.low),
      close: Number(bar.close),
    }));
    seriesRef.current.setData(data);
  }, [bars]);

  return <div ref={containerRef} className="h-96 w-full" />;
}
