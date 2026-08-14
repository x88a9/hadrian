"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Box, Grid3x3, Target } from "lucide-react";

import { Surface3D } from "@/components/surface-3d";
import { cn } from "@/lib/utils";
import type {
  AxisValue,
  TopographyCell,
  TopographyGrid,
} from "@/lib/types";

// --- Divergierende Farbskala (rot < 0 < emerald), symmetrisch um 0. ---
// Wird von der Heatmap UND der 3D-Surface geteilt.
const NEUTRAL: [number, number, number] = [39, 39, 42]; // zinc-800
const NEG: [number, number, number] = [239, 68, 68]; // red-500
const POS: [number, number, number] = [16, 185, 129]; // emerald-500

function lerp(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

export function divergingColor(
  value: number | null | undefined,
  maxAbs: number,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "rgb(24,24,27)"; // zinc-900 fuer fehlende Zellen
  }
  if (maxAbs <= 0) return `rgb(${NEUTRAL.join(",")})`;
  const t = Math.max(-1, Math.min(1, value / maxAbs));
  const target = t < 0 ? NEG : POS;
  const f = Math.abs(t);
  return `rgb(${lerp(NEUTRAL[0], target[0], f)},${lerp(
    NEUTRAL[1],
    target[1],
    f,
  )},${lerp(NEUTRAL[2], target[2], f)})`;
}

function fmtAxis(v: AxisValue): string {
  return typeof v === "number" ? String(v) : v;
}

function fmtVal(v: number | null | undefined, d = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(d);
}

const selectClass = cn(
  "h-8 max-w-full rounded-lg border border-zinc-800 bg-zinc-900/60 px-2.5 text-sm text-zinc-100",
  "outline-none transition-colors hover:border-zinc-700",
  "focus-visible:border-zinc-600 focus-visible:ring-2 focus-visible:ring-zinc-700",
);

function cellKey(x: AxisValue, y: AxisValue): string {
  return `${String(x)}|${String(y)}`;
}

function ViewToggle({
  view,
  onChange,
}: {
  view: "heatmap" | "surface";
  onChange: (v: "heatmap" | "surface") => void;
}) {
  const base =
    "inline-flex items-center gap-1.5 h-8 px-3 text-sm font-medium transition-colors";
  return (
    <div className="inline-flex overflow-hidden rounded-lg border border-zinc-800">
      <button
        type="button"
        onClick={() => onChange("heatmap")}
        className={cn(
          base,
          view === "heatmap"
            ? "bg-zinc-800 text-zinc-100"
            : "bg-zinc-900/40 text-zinc-400 hover:text-zinc-200",
        )}
      >
        <Grid3x3 className="size-4" /> Heatmap
      </button>
      <button
        type="button"
        onClick={() => onChange("surface")}
        className={cn(
          base,
          "border-l border-zinc-800",
          view === "surface"
            ? "bg-zinc-800 text-zinc-100"
            : "bg-zinc-900/40 text-zinc-400 hover:text-zinc-200",
        )}
      >
        <Box className="size-4" /> 3D
      </button>
    </div>
  );
}

function cellTitle(c: TopographyCell): string {
  const parts = [
    `value: ${fmtVal(c.value)}`,
    `net_ev: ${fmtVal(c.net_ev)}`,
    `n_trades: ${c.n_trades ?? "—"}`,
  ];
  if (c.n_neighbors && c.n_neighbors > 0) {
    parts.push(
      `Nachbarn (${c.n_neighbors}): min ${fmtVal(c.neighbor_min)} / mean ${fmtVal(
        c.neighbor_mean,
      )} / max ${fmtVal(c.neighbor_max)}`,
    );
  } else {
    parts.push("Nachbarn: keine");
  }
  if (c.low_confidence) parts.push("low_confidence");
  if (c.insufficient_sample) parts.push("insufficient_sample");
  return parts.join("\n");
}

interface HeatmapGridProps {
  grid: TopographyGrid;
}

function HeatmapGrid({ grid }: HeatmapGridProps) {
  const [hovered, setHovered] = useState<TopographyCell | null>(null);

  const { byKey, maxAbs } = useMemo(() => {
    const map = new Map<string, TopographyCell>();
    let m = 0;
    for (const c of grid.cells) {
      map.set(cellKey(c.x, c.y), c);
      if (typeof c.value === "number" && !Number.isNaN(c.value)) {
        m = Math.max(m, Math.abs(c.value));
      }
    }
    return { byKey: map, maxAbs: m };
  }, [grid]);

  // Zeilen von oben (hoechstes y) nach unten.
  const rows = [...grid.y_values].reverse();

  function isBest(c: TopographyCell): boolean {
    return (
      grid.best !== null &&
      String(grid.best.x) === String(c.x) &&
      String(grid.best.y) === String(c.y)
    );
  }
  function isRobust(c: TopographyCell): boolean {
    return (
      grid.robust_best !== null &&
      String(grid.robust_best.x) === String(c.x) &&
      String(grid.robust_best.y) === String(c.y)
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-auto">
        <div
          className="inline-grid gap-1 text-[11px]"
          style={{
            gridTemplateColumns: `auto repeat(${grid.x_values.length}, minmax(0, 52px))`,
          }}
        >
          {/* Kopfzeile: leere Ecke + x-Werte */}
          <div className="flex items-end justify-end pr-1 pb-1 text-zinc-500">
            <span className="font-mono">{grid.param_y}\{grid.param_x}</span>
          </div>
          {grid.x_values.map((xv) => (
            <div
              key={`x-${String(xv)}`}
              className="pb-1 text-center font-mono text-zinc-400"
            >
              {fmtAxis(xv)}
            </div>
          ))}

          {/* Zeilen */}
          {rows.map((yv) => (
            <div key={`row-${String(yv)}`} className="contents">
              <div className="flex items-center justify-end pr-1.5 font-mono text-zinc-400">
                {fmtAxis(yv)}
              </div>
              {grid.x_values.map((xv) => {
                const c = byKey.get(cellKey(xv, yv));
                if (!c) {
                  return (
                    <div
                      key={cellKey(xv, yv)}
                      className="flex aspect-square items-center justify-center rounded-sm border border-zinc-800/60 bg-zinc-900 text-zinc-700"
                    >
                      ·
                    </div>
                  );
                }
                const best = isBest(c);
                const robust = isRobust(c);
                return (
                  <div
                    key={cellKey(xv, yv)}
                    title={cellTitle(c)}
                    onMouseEnter={() => setHovered(c)}
                    onMouseLeave={() =>
                      setHovered((h) => (h === c ? null : h))
                    }
                    className={cn(
                      "relative flex aspect-square cursor-default items-center justify-center rounded-sm font-mono text-zinc-50",
                      robust && "ring-2 ring-amber-300",
                      best && !robust && "ring-1 ring-zinc-100/70",
                    )}
                    style={{ backgroundColor: divergingColor(c.value, maxAbs) }}
                  >
                    <span className="[text-shadow:0_1px_2px_rgba(0,0,0,0.6)]">
                      {fmtVal(c.value, 2)}
                    </span>
                    {robust && (
                      <Target className="absolute right-0.5 top-0.5 size-3 text-amber-200" />
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Hover-Detail */}
      <div className="min-h-[2.25rem] rounded-md border border-zinc-800 bg-zinc-900/40 px-3 py-1.5 text-xs text-zinc-400">
        {hovered ? (
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 font-mono">
            <span>
              {grid.param_x}={fmtAxis(hovered.x)} · {grid.param_y}=
              {fmtAxis(hovered.y)}
            </span>
            <span className="text-zinc-200">value {fmtVal(hovered.value)}</span>
            <span>net_ev {fmtVal(hovered.net_ev)}</span>
            <span>n {hovered.n_trades ?? "—"}</span>
            <span>
              nb {fmtVal(hovered.neighbor_min)}/{fmtVal(hovered.neighbor_mean)}/
              {fmtVal(hovered.neighbor_max)} ({hovered.n_neighbors ?? 0})
            </span>
          </div>
        ) : (
          <span className="text-zinc-600">
            Zelle überfahren für Details (Wert / net_ev / n_trades / Nachbarn)
          </span>
        )}
      </div>
    </div>
  );
}

interface TopographyHeatmapProps {
  grids: TopographyGrid[];
  preGate: boolean;
}

export function TopographyHeatmap({ grids, preGate }: TopographyHeatmapProps) {
  const [gridIdx, setGridIdx] = useState(0);
  const [view, setView] = useState<"heatmap" | "surface">("heatmap");

  useEffect(() => {
    if (gridIdx >= grids.length) setGridIdx(0);
  }, [grids, gridIdx]);

  if (grids.length === 0) return null;
  const grid = grids[Math.min(gridIdx, grids.length - 1)];

  return (
    <div className="flex flex-col gap-4">
      {preGate && (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>
            <span className="font-semibold">Pre-Gate Sweep.</span> Roh-Sweep vor
            Signal-Gating — EV-Niveau inflationiert, Form (Plateau vs. Spitze)
            aussagekräftig, absolute Höhe nicht.
          </span>
        </div>
      )}

      {/* Kopf: Grid-Auswahl + Aggregate + View-Toggle */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-[0.7rem] font-medium uppercase tracking-wide text-zinc-500">
            Grid ({grids.length})
          </span>
          <select
            className={selectClass}
            value={gridIdx}
            onChange={(e) => setGridIdx(Number(e.target.value))}
          >
            {grids.map((g, i) => (
              <option key={g.id} value={i}>
                {g.label}
              </option>
            ))}
          </select>
        </div>
        <ViewToggle view={view} onChange={setView} />
      </div>

      {/* Aggregat-Kennzahlen */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="rounded-md border border-zinc-800 bg-zinc-900/40 px-3 py-2">
          <div className="text-zinc-500">pct positive</div>
          <div className="font-mono text-sm text-zinc-100">
            {grid.pct_positive === null
              ? "—"
              : `${(grid.pct_positive * 100).toFixed(1)}%`}
          </div>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-900/40 px-3 py-2">
          <div className="text-zinc-500">
            best{preGate ? " (pre-gate)" : ""}
          </div>
          <div
            className={cn(
              "font-mono text-sm",
              preGate ? "text-zinc-300" : "text-emerald-300",
            )}
          >
            {grid.best ? fmtVal(grid.best.value) : "—"}
          </div>
          {grid.best && (
            <div className="font-mono text-[10px] text-zinc-500">
              {fmtAxis(grid.best.x)} / {fmtAxis(grid.best.y)}
            </div>
          )}
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-900/40 px-3 py-2">
          <div className="flex items-center gap-1 text-zinc-500">
            <Target className="size-3 text-amber-300" /> robust best
          </div>
          <div className="font-mono text-sm text-amber-200">
            {grid.robust_best ? fmtVal(grid.robust_best.value) : "—"}
          </div>
          {grid.robust_best && (
            <div className="font-mono text-[10px] text-zinc-500">
              floor {fmtVal(grid.robust_best.floor)}
            </div>
          )}
        </div>
      </div>

      {view === "heatmap" ? (
        <HeatmapGrid grid={grid} />
      ) : (
        <Surface3D grid={grid} />
      )}
    </div>
  );
}
