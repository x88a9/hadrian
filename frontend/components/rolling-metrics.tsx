"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { cn } from "@/lib/utils";
import { fmtR } from "@/lib/format";
import type { Trade } from "@/lib/types";

const WINDOWS = [10, 20, 50] as const;
type Window = (typeof WINDOWS)[number];
const DEFAULT_WINDOW: Window = 20;

interface Point {
  index: number;
  ev: number;
  date: string | null;
}

// Chronologisch sortierte R-Werte (gleiche Sortierregel wie equity-curve:
// trade_datetime asc, Trades ohne Datum stabil ans Ende), reduziert auf
// Eintraege mit numerischem r_value.
function orderedRTrades(trades: Trade[]): Array<{ r: number; date: string | null }> {
  const withDate = trades.filter((t) => t.trade_datetime);
  const withoutDate = trades.filter((t) => !t.trade_datetime);
  withDate.sort((a, b) =>
    (a.trade_datetime ?? "").localeCompare(b.trade_datetime ?? ""),
  );
  return [...withDate, ...withoutDate]
    .filter((t) => typeof t.r_value === "number" && !Number.isNaN(t.r_value))
    .map((t) => ({ r: t.r_value as number, date: t.trade_datetime }));
}

// Rolling EV = Mittel der letzten N R-Werte; Punkte ab Trade N.
function buildSeries(
  rows: Array<{ r: number; date: string | null }>,
  window: number,
): Point[] {
  const points: Point[] = [];
  for (let i = window - 1; i < rows.length; i++) {
    let sum = 0;
    for (let j = i - window + 1; j <= i; j++) sum += rows[j].r;
    points.push({
      index: i + 1,
      ev: Number((sum / window).toFixed(4)),
      date: rows[i].date,
    });
  }
  return points;
}

function RollingTooltip({ active, payload }: {
  active?: boolean;
  payload?: Array<{ payload: Point }>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs shadow-lg">
      <div className="text-zinc-400">Trade #{p.index}</div>
      <div className="mt-0.5 font-mono text-zinc-100">
        Rolling EV: {fmtR(p.ev)}R
      </div>
    </div>
  );
}

interface RollingMetricsProps {
  trades: Trade[];
}

export function RollingMetrics({ trades }: RollingMetricsProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [window, setWindow] = useState<Window>(DEFAULT_WINDOW);

  const rows = useMemo(() => orderedRTrades(trades), [trades]);
  const points = useMemo(() => buildSeries(rows, window), [rows, window]);

  const toggle = (
    <div className="flex items-center gap-1">
      {WINDOWS.map((w) => (
        <button
          key={w}
          type="button"
          onClick={() => setWindow(w)}
          className={cn(
            "h-7 rounded-md border px-2.5 text-xs font-mono tabular-nums transition-colors",
            w === window
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200",
          )}
        >
          {w}
        </button>
      ))}
    </div>
  );

  const header = (
    <div className="mb-2 flex items-center justify-between">
      <span className="text-xs text-zinc-500">
        Fenster (letzte N Trades)
      </span>
      {toggle}
    </div>
  );

  if (rows.length < window) {
    return (
      <div className="flex flex-col">
        {header}
        <div className="flex h-[300px] items-center justify-center text-center text-sm text-zinc-500">
          Zu wenige R-Trades ({rows.length}) für ein Fenster von {window}.
        </div>
      </div>
    );
  }

  if (!mounted) {
    return (
      <div className="flex flex-col">
        {header}
        <div className="h-[300px] w-full" aria-hidden />
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {header}
      <ResponsiveContainer width="100%" height={300}>
        <LineChart
          data={points}
          margin={{ top: 8, right: 12, bottom: 8, left: 0 }}
        >
          <XAxis
            dataKey="index"
            stroke="#52525b"
            tick={{ fill: "#a1a1aa", fontSize: 11 }}
            tickLine={{ stroke: "#3f3f46" }}
            axisLine={{ stroke: "#3f3f46" }}
          />
          <YAxis
            stroke="#52525b"
            tick={{ fill: "#a1a1aa", fontSize: 11 }}
            tickLine={{ stroke: "#3f3f46" }}
            axisLine={{ stroke: "#3f3f46" }}
            width={44}
          />
          <Tooltip
            content={<RollingTooltip />}
            cursor={{ stroke: "#52525b", strokeDasharray: "3 3" }}
          />
          <ReferenceLine y={0} stroke="#71717a" strokeDasharray="3 3" />
          <Line
            type="monotone"
            dataKey="ev"
            stroke="#38bdf8"
            strokeWidth={2}
            isAnimationActive={false}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
