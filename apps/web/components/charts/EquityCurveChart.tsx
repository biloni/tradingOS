"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from "lightweight-charts";
import type { EquityPoint } from "@/lib/api/backtests";

// See CandlestickChart.tsx for why resize uses a manual ResizeObserver +
// chart.applyOptions() rather than the autoSize convenience flag — autoSize
// was observed live to leave the canvas's pixel buffer at the browser
// default (300x150) in this app's flex layout, even though its CSS size
// was correct.
export function EquityCurveChart({ points }: { points: EquityPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);

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
    const series = chart.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 2 });
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
    const data: LineData<Time>[] = points.map((point) => ({
      time: point.as_of as Time,
      value: Number(point.equity),
    }));
    seriesRef.current.setData(data);
  }, [points]);

  return <div ref={containerRef} className="h-72 w-full" />;
}
