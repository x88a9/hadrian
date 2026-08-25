"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { fmtDateTime, fmtInt, fmtNum, fmtR } from "@/lib/format";
import type { EngineTrade } from "@/lib/types";

function directionClass(dir: EngineTrade["direction"]): string {
  return dir === "long" ? "text-emerald-400/90" : "text-red-400/90";
}

function rClass(r: number): string {
  if (Number.isNaN(r)) return "text-zinc-500";
  if (r > 0) return "text-emerald-400";
  if (r < 0) return "text-red-400";
  return "text-zinc-300";
}

function wlClass(wl: string): string {
  if (wl === "win") return "text-emerald-400";
  if (wl === "loss") return "text-red-400";
  return "text-zinc-500";
}

const headCls =
  "sticky top-0 z-10 bg-zinc-950 text-zinc-400 border-b border-zinc-800";
const numCls = "text-right font-mono tabular-nums";

interface EngineTradesTableProps {
  trades: EngineTrade[];
}

// Zeigt die Trades EINES Backtest-Runs (Engine-Output) — bewusst eine eigene
// Tabelle statt Wiederverwendung von TradesTable, da EngineTrade eine andere
// Form hat (entry_ts/exit_ts, gross_r/cost_r, exit_reason, tag) als der
// System-Trade-Datensatz.
export function EngineTradesTable({ trades }: EngineTradesTableProps) {
  if (trades.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-zinc-500">
        Keine Trades in diesem Run.
      </div>
    );
  }

  return (
    <div className="max-h-[560px] overflow-auto rounded-lg border border-zinc-800">
      <Table className="text-xs">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className={cn(headCls, "w-10 text-right")}>#</TableHead>
            <TableHead className={headCls}>Entry</TableHead>
            <TableHead className={headCls}>Exit</TableHead>
            <TableHead className={headCls}>Dir</TableHead>
            <TableHead className={cn(headCls, "text-right")}>
              Entry-Preis
            </TableHead>
            <TableHead className={cn(headCls, "text-right")}>Stop</TableHead>
            <TableHead className={cn(headCls, "text-right")}>
              Exit-Preis
            </TableHead>
            <TableHead className={cn(headCls, "text-right")}>
              Gross R
            </TableHead>
            <TableHead className={cn(headCls, "text-right")}>
              Cost R
            </TableHead>
            <TableHead className={cn(headCls, "text-right")}>R</TableHead>
            <TableHead className={cn(headCls, "text-center")}>W/L</TableHead>
            <TableHead className={cn(headCls, "text-right")}>Bars</TableHead>
            <TableHead className={headCls}>Exit-Grund</TableHead>
            <TableHead className={headCls}>Tag</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {trades.map((t, i) => (
            <TableRow key={`${t.entry_index}-${t.exit_index}`} className="border-zinc-800/70">
              <TableCell className={cn(numCls, "text-zinc-500")}>
                {i + 1}
              </TableCell>
              <TableCell className="font-mono text-zinc-300">
                {fmtDateTime(t.entry_ts)}
              </TableCell>
              <TableCell className="font-mono text-zinc-300">
                {fmtDateTime(t.exit_ts)}
              </TableCell>
              <TableCell className={cn("font-medium", directionClass(t.direction))}>
                {t.direction === "long" ? "Long" : "Short"}
              </TableCell>
              <TableCell className={cn(numCls, "text-zinc-300")}>
                {fmtNum(t.entry_price, 2)}
              </TableCell>
              <TableCell className={cn(numCls, "text-zinc-400")}>
                {fmtNum(t.stop_price, 2)}
              </TableCell>
              <TableCell className={cn(numCls, "text-zinc-300")}>
                {fmtNum(t.exit_price, 2)}
              </TableCell>
              <TableCell className={cn(numCls, "text-zinc-400")}>
                {fmtR(t.gross_r)}
              </TableCell>
              <TableCell className={cn(numCls, "text-zinc-500")}>
                {fmtR(t.cost_r)}
              </TableCell>
              <TableCell className={cn(numCls, rClass(t.r_value))}>
                {fmtR(t.r_value)}
              </TableCell>
              <TableCell
                className={cn("text-center font-semibold", wlClass(t.win_loss))}
              >
                {t.win_loss === "win" ? "W" : t.win_loss === "loss" ? "L" : "—"}
              </TableCell>
              <TableCell className={cn(numCls, "text-zinc-400")}>
                {fmtInt(t.bars_held)}
              </TableCell>
              <TableCell className="text-zinc-400">{t.exit_reason}</TableCell>
              <TableCell className="text-zinc-500">{t.tag ?? "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
