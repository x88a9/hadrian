"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Loader2,
  Plus,
  RotateCw,
  ServerCrash,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { LiveMetricsCards } from "@/components/live-metrics-cards";
import { LiveTradesTable } from "@/components/live-trades-table";
import { ApiError, getLiveMetrics, getLiveTrades } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { LiveMetrics, LiveTrade } from "@/lib/types";

type Range = "30d" | "all";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; metrics: LiveMetrics; trades: LiveTrade[] }
  | { status: "error"; message: string; offline: boolean };

// heute − 30 Tage als YYYY-MM-DD (lokal, deterministisch genug fuer Filter).
function thirtyDaysAgo(): string {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function LivePage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [range, setRange] = useState<Range>("30d");

  const load = useCallback(
    async (activeRange: Range, initial = false) => {
      if (initial) setState({ status: "loading" });
      try {
        const params =
          activeRange === "30d" ? { date_from: thirtyDaysAgo() } : {};
        const [metrics, tradesRes] = await Promise.all([
          getLiveMetrics(),
          getLiveTrades(params),
        ]);
        setState({
          status: "ready",
          metrics,
          trades: tradesRes.items,
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
    },
    [],
  );

  useEffect(() => {
    void load(range, true);
  }, [load, range]);

  function selectRange(next: Range) {
    if (next === range) return;
    setRange(next);
  }

  const rangeBtn = (value: Range, label: string) => (
    <button
      type="button"
      onClick={() => selectRange(value)}
      className={cn(
        "h-8 px-3 text-sm transition-colors",
        range === value
          ? "bg-zinc-800 text-zinc-100"
          : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
      )}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <span className="text-xs font-medium uppercase tracking-[0.35em] text-zinc-500">
            Hadrian³
          </span>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-50">
            Live-Trading
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Reale Trades mit Ausführungsqualität, PnL und Kontostand.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3">
          <div className="inline-flex overflow-hidden rounded-md border border-zinc-800">
            {rangeBtn("30d", "Letzte 30 Tage")}
            {rangeBtn("all", "Alle")}
          </div>
          <Button
            render={<Link href="/live/new" />}
            className="border border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
          >
            <Plus className="size-4" />
            Neuer Trade
          </Button>
        </div>
      </header>

      {state.status === "loading" ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/30 py-24 text-sm text-zinc-500">
          <Loader2 className="size-4 animate-spin" />
          Live-Trades werden geladen…
        </div>
      ) : null}

      {state.status === "error" ? (
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
              Live-Trades konnten nicht geladen werden
            </p>
            <p className="mt-1 max-w-md text-sm text-zinc-500">
              {state.message}
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => void load(range, true)}
            className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
          >
            <RotateCw className="size-4" />
            Erneut versuchen
          </Button>
        </div>
      ) : null}

      {state.status === "ready" ? (
        <>
          <LiveMetricsCards metrics={state.metrics} />
          {state.trades.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/20 px-6 py-20 text-center">
              <p className="text-sm font-medium text-zinc-300">
                Noch keine Live-Trades — leg den ersten Trade an.
              </p>
              <p className="max-w-md text-sm text-zinc-500">
                Über „Neuer Trade" oben rechts einen neuen Trade eröffnen.
              </p>
              <Button
                render={<Link href="/live/new" />}
                className="mt-2 border border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
              >
                <Plus className="size-4" />
                Neuer Trade
              </Button>
            </div>
          ) : (
            <LiveTradesTable trades={state.trades} />
          )}
        </>
      ) : null}
    </div>
  );
}
