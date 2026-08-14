// Live-Trading-Formatierung & Stufen-Vokabular (Phase 7).
// Deterministic (no locale, no timezone), like lib/format.ts.

import type { LiveStage, LiveWinLoss } from "./types";

const PLACEHOLDER = "—";

// Lifecycle order, excluding cancelled, which is a terminal special case.
export const STAGE_ORDER: LiveStage[] = [
  "setup_sighted",
  "risk_calculated",
  "order_placed",
  "entry_filled",
  "running",
  "closed",
];

export const STAGE_LABEL: Record<LiveStage, string> = {
  setup_sighted: "Setup gesichtet",
  risk_calculated: "Risk berechnet",
  order_placed: "Order gesetzt",
  entry_filled: "Entry gefüllt",
  running: "Laufend",
  closed: "Geschlossen",
  cancelled: "Abgebrochen",
};

// Open stages: non-terminal, still in progress.
export const OPEN_STAGES: LiveStage[] = [
  "order_placed",
  "entry_filled",
  "running",
];

// Which transition each stage allows; mirrors the backend.
export const NEXT_STAGES: Record<LiveStage, LiveStage[]> = {
  setup_sighted: ["risk_calculated", "cancelled"],
  risk_calculated: ["order_placed", "cancelled"],
  order_placed: ["entry_filled", "cancelled"],
  entry_filled: ["running", "closed"],
  running: ["closed"],
  closed: [],
  cancelled: [],
};

// Tailwind classes (background + text + border) per stage, dark terminal look.
export function stageColor(stage: LiveStage): string {
  switch (stage) {
    case "setup_sighted":
      return "bg-zinc-500/15 text-zinc-300 border-zinc-500/30";
    case "risk_calculated":
      return "bg-sky-500/15 text-sky-400 border-sky-500/30";
    case "order_placed":
      return "bg-indigo-500/15 text-indigo-400 border-indigo-500/30";
    case "entry_filled":
    case "running":
      return "bg-cyan-500/15 text-cyan-400 border-cyan-500/30";
    case "closed":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "cancelled":
      return "bg-zinc-700/30 text-zinc-500 border-zinc-700/40 line-through";
  }
}

export function winLossColor(wl: LiveWinLoss | null | undefined): string {
  switch (wl) {
    case "win":
      return "text-emerald-400";
    case "loss":
      return "text-red-400";
    case "break_even":
      return "text-zinc-400";
    default:
      return "text-zinc-400";
  }
}

// USD with a sign (for PnL) or without (for amounts).
export function fmtUsd(
  value: number | null | undefined,
  opts: { sign?: boolean; decimals?: number } = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return PLACEHOLDER;
  }
  const decimals = opts.decimals ?? 2;
  const body = `$${Math.abs(value).toFixed(decimals)}`;
  if (opts.sign) return `${value >= 0 ? "+" : "-"}${body}`;
  return value < 0 ? `-${body}` : body;
}

// Seconds -> a compact display (e.g. "3d 4h", "2h 15m", "45s").
export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return PLACEHOLDER;
  }
  const s = Math.max(0, Math.floor(seconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s % 60}s`;
  return `${s}s`;
}

// Elapsed time of an open position, from a start timestamp until now.
export function durationSince(
  iso: string | null | undefined,
  nowMs: number,
): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return (nowMs - t) / 1000;
}

// Percentage (input is already a percentage, e.g. deviation_pct), one decimal.
export function fmtPctValue(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return PLACEHOLDER;
  }
  return `${value.toFixed(1)}%`;
}
