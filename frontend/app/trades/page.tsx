"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Loader2,
  SearchX,
} from "lucide-react";

import {
  EMPTY_FILTERS,
  TradeFilters,
  type TradeFilterState,
} from "@/components/trade-filters";
import { LiveTradesTable } from "@/components/live-trades-table";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, getLiveTrades, getSystems, getTrades } from "@/lib/api";
import { fmtDateTime, fmtNum, fmtR } from "@/lib/format";
import { cn } from "@/lib/utils";
import type {
  LiveTrade,
  SystemSummary,
  Trade,
  TradeListResponse,
} from "@/lib/types";

type TradeView = "live" | "backtest";
const ALL_SYSTEMS = "__all__";

const PAGE_LIMIT = 100;

// Preis-Werte kompakt anzeigen (bis 4 signifikante Nachkommastellen abhaengig
// von der Groesse; deterministisch ueber fmtNum).
function fmtPrice(value: number | null): string {
  if (value === null) return "—";
  const abs = Math.abs(value);
  const decimals = abs >= 1000 ? 1 : abs >= 1 ? 2 : 5;
  return fmtNum(value, decimals);
}

export default function TradesPage() {
  // Default: Live (Brief — Trade-Explorer-Standardfilter auf Live).
  const [view, setView] = useState<TradeView>("live");

  const [systems, setSystems] = useState<SystemSummary[]>([]);
  const [filters, setFilters] = useState<TradeFilterState>(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);

  const [data, setData] = useState<TradeListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Live-Ansicht (unabhängig von den Backtest-Codepfaden).
  const [liveSystem, setLiveSystem] = useState<string>(ALL_SYSTEMS);
  const [liveTrades, setLiveTrades] = useState<LiveTrade[]>([]);
  const [liveLoading, setLiveLoading] = useState(true);
  const [liveError, setLiveError] = useState<string | null>(null);

  // Systemliste einmalig fuer das Dropdown laden. Fehler hier sind nicht fatal
  // (Dropdown bleibt leer, Trades lassen sich trotzdem laden).
  useEffect(() => {
    let active = true;
    getSystems()
      .then((res) => {
        if (active) setSystems(res.items);
      })
      .catch(() => {
        if (active) setSystems([]);
      });
    return () => {
      active = false;
    };
  }, []);

  // base-ui rendert in <Select.Value> den rohen value (hier: die System-ID),
  // solange dem Root kein `items`-Mapping gegeben wird.
  const liveSystemItems = useMemo(() => {
    const map: Record<string, string> = { [ALL_SYSTEMS]: "Alle Systeme" };
    for (const s of systems) map[String(s.id)] = s.name;
    return map;
  }, [systems]);

  const loadTrades = useCallback(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getTrades({ ...filters, limit: PAGE_LIMIT, offset })
      .then((res) => {
        if (active) setData(res);
      })
      .catch((err) => {
        if (!active) return;
        setData(null);
        if (err instanceof ApiError && err.status === 0) {
          setError(
            "Backend nicht erreichbar. Läuft der API-Server auf " +
              "Port 8000?",
          );
        } else if (err instanceof ApiError) {
          setError(`Fehler beim Laden der Trades: ${err.message}`);
        } else {
          setError("Unerwarteter Fehler beim Laden der Trades.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [filters, offset]);

  // Backtest-Trades nur laden, wenn die Backtest-Ansicht aktiv ist.
  useEffect(() => {
    if (view !== "backtest") return;
    return loadTrades();
  }, [loadTrades, view]);

  // Live-Trades laden, wenn die Live-Ansicht aktiv ist (optionaler Systemfilter).
  useEffect(() => {
    if (view !== "live") return;
    let active = true;
    setLiveLoading(true);
    setLiveError(null);
    const params =
      liveSystem === ALL_SYSTEMS ? {} : { system_id: Number(liveSystem) };
    getLiveTrades(params)
      .then((res) => {
        if (active) setLiveTrades(res.items);
      })
      .catch((err) => {
        if (!active) return;
        setLiveTrades([]);
        if (err instanceof ApiError && err.status === 0) {
          setLiveError(
            "Backend nicht erreichbar. Läuft der API-Server auf Port 8000?",
          );
        } else if (err instanceof ApiError) {
          setLiveError(`Fehler beim Laden der Live-Trades: ${err.message}`);
        } else {
          setLiveError("Unerwarteter Fehler beim Laden der Live-Trades.");
        }
      })
      .finally(() => {
        if (active) setLiveLoading(false);
      });
    return () => {
      active = false;
    };
  }, [view, liveSystem]);

  // Jede Filteraenderung setzt die Pagination zurueck auf Seite 1.
  function handleFilterChange(next: TradeFilterState) {
    setFilters(next);
    setOffset(0);
  }

  const total = data?.total ?? 0;
  const items = data?.items ?? [];
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + PAGE_LIMIT, total);
  const canPrev = offset > 0;
  const canNext = offset + PAGE_LIMIT < total;

  return (
    <div className="flex flex-col gap-6 py-2">
      <header>
        <span className="text-xs font-medium uppercase tracking-[0.35em] text-zinc-500">
          Hadrian³
        </span>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-zinc-50">
          Trade Explorer
        </h1>
        <p className="mt-2 text-sm text-zinc-500">
          Einzelne Trades serverseitig filtern und in R-Einheiten analysieren.
        </p>
      </header>

      <div className="inline-flex w-fit overflow-hidden rounded-md border border-zinc-800">
        {(["live", "backtest"] as const).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            className={cn(
              "h-8 px-4 text-sm transition-colors",
              view === v
                ? "bg-zinc-800 text-zinc-100"
                : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
            )}
          >
            {v === "live" ? "Live (real)" : "Backtest"}
          </button>
        ))}
      </div>

      {view === "live" ? (
        <div className="flex flex-col gap-4">
          <div className="flex w-full max-w-xs flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wider text-zinc-400">
              System
            </span>
            <Select
              items={liveSystemItems}
              value={liveSystem}
              onValueChange={(v) => setLiveSystem(v ?? ALL_SYSTEMS)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_SYSTEMS}>Alle Systeme</SelectItem>
                {systems.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {liveError ? (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/5 px-6 py-16 text-center">
              <AlertTriangle className="size-8 text-red-400" />
              <p className="text-sm text-red-300">{liveError}</p>
            </div>
          ) : liveLoading ? (
            <div className="flex items-center justify-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/30 py-24 text-sm text-zinc-500">
              <Loader2 className="size-4 animate-spin" />
              Lade Live-Trades…
            </div>
          ) : liveTrades.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-zinc-800 bg-zinc-900/20 px-6 py-20 text-center">
              <p className="text-sm font-medium text-zinc-300">
                Noch keine Live-Trades vorhanden.
              </p>
              <p className="max-w-md text-sm text-zinc-500">
                Reale Trades erscheinen hier, sobald sie angelegt sind.
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setView("backtest")}
                className="mt-2 border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
              >
                Zu Backtest-Trades wechseln
              </Button>
            </div>
          ) : (
            <LiveTradesTable trades={liveTrades} />
          )}
        </div>
      ) : (
        <>
      <TradeFilters
        systems={systems}
        value={filters}
        onChange={handleFilterChange}
        disabled={loading && data === null}
      />

      {error ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/5 px-6 py-16 text-center">
          <AlertTriangle className="size-8 text-red-400" />
          <p className="text-sm text-red-300">{error}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={loadTrades}
            className="border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
          >
            Erneut versuchen
          </Button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/40">
          <div className="max-h-[calc(100vh-22rem)] overflow-auto">
            <Table className="text-zinc-300">
              <TableHeader className="sticky top-0 z-10 bg-zinc-950/95 backdrop-blur [&_tr]:border-zinc-800">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-zinc-400">System</TableHead>
                  <TableHead className="text-zinc-400">Datum</TableHead>
                  <TableHead className="text-zinc-400">Zone</TableHead>
                  <TableHead className="text-zinc-400">TF</TableHead>
                  <TableHead className="text-right text-zinc-400">
                    Entry
                  </TableHead>
                  <TableHead className="text-right text-zinc-400">SL</TableHead>
                  <TableHead className="text-right text-zinc-400">
                    Exit
                  </TableHead>
                  <TableHead className="text-zinc-400">Dir</TableHead>
                  <TableHead className="text-right text-zinc-400">R</TableHead>
                  <TableHead className="text-zinc-400">W/L</TableHead>
                  <TableHead className="text-zinc-400">Source</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow className="hover:bg-transparent">
                    <TableCell
                      colSpan={11}
                      className="h-40 text-center text-zinc-500"
                    >
                      <span className="inline-flex items-center gap-2">
                        <Loader2 className="size-4 animate-spin" />
                        Lade Trades…
                      </span>
                    </TableCell>
                  </TableRow>
                ) : items.length === 0 ? (
                  <TableRow className="hover:bg-transparent">
                    <TableCell
                      colSpan={11}
                      className="h-40 text-center text-zinc-500"
                    >
                      <span className="inline-flex flex-col items-center gap-2">
                        <SearchX className="size-6 text-zinc-600" />
                        Keine Trades gefunden
                      </span>
                    </TableCell>
                  </TableRow>
                ) : (
                  items.map((t) => <TradeRow key={t.id} trade={t} />)
                )}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between border-t border-zinc-800 px-4 py-3 text-sm text-zinc-400">
            <span className="tabular-nums">
              {total === 0
                ? "Keine Treffer"
                : `Zeige ${rangeStart}–${rangeEnd} von ${total}`}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!canPrev || loading}
                onClick={() =>
                  setOffset((o) => Math.max(0, o - PAGE_LIMIT))
                }
                className="border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
              >
                <ChevronLeft />
                Zurück
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!canNext || loading}
                onClick={() => setOffset((o) => o + PAGE_LIMIT)}
                className="border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
              >
                Weiter
                <ChevronRight />
              </Button>
            </div>
          </div>
        </div>
      )}
        </>
      )}
    </div>
  );
}

function TradeRow({ trade }: { trade: Trade }) {
  const r = trade.r_value;
  const rClass =
    r === null
      ? "text-zinc-500"
      : r > 0
        ? "text-emerald-400"
        : r < 0
          ? "text-red-400"
          : "text-zinc-400";

  return (
    <TableRow className="border-zinc-800/70 hover:bg-zinc-800/40">
      <TableCell>
        <Link
          href={`/systems/${trade.system_id}`}
          className="font-medium text-zinc-100 underline-offset-2 hover:text-white hover:underline"
        >
          {trade.system_name}
        </Link>
      </TableCell>
      <TableCell className="font-mono text-xs tabular-nums text-zinc-400">
        {fmtDateTime(trade.trade_datetime)}
      </TableCell>
      <TableCell className="text-zinc-400">{trade.zone ?? "—"}</TableCell>
      <TableCell className="text-zinc-400">{trade.timeframe ?? "—"}</TableCell>
      <TableCell className="text-right font-mono tabular-nums text-zinc-300">
        {fmtPrice(trade.entry)}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums text-zinc-300">
        {fmtPrice(trade.sl)}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums text-zinc-300">
        {fmtPrice(trade.exit)}
      </TableCell>
      <TableCell>
        {trade.direction ? (
          <span
            className={cn(
              "text-xs font-medium uppercase tracking-wide",
              trade.direction === "long"
                ? "text-emerald-400/80"
                : "text-red-400/80",
            )}
          >
            {trade.direction}
          </span>
        ) : (
          <span className="text-zinc-500">—</span>
        )}
      </TableCell>
      <TableCell
        className={cn("text-right font-mono tabular-nums font-medium", rClass)}
      >
        {fmtR(r)}
      </TableCell>
      <TableCell className="text-zinc-400">{trade.win_loss ?? "—"}</TableCell>
      <TableCell className="text-xs text-zinc-600">{trade.source}</TableCell>
    </TableRow>
  );
}
