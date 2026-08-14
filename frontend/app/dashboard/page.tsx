"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Info,
  Loader2,
  RotateCw,
  ServerCrash,
} from "lucide-react";

import { EquityCurve } from "@/components/equity-curve";
import { GradeBadge } from "@/components/grade-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, getSystems, getTrades } from "@/lib/api";
import { cn } from "@/lib/utils";
import { fmtDate, fmtInt, fmtNum, fmtR } from "@/lib/format";
import type {
  SystemStatus,
  SystemSummary,
  Trade,
} from "@/lib/types";

const STATUSES: SystemStatus[] = [
  "backtest",
  "live_testing",
  "active",
  "retired",
];

const STATUS_LABEL: Record<SystemStatus, string> = {
  backtest: "Backtest",
  live_testing: "Live-Test",
  active: "Aktiv",
  retired: "Retired",
};

const STATUS_COLOR: Record<SystemStatus, string> = {
  backtest: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
  live_testing: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  active: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  retired: "bg-zinc-700/20 text-zinc-500 border-zinc-600/30",
};

type LoadState =
  | { status: "loading" }
  | {
      status: "ready";
      systems: SystemSummary[];
      trades: Trade[];
      splitDate: string;
    }
  | { status: "error"; message: string; offline: boolean };

function numericR(t: Trade): number | null {
  return typeof t.r_value === "number" && !Number.isNaN(t.r_value)
    ? t.r_value
    : null;
}

// Max Drawdown (positiv) auf der chronologisch gemergten Kurve.
// Peak startet bei 0, gleiche Chronologie wie die Equity-Kurve.
function maxDrawdown(trades: Trade[]): number | null {
  const withDate = trades.filter((t) => t.trade_datetime);
  const withoutDate = trades.filter((t) => !t.trade_datetime);
  withDate.sort((a, b) =>
    (a.trade_datetime ?? "").localeCompare(b.trade_datetime ?? ""),
  );
  const ordered = [...withDate, ...withoutDate];
  if (ordered.length === 0) return null;
  let cum = 0;
  let peak = 0;
  let maxDd = 0;
  for (const t of ordered) {
    cum += numericR(t) ?? 0;
    if (cum > peak) peak = cum;
    const dd = peak - cum;
    if (dd > maxDd) maxDd = dd;
  }
  return maxDd;
}

function AggCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-zinc-800 bg-zinc-900/30 p-4">
      <span className="text-[11px] uppercase tracking-wider text-zinc-600">
        {label}
      </span>
      <span
        className={cn(
          "font-mono text-xl tabular-nums text-zinc-100",
          accent,
        )}
      >
        {value}
      </span>
    </div>
  );
}

function rAccent(value: number | null): string | undefined {
  if (value === null || value === undefined) return undefined;
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-red-400";
  return undefined;
}

export default function DashboardPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selected, setSelected] = useState<Set<SystemStatus>>(
    () => new Set<SystemStatus>(["active"]),
  );
  const [fallback, setFallback] = useState(false);

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const [systemsRes, tradesRes] = await Promise.all([
        getSystems(),
        getTrades({ limit: 10000 }),
      ]);
      const systems = systemsRes.items;
      // Auto-Fallback: keine active-Systeme -> alle Status zeigen.
      const hasActive = systems.some((s) => s.status === "active");
      if (!hasActive) {
        setSelected(new Set(STATUSES));
        setFallback(true);
      } else {
        setFallback(false);
      }
      setState({
        status: "ready",
        systems,
        trades: tradesRes.items,
        splitDate: systemsRes.split_date,
      });
    } catch (err) {
      const offline = err instanceof ApiError && err.status === 0;
      const message =
        err instanceof ApiError
          ? offline
            ? "Backend nicht erreichbar. Läuft der API-Server?"
            : err.message
          : err instanceof Error
            ? err.message
            : "Unbekannter Fehler beim Laden.";
      setState({ status: "error", message, offline });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function toggleStatus(s: SystemStatus) {
    // Manuelle Interaktion beendet den Fallback-Hinweis.
    setFallback(false);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  }

  const view = useMemo(() => {
    if (state.status !== "ready") return null;
    const chosenSystems = state.systems.filter((s) => selected.has(s.status));
    const chosenIds = new Set(chosenSystems.map((s) => s.id));
    const chosenTrades = state.trades.filter((t) => chosenIds.has(t.system_id));

    const rValues = chosenTrades
      .map(numericR)
      .filter((r): r is number => r !== null);
    const totalR = rValues.reduce((a, b) => a + b, 0);
    const ev = rValues.length > 0 ? totalR / rValues.length : null;
    const posSum = rValues.filter((r) => r > 0).reduce((a, b) => a + b, 0);
    const negSum = rValues.filter((r) => r < 0).reduce((a, b) => a + b, 0);
    const profitFactor = negSum === 0 ? null : posSum / Math.abs(negSum);

    const datedTrades = chosenTrades.filter((t) => t.trade_datetime);
    const undatedCount = chosenTrades.length - datedTrades.length;
    const maxDd = maxDrawdown(datedTrades);

    // Beitrag je System (aus den geladenen Trades abgeleitet).
    const perSystem = chosenSystems
      .map((s) => {
        const tr = chosenTrades.filter((t) => t.system_id === s.id);
        const rv = tr.map(numericR).filter((r): r is number => r !== null);
        return {
          system: s,
          trades: tr.length,
          totalR: rv.reduce((a, b) => a + b, 0),
        };
      })
      .sort((a, b) => b.totalR - a.totalR);

    return {
      chosenSystems,
      chosenTrades,
      datedTrades,
      undatedCount,
      totalR,
      ev,
      profitFactor,
      maxDd,
      perSystem,
    };
  }, [state, selected]);

  return (
    <div className="flex flex-col gap-8 py-4">
      <header>
        <span className="text-xs font-medium uppercase tracking-[0.35em] text-zinc-500">
          Hadrian³
        </span>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-50">
          Portfolio Dashboard
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Aggregierte Kennzahlen und kombinierte Equity-Kurve über die
          gewählten Systeme.
        </p>
      </header>

      {state.status === "loading" && (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/30 py-24 text-sm text-zinc-500">
          <Loader2 className="size-4 animate-spin" />
          Portfolio wird geladen…
        </div>
      )}

      {state.status === "error" && (
        <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900/30 px-6 py-20 text-center">
          <span className="flex size-12 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950 text-zinc-400">
            {state.offline ? (
              <ServerCrash className="size-6" />
            ) : (
              <AlertTriangle className="size-6" />
            )}
          </span>
          <div>
            <p className="text-sm font-medium text-zinc-200">
              Portfolio konnte nicht geladen werden
            </p>
            <p className="mt-1 max-w-md text-sm text-zinc-500">
              {state.message}
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => void load()}
            className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
          >
            <RotateCw className="size-4" />
            Erneut versuchen
          </Button>
        </div>
      )}

      {state.status === "ready" && view && (
        <>
          {/* Status-Multi-Toggle */}
          <div className="flex flex-wrap items-center gap-2">
            {STATUSES.map((s) => {
              const on = selected.has(s);
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleStatus(s)}
                  className={cn(
                    "h-8 rounded-md border px-3 text-sm transition-colors",
                    on
                      ? STATUS_COLOR[s]
                      : "border-zinc-800 bg-zinc-900/40 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300",
                  )}
                >
                  {STATUS_LABEL[s]}
                </button>
              );
            })}
            <span className="ml-auto text-xs text-zinc-500 tabular-nums">
              {view.chosenSystems.length} Systeme gewählt
            </span>
          </div>

          {fallback && (
            <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
              <Info className="size-4 shrink-0" />
              Keine active-Systeme — zeige alle.
            </div>
          )}

          {view.chosenSystems.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/20 px-6 py-20 text-center">
              <p className="text-sm font-medium text-zinc-300">
                Keine Systeme im gewählten Status.
              </p>
              <p className="max-w-md text-sm text-zinc-500">
                Status oben zuschalten, um Systeme einzubeziehen.
              </p>
            </div>
          ) : (
            <>
              {/* Aggregat-Karten */}
              <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
                <AggCard
                  label="Systeme"
                  value={fmtInt(view.chosenSystems.length)}
                />
                <AggCard
                  label="Trades"
                  value={fmtInt(view.chosenTrades.length)}
                />
                <AggCard
                  label="Total R"
                  value={fmtR(view.totalR)}
                  accent={rAccent(view.totalR)}
                />
                <AggCard
                  label="Portfolio-EV"
                  value={fmtR(view.ev)}
                  accent={rAccent(view.ev)}
                />
                <AggCard
                  label="Profit Factor"
                  value={fmtNum(view.profitFactor, 2)}
                />
                <AggCard
                  label="Max DD (R)"
                  value={fmtNum(view.maxDd, 2)}
                  accent="text-red-400"
                />
              </section>

              {/* Kombinierte Equity-Kurve */}
              <section>
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
                  Kombinierte Equity-Kurve (kumuliertes R)
                </h2>
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
                  <EquityCurve
                    trades={view.datedTrades}
                    splitDate={state.splitDate}
                  />
                </div>
                {view.undatedCount > 0 && (
                  <p className="mt-2 text-xs text-zinc-500">
                    {view.undatedCount} Trades ohne Datum nicht enthalten.
                  </p>
                )}
              </section>

              {/* Beitragstabelle */}
              <section>
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
                  Beitrag je System
                </h2>
                <div className="overflow-hidden rounded-lg border border-zinc-800">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-zinc-800 hover:bg-transparent">
                        <TableHead className="text-zinc-400">Name</TableHead>
                        <TableHead className="text-zinc-400">Status</TableHead>
                        <TableHead className="text-right text-zinc-400">
                          Trades
                        </TableHead>
                        <TableHead className="text-right text-zinc-400">
                          Total R
                        </TableHead>
                        <TableHead className="text-right text-zinc-400">
                          OOS EV
                        </TableHead>
                        <TableHead className="text-right text-zinc-400">
                          Composite
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {view.perSystem.map(({ system, trades, totalR }) => (
                        <TableRow
                          key={system.id}
                          className="border-zinc-800 hover:bg-zinc-900/60"
                        >
                          <TableCell className="font-medium">
                            <Link
                              href={`/systems/${system.id}`}
                              className="text-zinc-100 transition-colors hover:text-emerald-300"
                            >
                              {system.name}
                            </Link>
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant="outline"
                              className={cn(
                                "font-normal",
                                STATUS_COLOR[system.status],
                              )}
                            >
                              {STATUS_LABEL[system.status]}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right font-mono text-zinc-300 tabular-nums">
                            {fmtInt(trades)}
                          </TableCell>
                          <TableCell
                            className={cn(
                              "text-right font-mono tabular-nums",
                              rAccent(totalR) ?? "text-zinc-300",
                            )}
                          >
                            {fmtR(totalR)}
                          </TableCell>
                          <TableCell
                            className={cn(
                              "text-right font-mono tabular-nums",
                              rAccent(system.metrics.oos.ev) ?? "text-zinc-300",
                            )}
                          >
                            {fmtR(system.metrics.oos.ev)}
                          </TableCell>
                          <TableCell className="text-right">
                            <GradeBadge
                              grade={system.metrics.all.composite_grade}
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
