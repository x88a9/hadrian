"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { GradeBadge } from "@/components/grade-badge";
import { cn } from "@/lib/utils";
import { fmtInt, fmtR } from "@/lib/format";
import type { Grade, SystemSummary } from "@/lib/types";

// Rang je Grade fuer die Sortierung (A+ > A > B > C > D > F).
const GRADE_RANK: Record<Grade, number> = {
  "A+": 6,
  A: 5,
  B: 4,
  C: 3,
  D: 2,
  F: 1,
};

type SortKey = "name" | "trades" | "oos_ev" | "oos_ece" | "composite";
type SortDir = "asc" | "desc";

const ALL = "__all__";

// Zahl-Farbe: positiv gruen, negativ rot, 0/null neutral.
function rColor(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "text-zinc-500";
  }
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-red-400";
  return "text-zinc-300";
}

// Vergleichbaren Wert je Sortierschluessel ziehen (null -> immer ans Ende).
function sortValue(s: SystemSummary, key: SortKey): number | string | null {
  switch (key) {
    case "name":
      return s.name;
    case "trades":
      return s.metrics.all.total_trades;
    case "oos_ev":
      return s.metrics.oos.ev;
    case "oos_ece":
      return s.metrics.oos.ece;
    case "composite":
      return s.metrics.all.composite_grade
        ? GRADE_RANK[s.metrics.all.composite_grade]
        : null;
  }
}

const STATUS_LABEL: Record<string, string> = {
  backtest: "Backtest",
  live_testing: "Live-Test",
  active: "Aktiv",
  retired: "Retired",
};

const STATUS_COLOR: Record<string, string> = {
  backtest: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
  live_testing: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  active: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  retired: "bg-zinc-700/20 text-zinc-500 border-zinc-600/30",
};

// Anzeige-Label je Quell-Engine (bewusste kosmetische Normalisierung, D1).
const ENGINE_LABEL: Record<string, string> = {
  hadrian2: "Hadrian²",
  hadrian_engine: "Hadrian Engine",
};

function engineLabel(source: string | null): string | null {
  if (!source) return null;
  return ENGINE_LABEL[source] ?? source;
}

interface SortHeadProps {
  label: string;
  colKey: SortKey;
  active: boolean;
  dir: SortDir;
  onSort: (key: SortKey) => void;
  className?: string;
}

function SortHead({
  label,
  colKey,
  active,
  dir,
  onSort,
  className,
}: SortHeadProps) {
  return (
    <TableHead className={cn("text-zinc-400", className)}>
      <button
        type="button"
        onClick={() => onSort(colKey)}
        className={cn(
          "inline-flex items-center gap-1 select-none transition-colors hover:text-zinc-100",
          active && "text-zinc-100",
        )}
      >
        {label}
        {active ? (
          dir === "asc" ? (
            <ArrowUp className="size-3.5" />
          ) : (
            <ArrowDown className="size-3.5" />
          )
        ) : (
          <ChevronsUpDown className="size-3.5 text-zinc-600" />
        )}
      </button>
    </TableHead>
  );
}

interface SystemsTableProps {
  systems: SystemSummary[];
}

export function SystemsTable({ systems }: SystemsTableProps) {
  const router = useRouter();

  const [query, setQuery] = useState("");
  const [prefix, setPrefix] = useState<string>(ALL);
  const [status, setStatus] = useState<string>(ALL);
  const [grade, setGrade] = useState<string>(ALL);
  const [provenance, setProvenance] = useState<string>(ALL);
  const [sortKey, setSortKey] = useState<SortKey>("composite");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // Filter-Optionen aus den Daten ableiten.
  const prefixes = useMemo(
    () =>
      Array.from(new Set(systems.map((s) => s.prefix)))
        .filter(Boolean)
        .sort(),
    [systems],
  );
  const statuses = useMemo(
    () =>
      Array.from(new Set(systems.map((s) => s.status)))
        .filter(Boolean)
        .sort(),
    [systems],
  );
  const grades = useMemo(() => {
    const present = new Set(
      systems
        .map((s) => s.metrics.all.composite_grade)
        .filter((g): g is Grade => g !== null),
    );
    return (["A+", "A", "B", "C", "D", "F"] as Grade[]).filter((g) =>
      present.has(g),
    );
  }, [systems]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      // Name defaultmaessig aufsteigend, Zahlen/Grade absteigend.
      setSortDir(key === "name" ? "asc" : "desc");
    }
  }

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = systems.filter((s) => {
      if (q && !s.name.toLowerCase().includes(q)) return false;
      if (prefix !== ALL && s.prefix !== prefix) return false;
      if (status !== ALL && s.status !== status) return false;
      if (grade !== ALL && s.metrics.all.composite_grade !== grade)
        return false;
      if (provenance !== ALL && s.provenance !== provenance) return false;
      return true;
    });

    const dir = sortDir === "asc" ? 1 : -1;
    return filtered.slice().sort((a, b) => {
      const va = sortValue(a, sortKey);
      const vb = sortValue(b, sortKey);
      // null immer ans Ende, unabhaengig von der Richtung.
      const na = va === null || va === undefined;
      const nb = vb === null || vb === undefined;
      if (na && nb) return 0;
      if (na) return 1;
      if (nb) return -1;
      if (typeof va === "string" && typeof vb === "string") {
        return va.localeCompare(vb) * dir;
      }
      return ((va as number) - (vb as number)) * dir;
    });
  }, [systems, query, prefix, status, grade, provenance, sortKey, sortDir]);

  const selectClass =
    "h-8 rounded-md border border-zinc-800 bg-zinc-900/60 px-2 text-sm text-zinc-200 outline-none transition-colors hover:border-zinc-700 focus-visible:border-zinc-600";

  return (
    <div className="flex flex-col gap-4">
      {/* Filter-Leiste */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Name suchen…"
          className="h-8 w-52 rounded-md border border-zinc-800 bg-zinc-900/60 px-2.5 text-sm text-zinc-200 placeholder:text-zinc-600 outline-none transition-colors hover:border-zinc-700 focus-visible:border-zinc-600"
        />
        <select
          value={prefix}
          onChange={(e) => setPrefix(e.target.value)}
          className={selectClass}
          aria-label="Klasse filtern"
        >
          <option value={ALL}>Klasse: alle</option>
          {prefixes.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className={selectClass}
          aria-label="Status filtern"
        >
          <option value={ALL}>Status: alle</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s] ?? s}
            </option>
          ))}
        </select>
        <select
          value={grade}
          onChange={(e) => setGrade(e.target.value)}
          className={selectClass}
          aria-label="Composite-Grade filtern"
        >
          <option value={ALL}>Grade: alle</option>
          {grades.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>
        <select
          value={provenance}
          onChange={(e) => setProvenance(e.target.value)}
          className={selectClass}
          aria-label="Herkunft filtern"
        >
          <option value={ALL}>Herkunft: alle</option>
          <option value="manual">Manuell</option>
          <option value="programmatic">Programmatisch</option>
          <option value="engine">Engine</option>
        </select>
        <span className="ml-auto text-xs text-zinc-500 tabular-nums">
          {rows.length} / {systems.length}
        </span>
      </div>

      <div className="overflow-hidden rounded-lg border border-zinc-800">
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-800 hover:bg-transparent">
              <SortHead
                label="Name"
                colKey="name"
                active={sortKey === "name"}
                dir={sortDir}
                onSort={toggleSort}
              />
              <TableHead className="text-zinc-400">Klasse</TableHead>
              <TableHead className="text-zinc-400">TF</TableHead>
              <TableHead className="text-zinc-400">Status</TableHead>
              <TableHead className="text-zinc-400">Herkunft</TableHead>
              <TableHead className="text-zinc-400">Import</TableHead>
              <SortHead
                label="Trades"
                colKey="trades"
                active={sortKey === "trades"}
                dir={sortDir}
                onSort={toggleSort}
                className="text-right [&>button]:justify-end [&>button]:w-full"
              />
              <SortHead
                label="OOS EV"
                colKey="oos_ev"
                active={sortKey === "oos_ev"}
                dir={sortDir}
                onSort={toggleSort}
                className="text-right [&>button]:justify-end [&>button]:w-full"
              />
              <SortHead
                label="OOS ECE"
                colKey="oos_ece"
                active={sortKey === "oos_ece"}
                dir={sortDir}
                onSort={toggleSort}
                className="text-right [&>button]:justify-end [&>button]:w-full"
              />
              <SortHead
                label="Composite"
                colKey="composite"
                active={sortKey === "composite"}
                dir={sortDir}
                onSort={toggleSort}
                className="text-right [&>button]:justify-end [&>button]:w-full"
              />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableCell
                  colSpan={10}
                  className="h-24 text-center text-sm text-zinc-500"
                >
                  Keine Systeme passen zu den Filtern.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((s) => (
                <TableRow
                  key={s.id}
                  onClick={() => router.push(`/systems/${s.id}`)}
                  className="cursor-pointer border-zinc-800 hover:bg-zinc-900/60"
                >
                  <TableCell className="font-medium text-zinc-100">
                    {s.name}
                  </TableCell>
                  <TableCell className="text-zinc-400">{s.prefix}</TableCell>
                  <TableCell className="font-mono text-xs text-zinc-400 tabular-nums">
                    {s.timeframe}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={cn(
                        "font-normal",
                        STATUS_COLOR[s.status] ??
                          "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
                      )}
                    >
                      {STATUS_LABEL[s.status] ?? s.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      {s.provenance === "programmatic" ? (
                        <div className="flex flex-col gap-0.5">
                          <Badge
                            variant="outline"
                            title={
                              engineLabel(s.source_engine) ?? "programmatisch"
                            }
                            className="font-normal bg-violet-500/10 text-violet-300 border-violet-500/30"
                          >
                            prog
                          </Badge>
                          {engineLabel(s.source_engine) ? (
                            <span className="text-[10px] leading-none text-zinc-500">
                              {engineLabel(s.source_engine)}
                            </span>
                          ) : null}
                        </div>
                      ) : s.provenance === "engine" ? (
                        <Badge
                          variant="outline"
                          title="Von der eigenen Backtesting-Engine erzeugt"
                          className="font-normal bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                        >
                          engine
                        </Badge>
                      ) : (
                        <span className="text-xs text-zinc-600">manuell</span>
                      )}
                      {s.origin === "ui" ? (
                        <Badge
                          variant="outline"
                          title="In der UI angelegt (Re-Import-geschützt)"
                          className="font-normal bg-sky-500/10 text-sky-300 border-sky-500/30"
                        >
                          ui
                        </Badge>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell>
                    <span
                      className={cn(
                        "text-xs",
                        s.import_status === "incomplete"
                          ? "text-amber-500/80"
                          : "text-zinc-600",
                      )}
                    >
                      {s.import_status === "incomplete"
                        ? "unvollständig"
                        : "vollständig"}
                    </span>
                  </TableCell>
                  <TableCell className="text-right font-mono text-zinc-300 tabular-nums">
                    {fmtInt(s.metrics.all.total_trades)}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right font-mono tabular-nums",
                      rColor(s.metrics.oos.ev),
                    )}
                  >
                    {fmtR(s.metrics.oos.ev)}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right font-mono tabular-nums",
                      rColor(s.metrics.oos.ece),
                    )}
                  >
                    {fmtR(s.metrics.oos.ece)}
                  </TableCell>
                  <TableCell className="text-right">
                    <GradeBadge grade={s.metrics.all.composite_grade} />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
