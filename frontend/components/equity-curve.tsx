"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fmtDateTime, fmtR } from "@/lib/format";
import type { Trade } from "@/lib/types";

interface Point {
  index: number;
  cum: number;
  r: number | null;
  date: string | null;
  oos: boolean;
}

// Sortiert Trades nach trade_datetime (None-Daten stabil ans Ende) und
// bildet die kumulierte R-Summe. split_date markiert (optional) den ersten
// OOS-Trade fuer eine vertikale Trennlinie.
function buildSeries(trades: Trade[], splitDate: string | null): {
  points: Point[];
  splitIndex: number | null;
} {
  const withDate = trades.filter((t) => t.trade_datetime);
  const withoutDate = trades.filter((t) => !t.trade_datetime);
  withDate.sort((a, b) =>
    (a.trade_datetime ?? "").localeCompare(b.trade_datetime ?? ""),
  );
  const ordered = [...withDate, ...withoutDate];

  const points: Point[] = [];
  let cum = 0;
  let splitIndex: number | null = null;
  for (let i = 0; i < ordered.length; i++) {
    const t = ordered[i];
    const r = typeof t.r_value === "number" ? t.r_value : null;
    cum += r ?? 0;
    const oos = Boolean(
      splitDate && t.trade_datetime && t.trade_datetime >= splitDate,
    );
    if (oos && splitIndex === null) splitIndex = i + 1;
    points.push({
      index: i + 1,
      cum: Number(cum.toFixed(4)),
      r,
      date: t.trade_datetime,
      oos,
    });
  }
  return { points, splitIndex };
}

function EquityTooltip({ active, payload }: {
  active?: boolean;
  payload?: Array<{ payload: Point }>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs shadow-lg">
      <div className="text-zinc-400">
        Trade #{p.index}
        {p.date ? ` · ${fmtDateTime(p.date)}` : " · ohne Datum"}
      </div>
      <div className="mt-0.5 font-mono text-zinc-100">
        Kumuliert: {fmtR(p.cum)}R
      </div>
      <div className="font-mono text-zinc-400">Trade: {fmtR(p.r)}R</div>
    </div>
  );
}

interface EquityCurveProps {
  trades: Trade[];
  splitDate?: string | null;
}

export function EquityCurve({ trades, splitDate = null }: EquityCurveProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const { points, splitIndex } = useMemo(
    () => buildSeries(trades, splitDate),
    [trades, splitDate],
  );

  if (points.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center text-sm text-zinc-500">
        Keine Trades vorhanden.
      </div>
    );
  }

  if (!mounted) {
    return <div className="h-[300px] w-full" aria-hidden />;
  }

  const finalCum = points[points.length - 1].cum;
  const positive = finalCum >= 0;
  const stroke = positive ? "#10b981" : "#ef4444";

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart
        data={points}
        margin={{ top: 8, right: 12, bottom: 8, left: 0 }}
      >
        <defs>
          <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
            <stop offset="100%" stopColor={stroke} stopOpacity={0.02} />
          </linearGradient>
        </defs>
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
          content={<EquityTooltip />}
          cursor={{ stroke: "#52525b", strokeDasharray: "3 3" }}
        />
        <ReferenceLine y={0} stroke="#71717a" strokeDasharray="3 3" />
        {splitIndex !== null && (
          <ReferenceLine
            x={splitIndex}
            stroke="#eab308"
            strokeDasharray="4 4"
            label={{ value: "OOS", position: "top", fill: "#eab308", fontSize: 10 }}
          />
        )}
        <Area
          type="monotone"
          dataKey="cum"
          stroke={stroke}
          strokeWidth={2}
          fill="url(#equityFill)"
          isAnimationActive={false}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
