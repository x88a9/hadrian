"use client";

import { useState } from "react";
import Link from "next/link";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LiveStageBadge } from "@/components/live-stage-badge";
import { cn } from "@/lib/utils";
import { fmtDateTime, fmtR } from "@/lib/format";
import {
  OPEN_STAGES,
  durationSince,
  fmtDuration,
  fmtPctValue,
  fmtUsd,
  winLossColor,
} from "@/lib/live-format";
import type { Direction, LiveTrade } from "@/lib/types";

function directionLabel(dir: Direction | null): string {
  if (dir === "long") return "Long";
  if (dir === "short") return "Short";
  return "—";
}

function directionClass(dir: Direction | null): string {
  if (dir === "long") return "text-emerald-400/90";
  if (dir === "short") return "text-red-400/90";
  return "text-zinc-500";
}

// Laufzeit: bei offenen Stufen live seit Entry/Öffnung, sonst finale Dauer.
function runtimeSeconds(t: LiveTrade, nowMs: number): number | null {
  if (OPEN_STAGES.includes(t.stage)) {
    return durationSince(t.entry_filled_at ?? t.opened_at, nowMs);
  }
  return t.duration_seconds;
}

const numCls = "text-right font-mono tabular-nums";

interface LiveTradesTableProps {
  trades: LiveTrade[];
}

export function LiveTradesTable({ trades }: LiveTradesTableProps) {
  // Einmalig im Client bestimmt -> kein Hydration-Mismatch, stabile Laufzeiten.
  const [nowMs] = useState(() => Date.now());

  if (trades.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/30 text-sm text-zinc-500">
        Keine Live-Trades vorhanden.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-800">
      <Table>
        <TableHeader>
          <TableRow className="border-zinc-800 hover:bg-transparent">
            <TableHead className="text-zinc-400">System</TableHead>
            <TableHead className="text-zinc-400">Asset</TableHead>
            <TableHead className="text-zinc-400">Stage</TableHead>
            <TableHead className="text-zinc-400">Richtung</TableHead>
            <TableHead className="text-right text-zinc-400">R</TableHead>
            <TableHead className="text-right text-zinc-400">PnL</TableHead>
            <TableHead className="text-right text-zinc-400">Deviation</TableHead>
            <TableHead className="text-right text-zinc-400">Laufzeit</TableHead>
            <TableHead className="text-right text-zinc-400">Angelegt</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {trades.map((t) => {
            const cancelled = t.stage === "cancelled";
            return (
              <TableRow
                key={t.id}
                className={cn(
                  "relative border-zinc-800 hover:bg-zinc-900/60",
                  cancelled && "opacity-50",
                )}
              >
                <TableCell className="relative font-medium text-zinc-100">
                  <Link
                    href={`/live/${t.id}`}
                    aria-label={`Live-Trade ${t.system_name ?? t.id} öffnen`}
                    className="absolute inset-0 z-10"
                  />
                  {t.system_name ??
                    (t.system_id === null ? (
                      <span className="text-zinc-500">Freier Trade</span>
                    ) : (
                      "—"
                    ))}
                </TableCell>
                <TableCell className="text-zinc-300">
                  {t.asset ?? "—"}
                </TableCell>
                <TableCell>
                  <LiveStageBadge stage={t.stage} />
                </TableCell>
                <TableCell
                  className={cn("font-medium", directionClass(t.direction))}
                >
                  {directionLabel(t.direction)}
                </TableCell>
                <TableCell className={cn(numCls, winLossColor(t.win_loss))}>
                  {fmtR(t.r_value)}
                </TableCell>
                <TableCell className={cn(numCls, winLossColor(t.win_loss))}>
                  {fmtUsd(t.realized_pnl_usd, { sign: true })}
                </TableCell>
                <TableCell className={cn(numCls, "text-zinc-300")}>
                  {fmtPctValue(t.deviation_pct)}
                </TableCell>
                <TableCell className={cn(numCls, "text-zinc-400")}>
                  {fmtDuration(runtimeSeconds(t, nowMs))}
                </TableCell>
                <TableCell className={cn(numCls, "text-zinc-500")}>
                  {fmtDateTime(t.created_at)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
