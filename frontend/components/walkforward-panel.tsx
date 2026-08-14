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

import { ApiError, getWalkForward } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { WalkForwardResponse, WalkForwardWindow } from "@/lib/types";

const inputClass = cn(
  "h-8 w-20 rounded-lg border border-zinc-800 bg-zinc-900/60 px-2.5 text-sm text-zinc-100",
  "outline-none transition-colors hover:border-zinc-700",
  "focus-visible:border-zinc-600 focus-visible:ring-2 focus-visible:ring-zinc-700",
);

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

interface WindowBar extends WalkForwardWindow {
  oosLabel: string;
  oosValue: number;
}

function WfTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: WindowBar }>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const w = payload[0].payload;
  return (
    <div className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs shadow-lg">
      <div className="text-zinc-400">
        Fenster #{w.index} · OOS ab {fmtDate(w.oos_start)}
      </div>
      <div className="mt-0.5 font-mono text-zinc-100">
        OOS-EV {w.oos_ev === null ? "—" : w.oos_ev.toFixed(3)} (n {w.n_oos})
      </div>
      <div className="font-mono text-zinc-400">
        IS-EV {w.is_ev === null ? "—" : w.is_ev.toFixed(3)} (n {w.n_is})
      </div>
    </div>
  );
}

export function WalkForwardPanel({ systemId }: { systemId: number }) {
  const [isMonths, setIsMonths] = useState(6);
  const [oosMonths, setOosMonths] = useState(3);
  const [data, setData] = useState<WalkForwardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getWalkForward(systemId, { is_months: isMonths, oos_months: oosMonths })
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
  }, [systemId, isMonths, oosMonths]);

  const bars = useMemo<WindowBar[]>(() => {
    if (!data) return [];
    return data.windows
      .filter((w) => w.oos_ev !== null)
      .map((w) => ({
        ...w,
        oosLabel: fmtDate(w.oos_start),
        oosValue: w.oos_ev ?? 0,
      }));
  }, [data]);

  return (
    <div className="flex flex-col gap-4">
      {/* Parameter */}
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[0.7rem] font-medium uppercase tracking-wide text-zinc-500">
            IS Monate
          </span>
          <input
            type="number"
            min={1}
            value={isMonths}
            onChange={(e) =>
              setIsMonths(Math.max(1, Math.floor(Number(e.target.value) || 1)))
            }
            className={inputClass}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[0.7rem] font-medium uppercase tracking-wide text-zinc-500">
            OOS Monate
          </span>
          <input
            type="number"
            min={1}
            value={oosMonths}
            onChange={(e) =>
              setOosMonths(Math.max(1, Math.floor(Number(e.target.value) || 1)))
            }
            className={inputClass}
          />
        </label>
      </div>

      {error && (
        <div className="rounded-md border border-red-900/50 bg-red-950/20 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {!error && data && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatTile
              label="pct positive"
              value={
                data.pct_positive === null
                  ? "—"
                  : `${data.pct_positive.toFixed(1)}%`
              }
              accent={
                data.pct_positive !== null && data.pct_positive >= 50
                  ? "text-emerald-300"
                  : "text-amber-300"
              }
            />
            <StatTile
              label="Fenster"
              value={`${data.n_windows_evaluated}/${data.n_windows}`}
              sub="evaluiert / gesamt"
            />
            <StatTile
              label="OOS-EV Ø"
              value={data.oos_ev_mean === null ? "—" : data.oos_ev_mean.toFixed(3)}
              accent={
                data.oos_ev_mean !== null && data.oos_ev_mean >= 0
                  ? "text-emerald-300"
                  : "text-red-300"
              }
              sub={
                data.oos_ev_std === null ? undefined : `± ${data.oos_ev_std.toFixed(3)}`
              }
            />
            <StatTile
              label="dat. Trades"
              value={String(data.n_dated_trades)}
            />
          </div>

          {bars.length === 0 ? (
            <div className="flex h-40 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-900/30 text-sm text-zinc-500">
              Zu wenige datierte Trades für Walk-Forward-Fenster.
            </div>
          ) : (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
              {mounted ? (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart
                    data={bars}
                    margin={{ top: 8, right: 12, bottom: 8, left: 0 }}
                  >
                    <XAxis
                      dataKey="oosLabel"
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
                      width={44}
                    />
                    <Tooltip
                      content={<WfTooltip />}
                      cursor={{ fill: "rgba(255,255,255,0.04)" }}
                    />
                    <ReferenceLine y={0} stroke="#71717a" strokeDasharray="3 3" />
                    <Bar
                      dataKey="oosValue"
                      radius={[2, 2, 0, 0]}
                      isAnimationActive={false}
                    >
                      {bars.map((w, i) => (
                        <Cell
                          key={i}
                          fill={
                            w.oosValue >= 0
                              ? "rgba(16,185,129,0.75)"
                              : "rgba(239,68,68,0.75)"
                          }
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[280px] w-full" aria-hidden />
              )}
            </div>
          )}
        </>
      )}

      {loading && !data && (
        <div className="flex h-40 items-center justify-center text-sm text-zinc-500">
          Lade Walk-Forward …
        </div>
      )}
    </div>
  );
}
