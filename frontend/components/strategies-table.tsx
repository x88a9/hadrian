"use client";

import { useRouter } from "next/navigation";
import { Copy, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { fmtDateTime, fmtR } from "@/lib/format";
import type { StrategySummary } from "@/lib/types";

const RULES_LABEL: Record<StrategySummary["rules"], string> = {
  declarative: "deklarativ",
  python: "python",
};

const RULES_COLOR: Record<StrategySummary["rules"], string> = {
  declarative: "bg-cyan-500/10 text-cyan-300 border-cyan-500/30",
  python: "bg-violet-500/10 text-violet-300 border-violet-500/30",
};

function rColor(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "text-zinc-500";
  }
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-red-400";
  return "text-zinc-300";
}

interface StrategiesTableProps {
  strategies: StrategySummary[];
  onDuplicate: (strategy: StrategySummary) => void;
  onDelete: (strategy: StrategySummary) => void;
}

export function StrategiesTable({
  strategies,
  onDuplicate,
  onDelete,
}: StrategiesTableProps) {
  const router = useRouter();

  if (strategies.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-zinc-500">
        Keine Strategien vorhanden.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-800">
      <Table>
        <TableHeader>
          <TableRow className="border-zinc-800 hover:bg-transparent">
            <TableHead className="text-zinc-400">Name</TableHead>
            <TableHead className="text-zinc-400">Asset</TableHead>
            <TableHead className="text-zinc-400">TF</TableHead>
            <TableHead className="text-zinc-400">Regeln</TableHead>
            <TableHead className="text-right text-zinc-400">Version</TableHead>
            <TableHead className="text-right text-zinc-400">
              Letztes Ergebnis
            </TableHead>
            <TableHead className="text-zinc-400">Aktualisiert</TableHead>
            <TableHead className="w-24 text-right text-zinc-400">
              <span className="sr-only">Aktionen</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {strategies.map((s) => (
            <TableRow
              key={s.id}
              onClick={() => router.push(`/strategies/${s.id}`)}
              className="cursor-pointer border-zinc-800 hover:bg-zinc-900/60"
            >
              <TableCell className="font-medium text-zinc-100">
                {s.name}
                {s.description ? (
                  <div className="mt-0.5 max-w-xs truncate text-xs font-normal text-zinc-500">
                    {s.description}
                  </div>
                ) : null}
              </TableCell>
              <TableCell className="font-mono text-xs text-zinc-300">
                {s.asset}
              </TableCell>
              <TableCell className="font-mono text-xs text-zinc-400 tabular-nums">
                {s.timeframe}
              </TableCell>
              <TableCell>
                <Badge
                  variant="outline"
                  className={cn("font-normal", RULES_COLOR[s.rules])}
                >
                  {RULES_LABEL[s.rules]}
                </Badge>
              </TableCell>
              <TableCell className="text-right font-mono text-zinc-300 tabular-nums">
                v{s.current_version}
              </TableCell>
              <TableCell
                className={cn(
                  "text-right font-mono tabular-nums",
                  rColor(s.last_total_r),
                )}
              >
                {s.last_backtest_at ? `${fmtR(s.last_total_r)}R` : "—"}
              </TableCell>
              <TableCell className="text-xs text-zinc-500">
                {fmtDateTime(s.updated_at)}
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-1">
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    title="Duplizieren"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDuplicate(s);
                    }}
                  >
                    <Copy className="size-3.5" />
                  </Button>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    title="Löschen"
                    className="text-red-400/80 hover:bg-red-500/10 hover:text-red-300"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(s);
                    }}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
