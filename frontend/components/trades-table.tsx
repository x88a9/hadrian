"use client";

import { Pencil, Trash2 } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { fmtDateTime, fmtNum, fmtR } from "@/lib/format";
import type { Trade } from "@/lib/types";

function directionLabel(dir: Trade["direction"]): string {
  if (dir === "long") return "Long";
  if (dir === "short") return "Short";
  return "—";
}

function directionClass(dir: Trade["direction"]): string {
  if (dir === "long") return "text-emerald-400/90";
  if (dir === "short") return "text-red-400/90";
  return "text-zinc-500";
}

function rClass(r: number | null): string {
  if (r === null || r === undefined || Number.isNaN(r)) return "text-zinc-500";
  if (r > 0) return "text-emerald-400";
  if (r < 0) return "text-red-400";
  return "text-zinc-300";
}

function wlLabel(wl: Trade["win_loss"]): string {
  if (wl === "win") return "W";
  if (wl === "loss") return "L";
  if (wl === "draw") return "D";
  return "—";
}

function wlClass(wl: Trade["win_loss"]): string {
  if (wl === "win") return "text-emerald-400";
  if (wl === "loss") return "text-red-400";
  return "text-zinc-500";
}

const headCls =
  "sticky top-0 z-10 bg-zinc-950 text-zinc-400 border-b border-zinc-800";
const numCls = "text-right font-mono tabular-nums";

interface TradesTableProps {
  trades: Trade[];
  // Optional: Zeilen-Aktionen. Nur gerendert, wenn mindestens ein Callback
  // gesetzt ist (Trade-Explorer bleibt so unverändert).
  onEdit?: (trade: Trade) => void;
  onDelete?: (trade: Trade) => void;
}

export function TradesTable({ trades, onEdit, onDelete }: TradesTableProps) {
  const withActions = Boolean(onEdit || onDelete);

  if (trades.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-zinc-500">
        Keine Trades vorhanden.
      </div>
    );
  }

  return (
    <div className="max-h-[560px] overflow-auto rounded-lg border border-zinc-800">
      <Table className="text-xs">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className={cn(headCls, "w-10 text-right")}>#</TableHead>
            <TableHead className={headCls}>Datum</TableHead>
            <TableHead className={headCls}>Zone</TableHead>
            <TableHead className={headCls}>TF</TableHead>
            <TableHead className={cn(headCls, "text-right")}>Entry</TableHead>
            <TableHead className={cn(headCls, "text-right")}>SL</TableHead>
            <TableHead className={cn(headCls, "text-right")}>Exit</TableHead>
            <TableHead className={headCls}>Dir</TableHead>
            <TableHead className={cn(headCls, "text-right")}>R</TableHead>
            <TableHead className={cn(headCls, "text-center")}>W/L</TableHead>
            {withActions ? (
              <TableHead className={cn(headCls, "w-20 text-right")}>
                <span className="sr-only">Aktionen</span>
              </TableHead>
            ) : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {trades.map((t, i) => (
            <TableRow key={t.id} className="border-zinc-800/70">
              <TableCell className={cn(numCls, "text-zinc-500")}>
                {i + 1}
              </TableCell>
              <TableCell className="font-mono text-zinc-300">
                {fmtDateTime(t.trade_datetime)}
              </TableCell>
              <TableCell className="text-zinc-300">{t.zone ?? "—"}</TableCell>
              <TableCell className="text-zinc-400">
                {t.timeframe ?? "—"}
              </TableCell>
              <TableCell className={cn(numCls, "text-zinc-300")}>
                {fmtNum(t.entry, 2)}
              </TableCell>
              <TableCell className={cn(numCls, "text-zinc-400")}>
                {fmtNum(t.sl, 2)}
              </TableCell>
              <TableCell className={cn(numCls, "text-zinc-300")}>
                {fmtNum(t.exit, 2)}
              </TableCell>
              <TableCell
                className={cn("font-medium", directionClass(t.direction))}
              >
                {directionLabel(t.direction)}
              </TableCell>
              <TableCell className={cn(numCls, rClass(t.r_value))}>
                {fmtR(t.r_value)}
              </TableCell>
              <TableCell
                className={cn(
                  "text-center font-semibold",
                  wlClass(t.win_loss),
                )}
              >
                {wlLabel(t.win_loss)}
              </TableCell>
              {withActions ? (
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    {onEdit ? (
                      <button
                        type="button"
                        onClick={() => onEdit(t)}
                        aria-label="Trade bearbeiten"
                        title="Bearbeiten"
                        className="flex size-6 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
                      >
                        <Pencil className="size-3.5" />
                      </button>
                    ) : null}
                    {onDelete ? (
                      <button
                        type="button"
                        onClick={() => onDelete(t)}
                        aria-label="Trade löschen"
                        title="Löschen"
                        className="flex size-6 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-red-500/15 hover:text-red-400"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    ) : null}
                  </div>
                </TableCell>
              ) : null}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
