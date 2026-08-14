"use client";

import { useMemo } from "react";

import { divergingColor } from "@/components/topography-heatmap";
import type { AxisValue, TopographyGrid } from "@/lib/types";

// Isometrische SVG-Projektion des Grids: Vierecks-Flaechen zwischen
// benachbarten Gitterpunkten, z = value, Maler-Reihenfolge hinten->vorn.
// Farbskala geteilt mit der Heatmap (divergierend rot < 0 < emerald).
// Bewusst dependency-frei (kein Plotly), Muster: concept-graph.tsx.

const TILE_W = 40; // Horizontalversatz je Achsenschritt
const TILE_H = 20; // Vertikalversatz (Tiefe) je Achsenschritt
const Z_SCALE = 72; // Pixel je normalisierter Hoehe (|value|/maxAbs)
const PAD = 44;

function fmtAxis(v: AxisValue): string {
  return typeof v === "number" ? String(v) : v;
}

interface ProjPoint {
  x: number;
  y: number;
  value: number | null;
}

interface Face {
  path: string;
  fill: string;
  depth: number;
}

export function Surface3D({ grid }: { grid: TopographyGrid }) {
  const model = useMemo(() => {
    const nx = grid.x_values.length;
    const ny = grid.y_values.length;

    const byKey = new Map<string, number | null>();
    let maxAbs = 0;
    for (const c of grid.cells) {
      byKey.set(`${String(c.x)}|${String(c.y)}`, c.value);
      if (typeof c.value === "number" && !Number.isNaN(c.value)) {
        maxAbs = Math.max(maxAbs, Math.abs(c.value));
      }
    }

    const valueAt = (i: number, j: number): number | null => {
      const v = byKey.get(`${String(grid.x_values[i])}|${String(grid.y_values[j])}`);
      return typeof v === "number" && !Number.isNaN(v) ? v : null;
    };

    // Rohprojektion (ohne Offset).
    const raw = (i: number, j: number): ProjPoint => {
      const value = valueAt(i, j);
      const h = maxAbs > 0 && value !== null ? value / maxAbs : 0;
      return {
        x: (i - j) * TILE_W,
        y: (i + j) * TILE_H - h * Z_SCALE,
        value,
      };
    };

    // Bounds ueber alle Ecken (inkl. Hoehenausschlag).
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (let i = 0; i < nx; i++) {
      for (let j = 0; j < ny; j++) {
        const p = raw(i, j);
        minX = Math.min(minX, p.x);
        maxX = Math.max(maxX, p.x);
        minY = Math.min(minY, p.y - Z_SCALE);
        maxY = Math.max(maxY, p.y + Z_SCALE);
      }
    }
    if (!Number.isFinite(minX)) {
      minX = 0;
      maxX = 0;
      minY = 0;
      maxY = 0;
    }

    const offX = PAD - minX;
    const offY = PAD - minY;
    const p = (i: number, j: number): ProjPoint => {
      const r = raw(i, j);
      return { x: r.x + offX, y: r.y + offY, value: r.value };
    };

    const faces: Face[] = [];
    for (let i = 0; i < nx - 1; i++) {
      for (let j = 0; j < ny - 1; j++) {
        const a = p(i, j);
        const b = p(i + 1, j);
        const c = p(i + 1, j + 1);
        const d = p(i, j + 1);
        if (
          a.value === null ||
          b.value === null ||
          c.value === null ||
          d.value === null
        ) {
          continue;
        }
        const avg = (a.value + b.value + c.value + d.value) / 4;
        faces.push({
          path: `M ${a.x} ${a.y} L ${b.x} ${b.y} L ${c.x} ${c.y} L ${d.x} ${d.y} Z`,
          fill: divergingColor(avg, maxAbs),
          depth: i + j, // kleiner = weiter hinten -> zuerst zeichnen
        });
      }
    }
    faces.sort((f1, f2) => f1.depth - f2.depth);

    // Tick-Punkte fuer Achsen (Basis-z=0 ignoriert Hoehe -> stabile Kante).
    const xTicks = grid.x_values.map((v, i) => ({
      label: fmtAxis(v),
      // Vorderkante: j = ny-1
      px: (i - (ny - 1)) * TILE_W + offX,
      py: (i + (ny - 1)) * TILE_H + offY,
    }));
    const yTicks = grid.y_values.map((v, j) => ({
      label: fmtAxis(v),
      // linke Kante: i = 0
      px: (0 - j) * TILE_W + offX,
      py: (0 + j) * TILE_H + offY,
    }));

    return {
      faces,
      width: maxX - minX + 2 * PAD,
      height: maxY - minY + 2 * PAD,
      xTicks,
      yTicks,
      xLabelAt: p(nx - 1, ny - 1),
      yLabelAt: p(0, ny - 1),
      zLabelAt: p(0, 0),
      degenerate: nx < 2 || ny < 2,
    };
  }, [grid]);

  if (model.degenerate) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-zinc-500">
        Grid zu klein für 3D-Darstellung.
      </div>
    );
  }

  return (
    <div className="overflow-auto rounded-xl border border-zinc-800 bg-zinc-900/30 p-2">
      <svg
        width={model.width}
        height={model.height}
        viewBox={`0 0 ${model.width} ${model.height}`}
        className="block"
        role="img"
        aria-label="Isometrische 3D-Surface des Sweep-Grids"
      >
        {/* Flaechen (Maler-Reihenfolge). */}
        {model.faces.map((f, i) => (
          <path
            key={i}
            d={f.path}
            fill={f.fill}
            stroke="rgba(0,0,0,0.35)"
            strokeWidth={0.75}
            strokeLinejoin="round"
          />
        ))}

        {/* x-Ticks (TP) an der Vorderkante. */}
        {model.xTicks.map((t, i) => (
          <text
            key={`xt-${i}`}
            x={t.px}
            y={t.py + 12}
            textAnchor="middle"
            className="fill-zinc-500 text-[9px] font-mono"
          >
            {t.label}
          </text>
        ))}
        {/* y-Ticks (SL) an der linken Kante. */}
        {model.yTicks.map((t, i) => (
          <text
            key={`yt-${i}`}
            x={t.px - 6}
            y={t.py + 4}
            textAnchor="end"
            className="fill-zinc-500 text-[9px] font-mono"
          >
            {t.label}
          </text>
        ))}

        {/* Achsentitel. */}
        <text
          x={model.xLabelAt.x + 8}
          y={model.xLabelAt.y + 26}
          textAnchor="middle"
          className="fill-zinc-400 text-[10px] font-medium"
        >
          x = TP ({grid.param_x})
        </text>
        <text
          x={model.yLabelAt.x - 8}
          y={model.yLabelAt.y + 22}
          textAnchor="end"
          className="fill-zinc-400 text-[10px] font-medium"
        >
          y = SL ({grid.param_y})
        </text>
        <text
          x={model.zLabelAt.x}
          y={PAD - 18}
          textAnchor="middle"
          className="fill-zinc-400 text-[10px] font-medium"
        >
          z = OOS-EV
        </text>
      </svg>
    </div>
  );
}
