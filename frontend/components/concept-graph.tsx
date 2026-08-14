"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { cn } from "@/lib/utils";
import type {
  ConceptGraph as ConceptGraphData,
  GraphNode,
  SystemStatus,
} from "@/lib/types";

// Fuellfarbe pro Systemstatus (D6: status-codiert).
const STATUS_FILL: Record<SystemStatus, string> = {
  backtest: "#71717a", // zinc-500
  live_testing: "#3b82f6", // blue-500
  active: "#22c55e", // green-500
  retired: "#3f3f46", // zinc-700 (dunkel)
};

const CONCEPT_FILL = "#8b5cf6"; // violet-500 (Akzent)

const NODE_WIDTH = 168;
const NODE_HEIGHT = 30;
const ROW_GAP = 14;
const COL_GAP = 320; // horizontaler Abstand Konzept-Spalte -> System-Spalte
const PAD_X = 24;
const PAD_TOP = 24;
const PAD_BOTTOM = 24;

interface PlacedNode extends GraphNode {
  x: number; // linke obere Ecke
  y: number;
  cx: number; // Mittelpunkt (fuer Kanten)
  cy: number;
}

interface Edge {
  key: string;
  conceptId: string;
  systemId: string;
  path: string;
  source: "manual" | "heuristic";
}

// Sanfte horizontale Bezier-Kurve von rechter Kante Konzept zu linker Kante System.
function bezierPath(x1: number, y1: number, x2: number, y2: number): string {
  const dx = (x2 - x1) / 2;
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

export function ConceptGraph({ data }: { data: ConceptGraphData }) {
  const router = useRouter();
  const [hovered, setHovered] = useState<string | null>(null);

  const { conceptNodes, systemNodes, edges, width, height } = useMemo(() => {
    const concepts = data.nodes.filter((n) => n.type === "concept");
    const systems = data.nodes.filter((n) => n.type === "system");

    const conceptColX = PAD_X;
    const systemColX = PAD_X + NODE_WIDTH + COL_GAP;

    // Vertikal zentriert je Spalte verteilen.
    function layout(nodes: GraphNode[], colX: number): PlacedNode[] {
      return nodes.map((n, i) => {
        const y = PAD_TOP + i * (NODE_HEIGHT + ROW_GAP);
        return {
          ...n,
          x: colX,
          y,
          cx: colX + NODE_WIDTH / 2,
          cy: y + NODE_HEIGHT / 2,
        };
      });
    }

    const placedConcepts = layout(concepts, conceptColX);
    const placedSystems = layout(systems, systemColX);

    const byId = new Map<string, PlacedNode>();
    for (const n of placedConcepts) byId.set(n.id, n);
    for (const n of placedSystems) byId.set(n.id, n);

    const placedEdges: Edge[] = [];
    for (const link of data.links) {
      // Kanten immer Konzept -> System orientieren (source/target-Reihenfolge
      // im Contract nicht garantiert).
      const a = byId.get(link.source);
      const b = byId.get(link.target);
      if (!a || !b) continue;
      const concept = a.type === "concept" ? a : b;
      const system = a.type === "concept" ? b : a;
      if (concept.type !== "concept" || system.type !== "system") continue;
      placedEdges.push({
        key: `${link.source}->${link.target}`,
        conceptId: concept.id,
        systemId: system.id,
        source: link.assignment_source,
        path: bezierPath(
          concept.x + NODE_WIDTH,
          concept.cy,
          system.x,
          system.cy,
        ),
      });
    }

    const rows = Math.max(placedConcepts.length, placedSystems.length);
    const contentHeight =
      PAD_TOP + rows * (NODE_HEIGHT + ROW_GAP) - ROW_GAP + PAD_BOTTOM;
    const contentWidth = systemColX + NODE_WIDTH + PAD_X;

    return {
      conceptNodes: placedConcepts,
      systemNodes: placedSystems,
      edges: placedEdges,
      width: contentWidth,
      height: Math.max(contentHeight, 200),
    };
  }, [data]);

  // Bestimmt, ob ein Knoten bei aktivem Hover hervorgehoben ist.
  const connectedNodes = useMemo(() => {
    if (!hovered) return null;
    const set = new Set<string>([hovered]);
    for (const e of edges) {
      if (e.conceptId === hovered) set.add(e.systemId);
      if (e.systemId === hovered) set.add(e.conceptId);
    }
    return set;
  }, [hovered, edges]);

  function isEdgeActive(e: Edge): boolean {
    if (!hovered) return false;
    return e.conceptId === hovered || e.systemId === hovered;
  }

  function nodeDimmed(id: string): boolean {
    if (!connectedNodes) return false;
    return !connectedNodes.has(id);
  }

  return (
    <div className="overflow-auto rounded-xl border border-zinc-800 bg-zinc-900/30 p-2">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="block"
        role="img"
        aria-label="Konzept-System-Graph"
      >
        {/* Kanten zuerst (hinter den Knoten). */}
        <g>
          {edges.map((e) => {
            const active = isEdgeActive(e);
            const dimmed = hovered !== null && !active;
            return (
              <path
                key={e.key}
                d={e.path}
                fill="none"
                stroke={active ? "#a78bfa" : "#52525b"}
                strokeWidth={active ? 2 : 1.25}
                strokeDasharray={e.source === "heuristic" ? "4 3" : undefined}
                opacity={dimmed ? 0.12 : e.source === "heuristic" ? 0.55 : 0.8}
                className="transition-opacity"
              />
            );
          })}
        </g>

        {/* Konzept-Knoten. */}
        <g>
          {conceptNodes.map((n) => {
            const dimmed = nodeDimmed(n.id);
            return (
              <g
                key={n.id}
                transform={`translate(${n.x}, ${n.y})`}
                onMouseEnter={() => setHovered(n.id)}
                onMouseLeave={() => setHovered(null)}
                className="cursor-default"
                opacity={dimmed ? 0.25 : 1}
              >
                <rect
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx={7}
                  fill={CONCEPT_FILL}
                  fillOpacity={0.18}
                  stroke={CONCEPT_FILL}
                  strokeWidth={hovered === n.id ? 2 : 1.25}
                />
                <text
                  x={NODE_WIDTH / 2}
                  y={NODE_HEIGHT / 2}
                  textAnchor="middle"
                  dominantBaseline="central"
                  className="fill-violet-200 text-[11px] font-medium"
                >
                  {truncate(n.label, 22)}
                </text>
              </g>
            );
          })}
        </g>

        {/* System-Knoten (klickbar -> Detailseite). */}
        <g>
          {systemNodes.map((n) => {
            const dimmed = nodeDimmed(n.id);
            const fill = n.status ? STATUS_FILL[n.status] : "#71717a";
            const numericId = n.id.split(":")[1];
            return (
              <g
                key={n.id}
                transform={`translate(${n.x}, ${n.y})`}
                onMouseEnter={() => setHovered(n.id)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => router.push(`/systems/${numericId}`)}
                className="cursor-pointer"
                opacity={dimmed ? 0.25 : 1}
                role="link"
                aria-label={`System ${n.label}`}
              >
                <rect
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx={7}
                  fill={fill}
                  fillOpacity={0.18}
                  stroke={fill}
                  strokeWidth={hovered === n.id ? 2 : 1.25}
                />
                <text
                  x={12}
                  y={NODE_HEIGHT / 2}
                  textAnchor="start"
                  dominantBaseline="central"
                  className="fill-zinc-100 text-[11px] font-medium"
                >
                  {truncate(n.label, 20)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

// Legende (Kantenstil + Statusfarben) fuer die Seite.
export function ConceptGraphLegend({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-zinc-400",
        className,
      )}
    >
      <div className="flex items-center gap-1.5">
        <svg width="26" height="8" className="shrink-0">
          <line x1="0" y1="4" x2="26" y2="4" stroke="#a1a1aa" strokeWidth="1.5" />
        </svg>
        <span>manuell</span>
      </div>
      <div className="flex items-center gap-1.5">
        <svg width="26" height="8" className="shrink-0">
          <line
            x1="0"
            y1="4"
            x2="26"
            y2="4"
            stroke="#a1a1aa"
            strokeWidth="1.5"
            strokeDasharray="4 3"
          />
        </svg>
        <span>heuristisch</span>
      </div>
      <span className="text-zinc-700">·</span>
      <LegendDot color="#8b5cf6" label="Konzept" />
      <LegendDot color={STATUS_FILL.backtest} label="Backtest" />
      <LegendDot color={STATUS_FILL.live_testing} label="Live Testing" />
      <LegendDot color={STATUS_FILL.active} label="Active" />
      <LegendDot color={STATUS_FILL.retired} label="Retired" />
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="inline-block size-2.5 rounded-sm"
        style={{ backgroundColor: color, opacity: 0.85 }}
      />
      <span>{label}</span>
    </div>
  );
}
