"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const BIN_WIDTH = 0.5;

interface Bin {
  start: number;
  end: number;
  label: string;
  count: number;
  negative: boolean;
}

// Bildet Bins fester Breite (0.5R) ueber den Wertebereich min..max.
function buildBins(values: number[]): Bin[] {
  const clean = values.filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (clean.length === 0) return [];

  const min = Math.min(...clean);
  const max = Math.max(...clean);

  // Auf Bin-Grenzen ausrichten.
  const first = Math.floor(min / BIN_WIDTH) * BIN_WIDTH;
  const last = Math.floor(max / BIN_WIDTH) * BIN_WIDTH;

  const bins: Bin[] = [];
  for (let start = first; start <= last + 1e-9; start += BIN_WIDTH) {
    const end = start + BIN_WIDTH;
    bins.push({
      start,
      end,
      // Bin-Mittelpunkt bestimmt Farbe: enthaelt der Bin negatives R?
      negative: start < -1e-9,
      label: `${start.toFixed(1)}`,
      count: 0,
    });
  }

  for (const v of clean) {
    let idx = Math.floor((v - first) / BIN_WIDTH);
    if (idx < 0) idx = 0;
    if (idx >= bins.length) idx = bins.length - 1;
    bins[idx].count += 1;
  }

  return bins;
}

function HistTooltip({ active, payload }: {
  active?: boolean;
  payload?: Array<{ payload: Bin }>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const bin = payload[0].payload;
  return (
    <div className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs shadow-lg">
      <div className="font-mono text-zinc-200">
        {bin.start.toFixed(2)}R … {bin.end.toFixed(2)}R
      </div>
      <div className="mt-0.5 text-zinc-400">
        {bin.count} {bin.count === 1 ? "Trade" : "Trades"}
      </div>
    </div>
  );
}

interface RHistogramProps {
  values: number[];
}

export function RHistogram({ values }: RHistogramProps) {
  // recharts nur clientseitig rendern (kein SSR / Hydration-Mismatch).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const bins = useMemo(() => buildBins(values), [values]);

  if (bins.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center text-sm text-zinc-500">
        Keine R-Werte vorhanden.
      </div>
    );
  }

  if (!mounted) {
    return <div className="h-[300px] w-full" aria-hidden />;
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={bins} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
        <XAxis
          dataKey="label"
          stroke="#52525b"
          tick={{ fill: "#a1a1aa", fontSize: 11 }}
          tickLine={{ stroke: "#3f3f46" }}
          axisLine={{ stroke: "#3f3f46" }}
          interval="preserveStartEnd"
        />
        <YAxis
          stroke="#52525b"
          tick={{ fill: "#a1a1aa", fontSize: 11 }}
          tickLine={{ stroke: "#3f3f46" }}
          axisLine={{ stroke: "#3f3f46" }}
          allowDecimals={false}
        />
        <Tooltip
          content={<HistTooltip />}
          cursor={{ fill: "rgba(255,255,255,0.04)" }}
        />
        <ReferenceLine x="0.0" stroke="#71717a" strokeDasharray="3 3" />
        <Bar dataKey="count" radius={[2, 2, 0, 0]} isAnimationActive={false}>
          {bins.map((bin, i) => (
            <Cell
              key={i}
              fill={bin.negative ? "rgba(239,68,68,0.7)" : "rgba(16,185,129,0.7)"}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
