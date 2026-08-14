"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ApiError, getMonteCarlo } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { MonteCarloResponse } from "@/lib/types";

function StatTile({
  label,
  value,
  accent,
  sub,
}: {
  label: string;
  value: string;
  accent?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
      <div className="text-[0.7rem] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className={cn("font-mono text-lg text-zinc-100", accent)}>{value}</div>
      {sub && <div className="font-mono text-[11px] text-zinc-500">{sub}</div>}
    </div>
  );
}

interface HistBar {
  mid: number;
  label: string;
  count: number;
  negative: boolean;
}

interface FanPoint {
  step: number;
  outer: [number, number];
  inner: [number, number];
  p50: number;
}

function fmt3(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(3);
}

function HistTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: HistBar }>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const b = payload[0].payload;
  return (
    <div className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs shadow-lg">
      <div className="font-mono text-zinc-200">EV ≈ {b.mid.toFixed(3)}</div>
      <div className="mt-0.5 text-zinc-400">{b.count} Iterationen</div>
    </div>
  );
}

function FanTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: FanPoint }>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs shadow-lg">
      <div className="text-zinc-400">Trade #{p.step}</div>
      <div className="mt-0.5 font-mono text-zinc-100">p50 {fmt3(p.p50)}R</div>
      <div className="font-mono text-zinc-400">
        p25–p75 {fmt3(p.inner[0])} … {fmt3(p.inner[1])}
      </div>
      <div className="font-mono text-zinc-500">
        p5–p95 {fmt3(p.outer[0])} … {fmt3(p.outer[1])}
      </div>
    </div>
  );
}

export function MonteCarloPanel({ systemId }: { systemId: number }) {
  const [data, setData] = useState<MonteCarloResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getMonteCarlo(systemId)
      .then((r) => {
        if (active) setData(r);
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof ApiError ? err.message : "Fehler beim Laden");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [systemId]);

  const hist = useMemo<HistBar[]>(() => {
    if (!data) return [];
    return data.ev_histogram.map((b) => {
      const mid = (b.bin_start + b.bin_end) / 2;
      return {
        mid,
        label: mid.toFixed(2),
        count: b.count,
        negative: mid < 0,
      };
    });
  }, [data]);

  const fan = useMemo<FanPoint[]>(() => {
    if (!data) return [];
    const f = data.equity_fan;
    const n = f.steps.length;
    const out: FanPoint[] = [];
    for (let i = 0; i < n; i++) {
      out.push({
        step: f.steps[i],
        outer: [f.p5[i], f.p95[i]],
        inner: [f.p25[i], f.p75[i]],
        p50: f.p50[i],
      });
    }
    return out;
  }, [data]);

  if (loading && !data) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-zinc-500">
        Lade Monte-Carlo …
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-900/50 bg-red-950/20 px-3 py-2 text-sm text-red-300">
        {error}
      </div>
    );
  }

  if (!data) return null;

  if (data.n_trades === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-900/30 text-sm text-zinc-500">
        Keine R-Werte für Monte-Carlo vorhanden.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatTile
          label="P(EV > 0)"
          value={
            data.p_ev_positive === null
              ? "—"
              : `${(data.p_ev_positive * 100).toFixed(1)}%`
          }
          accent={
            data.p_ev_positive !== null && data.p_ev_positive >= 0.5
              ? "text-emerald-300"
              : "text-amber-300"
          }
          sub={`${data.n_iterations} Iterationen`}
        />
        <StatTile
          label="EV p50"
          value={fmt3(data.ev_p50)}
          accent={
            data.ev_p50 !== null && data.ev_p50 >= 0
              ? "text-emerald-300"
              : "text-red-300"
          }
        />
        <StatTile
          label="EV p5 – p95"
          value={`${fmt3(data.ev_p5)} … ${fmt3(data.ev_p95)}`}
        />
        <StatTile
          label="Trades / Horizont"
          value={`${data.n_trades} / ${data.horizon}`}
        />
      </div>

      {/* EV-Histogramm */}
      <div>
        <div className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
          EV-Verteilung (Bootstrap)
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
          {mounted && hist.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart
                data={hist}
                margin={{ top: 8, right: 12, bottom: 8, left: 0 }}
              >
                <XAxis
                  dataKey="label"
                  stroke="#52525b"
                  tick={{ fill: "#a1a1aa", fontSize: 10 }}
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
                  width={44}
                />
                <Tooltip
                  content={<HistTooltip />}
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                />
                <ReferenceLine x="0.00" stroke="#71717a" strokeDasharray="3 3" />
                <Bar dataKey="count" radius={[2, 2, 0, 0]} isAnimationActive={false}>
                  {hist.map((b, i) => (
                    <Cell
                      key={i}
                      fill={
                        b.negative
                          ? "rgba(239,68,68,0.7)"
                          : "rgba(16,185,129,0.7)"
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[240px] w-full" aria-hidden />
          )}
        </div>
      </div>

      {/* Equity-Fan */}
      <div>
        <div className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
          Equity-Fan (kumuliertes R, Perzentil-Bänder)
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
          {mounted && fan.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart
                data={fan}
                margin={{ top: 8, right: 12, bottom: 8, left: 0 }}
              >
                <XAxis
                  dataKey="step"
                  type="number"
                  domain={["dataMin", "dataMax"]}
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
                  content={<FanTooltip />}
                  cursor={{ stroke: "#52525b", strokeDasharray: "3 3" }}
                />
                <ReferenceLine y={0} stroke="#71717a" strokeDasharray="3 3" />
                {/* p5–p95: schwaches Band */}
                <Area
                  dataKey="outer"
                  stroke="none"
                  fill="#38bdf8"
                  fillOpacity={0.12}
                  isAnimationActive={false}
                  activeDot={false}
                />
                {/* p25–p75: staerkeres Band */}
                <Area
                  dataKey="inner"
                  stroke="none"
                  fill="#38bdf8"
                  fillOpacity={0.28}
                  isAnimationActive={false}
                  activeDot={false}
                />
                {/* p50: Median-Linie */}
                <Line
                  dataKey="p50"
                  stroke="#e4e4e7"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[280px] w-full" aria-hidden />
          )}
        </div>
      </div>
    </div>
  );
}
